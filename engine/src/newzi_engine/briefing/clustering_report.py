from pathlib import Path

def write_clustering_report(events, audit, directory=None):
    from ..paths import ENGINE_OUTPUT
    directory = directory or ENGINE_OUTPUT
    path=Path(directory); path.mkdir(parents=True, exist_ok=True); lines=["# NEWS ENGINE â€” CLUSTERING REPORT", "", "## Multi-article clusters", ""]
    multi=[e for e in events if len(e.articles)>1]
    for e in multi:
        lines += [f"### {e.representative_title}", f"Confidence: {e.cluster_confidence}/100", f"Sources: {len(set(e.source_ids))}", ""]
        lines += [f"- {a.source_name}: {a.title}" for a in e.articles]
        if e.merge_audit:
            s=e.merge_audit[-1]; lines += ["", f"Genre: {s.get('genre','UNKNOWN')}", f"Fingerprint A: {s.get('fingerprint_a',{})}", f"Fingerprint B: {s.get('fingerprint_b',{})}", f"Signals: title={s['title_similarity']}, entities={s['entity_overlap']}, distinctive={s['distinctive_overlap']}, temporal={s['temporal_score']}, same_source={s['same_source']}"]
        lines.append("")
    lines += ["## Near misses", ""]
    for item in sorted(audit.get("near_misses", []), key=lambda x:x.get("confidence",0), reverse=True)[:30]:
        reason="OBJECT_CONFLICT" if item.get("conflict") else ("GENRE_INCOMPATIBLE" if item.get("genre_conflict") else ("INSUFFICIENT_EVENT_EVIDENCE" if not item.get("action_agreement") else "DISTINCTIVE_ENTITY_MISMATCH"))
        lines.append(f"- Confidence {item['confidence']} â€” {reason}: {item['article_a']} / {item['article_b']} (title={item['title_similarity']}, entities={item['entity_overlap']}, distinctive={item['distinctive_overlap']}, conflict={item['conflict']})")
    (path/"clustering_report.md").write_text("\n".join(lines), encoding="utf-8")

