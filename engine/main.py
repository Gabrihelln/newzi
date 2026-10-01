import argparse, json, logging
import time
import socket, ssl
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))
from newzi_engine.collectors.registry import load_sources, load_settings
from newzi_engine.collectors.rss import RSSCollector
from newzi_engine.images import enrich_missing_images
from newzi_engine.storage import Store
from newzi_engine.processors.dedup import exact_deduplicate
from newzi_engine.processors.classify import classify_articles
from newzi_engine.editorial.genre import classify_editorial
from newzi_engine.clustering.events import cluster_articles
from newzi_engine.ranking.score import rank_events
from newzi_engine.briefing.render import select_events, write_outputs
from newzi_engine.briefing.clustering_report import write_clustering_report
from newzi_engine.briefing.editorial_report import write_editorial_report

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def _run_stage(name, function, *args, timings=None, **kwargs):
    started = time.perf_counter()
    logging.info("[PIPELINE] stage=%s status=started", name)
    try:
        return function(*args, **kwargs)
    except Exception:
        logging.exception("[PIPELINE] stage=%s status=failed", name)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if timings is not None:
            timings[name] = duration_ms
        logging.info("[PIPELINE] stage=%s duration_ms=%s", name, duration_ms)

def collect_sources(no_network=False, incremental=False):
    """Fetch configured feeds and persist articles without running editorial ranking."""
    started=time.perf_counter(); sources=load_sources(); settings=load_settings(); store=Store(); collected=[]; results=[]
    if no_network:
        articles=store.all_articles(); results=[{"source_id":s['id'],"name":s['name'],"status":"SKIPPED","duration_ms":0,"articles_seen":0,"articles_new":0,"newest_article":None} for s in sources]
    else:
        health=store.get_source_health(); max_workers=max(1,int(settings.get("request",{}).get("max_concurrent_sources",6)))
        def fetch(source):
            saved=health.get(source['id'],{}); open_until=saved.get('circuit_open_until')
            if open_until:
                try:
                    if datetime.fromisoformat(open_until.replace('Z','+00:00'))>datetime.now(timezone.utc):
                        return source,[],"SOURCE_BACKOFF",{"status":"BACKOFF","duration_ms":0,"articles_seen":0,"newest_article":None},{}
                except ValueError: pass
            collector=RSSCollector(settings); batch,error=collector.collect(source,{"etag":saved.get('etag'),"last_modified":saved.get('last_modified')})
            return source,batch,error,collector.last_metrics,collector.validators
        fetched=[]
        with ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix="newzi-source") as pool:
            futures=[pool.submit(fetch,source) for source in sources]
            for future in as_completed(futures): fetched.append(future.result())
        for source,batch,error,metrics,validators in fetched:
            ok=not error
            if metrics.get('status')=='BACKOFF': ok=False
            if metrics.get('status')=='NOT_MODIFIED': ok=True
            if metrics.get('status') not in ('BACKOFF',): store.save_source_result(source['id'],metrics,validators,error)
            collected.extend(batch)
            results.append({"source_id":source['id'],"name":source['name'],"status":metrics.get('status','FAILED'),"duration_ms":int(metrics.get('duration_ms') or 0),"fetch_ms":int(metrics.get('fetch_ms') or 0),"ttfb_ms":int(metrics.get('ttfb_ms') or 0),"download_ms":int(metrics.get('download_ms') or 0),"parse_ms":int(metrics.get('parse_ms') or 0),"discovery_ms":int(metrics.get('discovery_ms') or 0),"response_bytes":int(metrics.get('response_bytes') or 0),"http_status":metrics.get('http_status'),"articles_seen":int(metrics.get('articles_seen') or 0),"articles_new":0,"newest_article":metrics.get('newest_article'),"error":error})
            logging.info("[COLLECT] %s: %s (%s, %sms)",source['name'],len(batch),error or 'OK',metrics.get('duration_ms',0))
        upsert,changed=store.upsert_articles(collected)
        normalized_images=store.normalize_existing_image_urls()
        if normalized_images:
            changed_by_id={article.article_id:article for article in (*changed,*normalized_images)}
            changed=list(changed_by_id.values())
        logging.info("[DATABASE] operation=article_upsert duration_ms=%s new=%s updated=%s unchanged=%s",upsert.get("persistence_ms",0),upsert.get("new",0),upsert.get("updated",0),upsert.get("unchanged",0))
        for row in results:
            counts=upsert['by_source'].get(row['source_id'],{}); row['articles_new']=counts.get('new',0); row['articles_updated']=counts.get('updated',0); row['articles_unchanged']=counts.get('unchanged',0)
        image_settings=settings.get("request",{})
        logging.info("[IMAGE] stage=enrichment status=started limit=%s workers=%s per_request_timeout_seconds=%s",image_settings.get("image_enrichment_batch_size",8),image_settings.get("image_enrichment_workers",4),image_settings.get("image_metadata_timeout_seconds",2.5))
        image_metrics=enrich_missing_images(store,limit=int(image_settings.get("image_enrichment_batch_size",8)),max_workers=int(image_settings.get("image_enrichment_workers",4)),timeout_seconds=float(image_settings.get("image_metadata_timeout_seconds",2.5))) if hasattr(store,"articles_needing_image") else {"checked":0,"found":0,"failed":0,"duration_ms":0,"updated_articles":[]}
        image_metrics.pop("updated_articles",[])
        articles=store.all_articles()
        # Publish the metadata snapshot only. This repairs older rows whose
        # images were enriched after indexing without re-running classification.
        image_metrics["indexed_articles_updated"]=_publish_image_updates(articles)
        logging.info("[IMAGE] stage=enrichment status=complete checked=%s found=%s failed=%s probes=%s timeouts=%s article_pages=%s indexed_image_updates=%s duration_ms=%s",image_metrics.get("checked",0),image_metrics.get("found",0),image_metrics.get("failed",0),image_metrics.get("image_probe_attempts",0),image_metrics.get("image_probe_timeouts",0),image_metrics.get("article_pages_fetched",0),image_metrics.get("indexed_articles_updated",0),image_metrics.get("duration_ms",0))
    if no_network:
        image_metrics={"checked":0,"found":0,"failed":0,"duration_ms":0,"indexed_articles_updated":0}
    successful=sum(row['status'] in ('SUCCESS','NOT_MODIFIED','SKIPPED') for row in results)
    durations=sorted(row['duration_ms'] for row in results if row['status']!='SKIPPED')
    total_ms=int((time.perf_counter()-started)*1000)
    source_errors={row['source_id']:row['error'] for row in results if row.get('error')}
    stats={"sources_checked":len(sources),"sources_successful":successful,"source_errors":source_errors,"source_metrics":sorted(results,key=lambda row:row['duration_ms'],reverse=True),"collection_total_ms":total_ms,"collection_fastest_ms":min(durations) if durations else 0,"collection_median_ms":durations[len(durations)//2] if durations else 0,"collection_slowest_ms":max(durations) if durations else 0,"persistence_ms":int(upsert.get('persistence_ms',0)) if not no_network else 0,"article_image_enrichment":image_metrics,"articles_new":sum(row.get('articles_new',0) for row in results),"articles_updated":sum(row.get('articles_updated',0) for row in results),"articles_unchanged":sum(row.get('articles_unchanged',0) for row in results)}
    return stats,(changed if incremental and not no_network else articles)


def _publish_image_updates(articles):
    if not articles:
        return 0
    try:
        sys.path.insert(0,str(PROJECT_ROOT/'backend'/'src'))
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.content import sync_article_image_metadata
        return sync_article_image_metadata(ProductRepository(),articles)
    except Exception as exc:
        logging.warning("[IMAGE] Best-effort index update skipped: %s",exc)
        return 0


def backfill_article_images(limit=100):
    """Backfill only missing image metadata; never run article classification."""
    settings=load_settings().get("request",{})
    store=Store()
    result=enrich_missing_images(store,limit=limit,max_workers=int(settings.get("image_enrichment_workers",4)),timeout_seconds=float(settings.get("image_metadata_timeout_seconds",2.5)))
    updated=result.pop("updated_articles",[])
    result["indexed_articles_updated"]=_publish_image_updates(updated)
    return result

def run(no_network=False):
    engine_started = time.perf_counter()
    logging.info("[PIPELINE] engine=status=started no_network=%s",no_network)
    stage_timings = {}
    collection_stats,articles=_run_stage("source_collection", collect_sources, no_network, timings=stage_timings)
    sources=load_sources(); settings=load_settings(); store=Store()
    max_age=settings.get("request", {}).get("max_age_days", 30)
    cutoff=datetime.now(timezone.utc)-timedelta(days=max_age)
    articles=_run_stage("normalize_and_filter_articles", lambda: [a for a in articles if not a.published_at or a.published_at >= cutoff], timings=stage_timings)
    source_map={s["id"]:s for s in sources}
    def apply_source_metadata():
        for article in articles:
            source=source_map.get(article.source_id,{})
            article.source_type=source.get("source_type", article.source_type); article.publisher_id=source.get("publisher_id", article.publisher_id or article.source_id)
    _run_stage("source_metadata", apply_source_metadata, timings=stage_timings)
    unique,removed=_run_stage("exact_deduplication", exact_deduplicate, articles, timings=stage_timings)
    _run_stage("article_classification", classify_articles, unique, timings=stage_timings)
    _run_stage("editorial_classification", classify_editorial, unique, timings=stage_timings)
    events,audit=_run_stage("event_clustering", cluster_articles, unique, settings, sources, diagnostics=True, timings=stage_timings)
    ranked=_run_stage("event_ranking", rank_events, events, sources, settings, timings=stage_timings)
    selected=_run_stage("briefing_composition", select_events, ranked, timings=stage_timings)
    from newzi_engine.topic_registry import taxonomy
    category_counts={cat:sum(cat in e.categories for e in events) for cat in (*taxonomy().nodes,"OTHER")}; eligible=len(ranked)
    genre_counts={g:sum(e.content_genre==g for e in events) for g in sorted(set(e.content_genre for e in events))}
    stats={**collection_stats,"sources_failed":collection_stats["sources_checked"]-collection_stats["sources_successful"],"articles_collected":len(articles),"articles_after_deduplication":len(unique),"exact_duplicates_removed":len(removed),"events_created":len(events),"single_source_events":sum(len(set(e.publisher_ids or e.source_ids))==1 for e in events),"multi_source_events":sum(len(set(e.publisher_ids or e.source_ids))>1 for e in events),**{f"events_{k.lower()}":v for k,v in category_counts.items()},"events_excluded_other":category_counts["OTHER"],"eligible_events":eligible,"average_articles_per_event":round(len(unique)/max(1,len(events)),2),"average_sources_per_event":round(sum(len(set(e.publisher_ids or e.source_ids)) for e in events)/max(1,len(events)),2),"genre_distribution":genre_counts,"eligible_by_genre":{g:sum(e.content_genre==g for e in ranked) for g in genre_counts},"events_ranked":len(ranked),"items_selected":len(selected),"pipeline_stage_ms":stage_timings,"product_index_update":"not_run_by_default_engine_cli"}
    _run_stage("output_rendering", write_outputs, selected, stats, timings=stage_timings)
    _run_stage("clustering_report", write_clustering_report, events, audit, timings=stage_timings)
    _run_stage("editorial_report", write_editorial_report, unique, events, ranked, timings=stage_timings)
    _run_stage("engine_run_persistence", store.save_run, stats, timings=stage_timings)
    logging.info("[INDEX] stage=product_content_index status=not_run by=default_engine_cli")
    logging.info("[PIPELINE] engine=status=completed total_duration_ms=%s",round((time.perf_counter()-engine_started)*1000,2))
    logging.info("[ARTICLES] Collected: %s; exact duplicates removed: %s; valid: %s",len(articles),len(removed),len(unique)); logging.info("[CLUSTERING] Events: %s; multi-source: %s",len(events),stats['multi_source_events']); logging.info("[BRIEFING] Items selected: %s",len(selected)); return stats,selected

def profile_source(source_id):
    """Profile one configured source end-to-end, including a separate DNS/TCP/TLS probe."""
    source=next((item for item in load_sources() if item['id']==source_id),None)
    if not source: raise SystemExit(f"Unknown source id: {source_id}")
    url=urlsplit(source['feed_url']); timings={}; started=time.perf_counter()
    dns_started=time.perf_counter(); addresses=socket.getaddrinfo(url.hostname,url.port or 443,type=socket.SOCK_STREAM); timings['dns_ms']=round((time.perf_counter()-dns_started)*1000,2)
    family,socktype,proto,_,address=addresses[0]; sock=socket.socket(family,socktype,proto); sock.settimeout(4)
    try:
        tcp_started=time.perf_counter(); sock.connect(address); timings['tcp_ms']=round((time.perf_counter()-tcp_started)*1000,2)
        tls_started=time.perf_counter(); secure=ssl.create_default_context().wrap_socket(sock,server_hostname=url.hostname); timings['tls_ms']=round((time.perf_counter()-tls_started)*1000,2); secure.close()
    finally:
        try: sock.close()
        except OSError: pass
    store=Store()
    # Diagnostic runs deliberately perform a full feed response so cache hits do not
    # hide transport, parse, discovery, and per-item processing timings.
    collector=RSSCollector(load_settings()); items,error=collector.collect(source); timings.update(collector.last_metrics)
    if not error and items:
        upsert,changed=store.upsert_articles(items); timings['articles_new']=upsert['by_source'].get(source_id,{}).get('new',0); timings['articles_updated']=upsert['by_source'].get(source_id,{}).get('updated',0); timings['articles_unchanged']=upsert['by_source'].get(source_id,{}).get('unchanged',0)
        sys.path.insert(0,str(PROJECT_ROOT/'backend'/'src'))
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.content import sync_content
        repo=ProductRepository(); phase=time.perf_counter(); index=sync_content(repo,changed); timings['article_processing_ms']=round((time.perf_counter()-phase)*1000,2); timings['classification_ms']=index.get('classification_ms',0); timings['classification_count']=index.get('classification_count',0); timings['average_article_processing_ms']=index.get('average_article_processing_ms',0); timings['articles_changed']=len(changed)
    timings['total_profile_ms']=round((time.perf_counter()-started)*1000,2); timings['source_id']=source_id; timings['source_name']=source['name']; timings['error']=error; print(json.dumps(timings,ensure_ascii=False,indent=2))

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--diagnostics",action="store_true"); parser.add_argument("--no-network",action="store_true"); parser.add_argument("--profile-source",metavar="SOURCE_ID"); parser.add_argument("--backfill-article-images",action="store_true"); parser.add_argument("--image-backfill-limit",type=int,default=100); parser.add_argument("--semantic-probe",action="store_true"); parser.add_argument("--semantic-evaluate",action="store_true"); parser.add_argument("--semantic-calibrate",action="store_true"); parser.add_argument("--semantic-hierarchical-evaluate",action="store_true"); parser.add_argument("--semantic-hierarchical-only",action="store_true"); parser.add_argument("--semantic-hybrid-evaluate",action="store_true"); parser.add_argument("--semantic-phase-23",action="store_true"); parser.add_argument("--semantic-phase-32",action="store_true"); parser.add_argument("--semantic-phase-321",action="store_true"); parser.add_argument("--semantic-phase-33",action="store_true"); parser.add_argument("--scheduler-once",action="store_true"); parser.add_argument("--worker-once",action="store_true"); parser.add_argument("--scheduler",action="store_true"); parser.add_argument("--worker",action="store_true"); parser.add_argument("--worker-batch",action="store_true"); parser.add_argument("--delivery-once",action="store_true"); parser.add_argument("--delivery-worker",action="store_true"); parser.add_argument("--taxonomy-health",action="store_true"); parser.add_argument("--briefing-health",action="store_true"); parser.add_argument("--briefing-diagnostic",metavar="DELIVERY_OR_USER_ID"); args=parser.parse_args()
    if args.profile_source: profile_source(args.profile_source); raise SystemExit(0)
    if args.backfill_article_images:
        print(json.dumps(backfill_article_images(args.image_backfill_limit),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.briefing_health or args.briefing_diagnostic:
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.scheduling import briefing_diagnostic, briefing_health
        repo=ProductRepository()
        result=briefing_health(repo) if args.briefing_health else briefing_diagnostic(repo,args.briefing_diagnostic)
        print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_probe:
        from newzi_engine.llm.probe import run_probe
        print(json.dumps(run_probe(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_evaluate:
        from newzi_engine.semantic.evaluate import run_evaluation
        print(json.dumps(run_evaluation(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_calibrate:
        from newzi_engine.semantic.evaluate import run_calibration
        print(json.dumps(run_calibration(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_hierarchical_evaluate:
        from newzi_engine.semantic.evaluate import run_phase_222
        print(json.dumps(run_phase_222(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_hierarchical_only:
        from newzi_engine.semantic.evaluate import rerun_hierarchical_only
        print(json.dumps(rerun_hierarchical_only(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_hybrid_evaluate:
        from newzi_engine.semantic.evaluate import run_candidate_evaluation, run_hybrid_evaluation, run_verifier_false_split_analysis
        print(json.dumps({"candidates":run_candidate_evaluation(),"hybrid":run_hybrid_evaluation(),"verifier":run_verifier_false_split_analysis()},ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_phase_23:
        from newzi_engine.semantic.phase23 import run_phase_23
        print(json.dumps(run_phase_23(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_phase_32:
        from newzi_engine.semantic.phase32 import run_phase32
        print(json.dumps(run_phase32(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_phase_321:
        from newzi_engine.semantic.quality321 import run_phase321
        print(json.dumps(run_phase321(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.semantic_phase_33:
        from newzi_engine.semantic.phase33 import run_phase33
        print(json.dumps(run_phase33(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.delivery_once:
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.scheduling import BriefingDeliveryWorker
        print(json.dumps(BriefingDeliveryWorker(ProductRepository()).run_once(),ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.scheduler_once or args.worker_once:
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.scheduling import BriefingDeliveryWorker, BriefingScheduler
        repo=ProductRepository(); result=BriefingScheduler(repo).run_once() if args.scheduler_once else BriefingDeliveryWorker(repo).run_once(); print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.delivery_worker:
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.scheduling import BriefingDeliveryWorker
        BriefingDeliveryWorker(ProductRepository()).run_forever(); raise SystemExit(0)
    if args.scheduler or args.worker or args.worker_batch:
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.scheduling import BriefingDeliveryWorker, BriefingScheduler
        repo=ProductRepository()
        if args.scheduler: BriefingScheduler(repo).run_forever()
        elif args.worker: BriefingDeliveryWorker(repo).run_forever()
        else: print(json.dumps(BriefingDeliveryWorker(repo).run_once(),ensure_ascii=False,indent=2))
        raise SystemExit(0)
    if args.taxonomy_health:
        from newzi_backend.product_backend import ProductRepository
        from newzi_backend.content import sync_content, taxonomy_health
        repo=ProductRepository(); index=sync_content(repo); print(json.dumps({"index":index,"coverage":taxonomy_health(repo)},ensure_ascii=False,indent=2)); raise SystemExit(0)
    stats,items=run(args.no_network)
    if args.diagnostics: print(json.dumps(stats,indent=2,ensure_ascii=False)); print("\nTOP EVENTS"); [print(f"{i}. {e.representative_title} â€” {e.relevance_score}/100 ({len(set(e.source_ids))} sources)") for i,e in enumerate(items,1)]

