"""Event clustering and how composition uses it: one story per event, every outlet credited."""
from datetime import datetime, timedelta, timezone

import support  # noqa: F401  (isolated environment before engine/backend imports)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SETTINGS = {"clustering": {"time_window_hours": 72}}


def story(article_id, source, title, hours_ago=1, description=""):
    from newzi_backend.content import clustering_genre
    from newzi_engine.models import Article
    published = NOW - timedelta(hours=hours_ago)
    article = Article(article_id, source, source.title(), title, description, "https://news.example/" + article_id,
                      "https://news.example/" + article_id, published, published, "en", publisher_id=source)
    article.content_genre = clustering_genre(article)
    return article


def groups(articles):
    from newzi_engine.clustering.events import cluster_articles
    return sorted(sorted(event.article_ids) for event in cluster_articles(articles, SETTINGS))


def test_same_story_from_several_outlets_is_one_event():
    articles = [story("a", "verge", "Google releases Gemini 4 Argon, its most powerful AI model"),
                story("b", "wired", "Google rolls out Gemini 4 Argon, its most advanced AI model"),
                story("c", "engadget", "Google's first Gemini 4 model is Argon")]
    assert groups(articles) == [["a", "b", "c"]]


def test_a_shared_brand_alone_does_not_make_an_event():
    # Real stories from one morning that used to collapse into a single "OpenAI" event.
    articles = [story("ads", "verge_ai", "OpenAI is sticking more ads in ChatGPT",
                      description="OpenAI's latest ad format will put images of sponsored products and services on your screen."),
                story("pr", "verge_ai", "OpenAI PR tells journalist to ‘move on’ while asking Sam Altman about a ChatGPT user’s suicide",
                      description="An OpenAI publicist tried to change the topic of CEO Sam Altman's interview with Vanity Fair."),
                story("wallet", "canaltech", "ChatGPT vai ganhar carteira digital para fazer compras por você",
                      description="O ChatGPT está prestes a ganhar uma carteira digital própria. A opção Wallet começou a aparecer."),
                story("watermark", "canaltech", "ChatGPT copia o Claude e também começa a \"carimbar\" textos feitos por sua IA",
                      description="O ChatGPT vai começar a colocar uma marca-d’água invisível em textos. A OpenAI anunciou o textGrain."),
                story("movie", "canaltech", "Filme sobre criador do ChatGPT é aclamado após Amazon largar projeto por US$ 50 bi",
                      description="As primeiras impressões de Artificial, o novo filme de Luca Guadagnino, já estão circulando.")]
    assert groups(articles) == [["ads"], ["movie"], ["pr"], ["wallet"], ["watermark"]]


def test_a_story_must_fit_the_event_not_only_its_closest_member():
    from newzi_engine.clustering.events import _fits_anchor
    from newzi_engine.clustering.similarity import signal_pair
    launch = story("launch", "verge", "Google releases Gemini 4 Argon model for developers")
    phones = story("phones", "android", "Pixel 11 phones leak with Tensor G6 chip and new cameras")
    assert not _fits_anchor(signal_pair(phones, launch, 72))
    assert _fits_anchor(signal_pair(story("again", "wired", "Gemini 4 Argon model arrives for Google developers"), launch, 72))


def test_coupons_never_form_an_event():
    articles = [story("p1", "wired", "Squarespace Promo Codes: 20% Off in October 2026",
                      description="Get 20% off your next website and more top coupons from WIRED."),
                story("p2", "wired", "Design Within Reach Promo Codes: 30% Off | October 2026",
                      description="Get 30% off, 20% off, and free shipping with our Design Within Reach coupon codes."),
                story("p3", "wired", "Surfshark Promo Codes: 87% Off | October 2026",
                      description="Save up to 87% with a Surfshark coupon code, 3 months of VPN free today.")]
    assert groups(articles) == [["p1"], ["p2"], ["p3"]]


def index(repo, article_id, source, title, event_id=None, hours_ago=1, quality=5.0, topic="TECHNOLOGY", country="US", description="", language="pt-BR"):
    from newzi_backend.timeutil import iso
    published = iso(NOW - timedelta(hours=hours_ago))
    repo.db.execute("""INSERT INTO indexed_content(id,content_hash,title,description,url,source_name,source_id,source_country,source_language,
        published_at,indexed_at,enrichment_mode,quality_score,event_id,image_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (article_id, "h_" + article_id, title, description, "https://news.example/" + article_id, source.title(), source,
                     country, language, published, published, "test", quality, event_id, f"https://news.example/images/{len(article_id)}-{article_id[:2]}.jpg"))
    repo.db.execute("INSERT INTO content_taxonomy(content_id,taxonomy_id,score) VALUES(?,?,?)", (article_id, topic, 8.0))
    repo.db.commit()


def test_compose_tells_each_event_once_and_credits_every_outlet(repo):
    from newzi_backend.content import compose
    index(repo, "verge_gemini", "verge", "Google releases Gemini 4 Argon", event_id="gemini", quality=9.0)
    index(repo, "wired_gemini", "wired", "Google rolls out Gemini 4 Argon", event_id="gemini", quality=7.0)
    index(repo, "wired_gemini_2", "wired", "Gemini 4 Argon: what developers get", event_id="gemini", quality=6.0)
    index(repo, "verge_pixel", "verge", "Pixel 11 leaks with a new chip")
    items = compose(repo, ["TECHNOLOGY"], "en", 10, now=NOW)["items"]
    assert [item["event_id"] for item in items] == ["gemini", "verge_pixel"]       # coverage ranks the event first
    assert [source["article_id"] for source in items[0]["sources"]] == ["verge_gemini", "wired_gemini"]  # one per outlet
    assert len(items[1]["sources"]) == 1


def told_yesterday(repo, profile_key, event_id, article_id, hours_ago=25, manual=False):
    """An earlier briefing of this profile that told ``event_id`` through ``article_id``."""
    import json
    from newzi_backend.timeutil import iso
    edition_id = "edition_" + article_id
    told = iso(NOW - timedelta(hours=hours_ago))
    repo.db.execute("INSERT INTO briefing_editions(id,profile_key,edition_date,language,status,generated_at,item_count,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (edition_id, profile_key + ("_manual_x" if manual else ""), (NOW - timedelta(days=1)).date().isoformat(),
                     "pt-BR", "READY", told, 1, told))
    repo.db.execute("INSERT INTO briefing_edition_items(id,edition_id,position,event_id,sources_json,created_at) VALUES(?,?,?,?,?,?)",
                    ("item_" + article_id, edition_id, 1, event_id, json.dumps([{"article_id": article_id}]), told))
    repo.db.commit()


def sports_briefing(repo):
    from newzi_backend.content import compose
    return compose(repo, ["SPORTS"], "pt-BR", 5, now=NOW, briefing_date=NOW.date().isoformat())["items"]


def sports_profile_key():
    from newzi_backend.scheduling import BriefingProfile
    return BriefingProfile(("SPORTS",), "pt-BR", 5, "BOTH").key()


def test_a_story_told_yesterday_without_news_is_not_told_again(repo):
    index(repo, "preview", "ge", "Botafogo recebe a Chapecoense no Nilton Santos", event_id="bota_chape",
          hours_ago=26, quality=9.0, topic="SPORTS")
    index(repo, "other", "lance", "Seleção é convocada para amistosos", hours_ago=3, topic="SPORTS")
    told_yesterday(repo, sports_profile_key(), "bota_chape", "preview", manual=True)   # onboarding saves are manual editions
    assert [item["event_id"] for item in sports_briefing(repo)] == ["other"]


def test_a_story_told_yesterday_returns_with_its_latest_coverage(repo):
    index(repo, "preview", "ge", "Botafogo recebe a Chapecoense no Nilton Santos", event_id="bota_chape",
          hours_ago=26, quality=9.0, topic="SPORTS")
    index(repo, "result", "lance", "Botafogo vence a Chapecoense por 2 a 0", event_id="bota_chape",
          hours_ago=12, quality=4.0, topic="SPORTS")
    told_yesterday(repo, sports_profile_key(), "bota_chape", "preview")
    items = sports_briefing(repo)
    assert [item["event_id"] for item in items] == ["bota_chape"]
    assert items[0]["headline"] == "Botafogo vence a Chapecoense por 2 a 0" and "EVENT_UPDATE" in items[0]["warnings"]


def test_what_a_user_heard_is_theirs_even_after_changing_topics(repo):
    from newzi_backend.content import compose
    index(repo, "preview", "ge", "Botafogo recebe a Chapecoense no Nilton Santos", event_id="bota_chape", hours_ago=26, topic="SPORTS")
    index(repo, "other", "lance", "Seleção é convocada para amistosos", hours_ago=3, topic="SPORTS")
    told_yesterday(repo, "an_older_profile", "bota_chape", "preview")       # told under the user's old topics
    repo.db.execute("UPDATE briefing_editions SET user_id='reader'"); repo.db.commit()
    briefing = lambda user: [item["event_id"] for item in compose(repo, ["SPORTS"], "pt-BR", 5, now=NOW,
                                                                   briefing_date=NOW.date().isoformat(), user_id=user)["items"]]
    assert briefing("reader") == ["other"]
    assert briefing("someone_else") == ["other", "bota_chape"]                # another user never heard it


def test_an_event_leads_with_its_newest_coverage(repo):
    index(repo, "preview", "ge", "Botafogo recebe a Chapecoense no Nilton Santos", event_id="bota_chape", hours_ago=14, quality=9.0, topic="SPORTS")
    index(repo, "result", "lance", "Botafogo vence a Chapecoense por 2 a 0", event_id="bota_chape", hours_ago=8, quality=4.0, topic="SPORTS")
    assert sports_briefing(repo)[0]["sources"][0]["article_id"] == "result"


def test_a_preview_overtaken_by_the_result_is_left_out(repo):
    # Real Sunday case: the live-coverage piece led the briefing while the result sat in other events.
    index(repo, "live", "gazeta", "Botafogo x Chapecoense: siga o tempo real do jogo pelo Campeonato Brasileiro",
          event_id="live", hours_ago=12.5, quality=9.0, topic="SPORTS")
    index(repo, "watch", "metropoles", "Botafogo x Chapecoense: onde assistir ao jogo pelo Campeonato Brasileiro",
          event_id="live", hours_ago=12.5, quality=9.0, topic="SPORTS")
    index(repo, "result", "metropoles", "Tiquinho marca no início, Botafogo vence a Chapecoense e se afasta do Z4",
          hours_ago=10.5, quality=4.0, topic="SPORTS")
    index(repo, "next", "ge", "Escalação do Bahia contra o Flamengo: time provável e dúvidas", hours_ago=6, topic="SPORTS")
    index(repo, "news", "lance", "Flamengo tem desfalque de última hora para enfrentar o Bahia", hours_ago=2, topic="SPORTS")
    # The coming match stays: newer news naming both teams is not its result.
    assert {item["event_id"] for item in sports_briefing(repo)} == {"result", "next", "news"}


def test_a_headline_framed_for_a_past_day_is_left_out(repo):
    from newzi_backend.content import anticipated_day
    from datetime import date
    saturday = date(2026, 10, 17)
    assert anticipated_day("Primeiro campeonato estadual de 2027 começa neste sábado; entenda", saturday) == saturday
    assert anticipated_day("Unifacisa e Osasco medem forças nesta segunda pelo NBB", saturday) == date(2026, 10, 19)
    assert anticipated_day("Final será amanhã no Maracanã", saturday) == date(2026, 10, 18)
    assert anticipated_day("Botafogo vence a Chapecoense", saturday) is None
    index(repo, "yesterday", "ge", "Campeonato estadual começa hoje com quatro jogos", hours_ago=30, topic="SPORTS")
    index(repo, "fresh", "lance", "Seleção é convocada para amistosos", hours_ago=2, topic="SPORTS")
    assert [item["event_id"] for item in sports_briefing(repo)] == ["fresh"]


POPE = [("missa", "vatican", "Papa Leão XIV celebra missa no hospital após cirurgia para retirar câncer do pulmão", 40,
         "O pontífice segue internado no Gemelli."),
        ("alta1", "folha", "Papa Leão XIV recebe alta após cirurgia para tratar câncer de pulmão", 24, ""),
        ("alta2", "g1", "Papa Leão 14 recebe alta do hospital, podendo voltar ao Vaticano", 21, ""),
        ("alta3", "uol", "Papa recebe alta do hospital depois de cirurgia para remover câncer no pulmão", 9,
         "O papa Leão XIV deixou o Gemelli neste sábado.")]


def index_pope(repo, stories=POPE):
    for article_id, source, title, hours, description in stories:   # clustering left each in its own event, as in production
        index(repo, article_id, source, title, event_id=article_id, hours_ago=hours, topic="WORLD", description=description)
    index(repo, "other", "bbc", "Terremoto atinge o Japão e deixa feridos", hours_ago=3, topic="WORLD")


def world_briefing(repo, user_id=None):
    from newzi_backend.content import compose
    return compose(repo, ["WORLD"], "pt-BR", 5, now=NOW, briefing_date=NOW.date().isoformat(), user_id=user_id)["items"]


def test_one_story_split_across_events_is_told_once_through_its_latest_state(repo):
    index_pope(repo)
    items = world_briefing(repo)
    pope = [item for item in items if "Papa" in item["headline"]]
    assert len(pope) == 1 and pope[0]["headline"] == "Papa recebe alta do hospital depois de cirurgia para remover câncer no pulmão"
    assert len(items) == 2


def test_a_story_told_while_ongoing_returns_with_its_update(repo):
    index_pope(repo)
    told_yesterday(repo, "any_profile", "missa", "missa", hours_ago=30)   # "still in hospital" was told
    repo.db.execute("UPDATE briefing_editions SET user_id='reader'"); repo.db.commit()
    pope = [item for item in world_briefing(repo, "reader") if "Papa" in item["headline"]]
    assert [item["headline"] for item in pope] == ["Papa recebe alta do hospital depois de cirurgia para remover câncer no pulmão"]
    assert "EVENT_UPDATE" in pope[0]["warnings"]


def test_different_stories_about_the_same_people_stay_apart():
    from newzi_backend.threads import story_threads
    titles = ["Qual foi a diferença de votos entre Lula e Flávio Bolsonaro no primeiro turno?",
              "Nova pesquisa: Flávio Bolsonaro e Lula empatam com 50% no segundo turno das eleições",
              "Economia: Lula e Flávio divergem sobre ajuste fiscal e papel do Estado",
              "Flávio Bolsonaro defende aumentar segurança e diz que fará de tudo para o pobre",
              "Coligação de Lula aciona PGE e PF para apurar supostas vantagens da Meta à campanha",
              "A crise global que Flávio Bolsonaro ou Lula terão de enfrentar se eleitos",
              "Lula compara fim da 6x1 com Constituinte e fala em vitória da sociedade",
              "Lula e Flávio Bolsonaro trocam ataques em debate na televisão",
              "Flávio Bolsonaro visita o Nordeste em campanha pelo segundo turno",
              "Lula grava programa eleitoral com aliados no segundo turno"]
    filler = [f"Notícia número {n} sobre assunto {n} da cidade {n}" for n in range(40)]
    contents = [{"id": f"s{n}", "title": title, "published_at": f"2026-10-17T{n % 24:02d}:00:00.000Z", "event_id": None}
                for n, title in enumerate(titles + filler)]
    threads = story_threads(contents)
    assert len({threads[f"s{n}"] for n in range(len(titles))}) == len(titles)


def test_an_outlets_headline_template_is_not_a_story():
    from newzi_backend.threads import story_threads
    rows = [("Melhores momentos: Hamburg 1 x 0 Stuttgart pelo Alemão", "ge"),
            ("Melhores momentos: Union Berlin 0 x 0 Dortmund pelo Alemão", "ge"),
            ("Melhores momentos: Schalke 0 x 1 Mainz pelo Alemão", "ge"),
            ("Melhores momentos: Elversberg 4 x 3 Augsburg pelo Alemão", "ge"),
            ("Remo x Bragantino - Campeonato Brasileiro 2026 - globoesporte.com", "ge"),
            ("Vila Nova x Novorizontino - Campeonato Brasileiro Série B 2026 - globoesporte.com", "ge"),
            ("Cruzeiro x Bolívar - Taça Libertadores Feminina 2026 - globoesporte.com", "ge"),
            ("Leeds United x Manchester United - Campeonato Inglês 2026/27 - globoesporte.com", "ge"),
            # One outlet covering a story heavily is not a template: its headlines keep naming the pope.
            ("Papa Leão XIV celebra missa no hospital após cirurgia para retirar câncer do pulmão", "folha"),
            ("Papa Leão XIV recebe alta após cirurgia para tratar câncer de pulmão", "folha"),
            ("Papa Leão 14 recebe alta do hospital, podendo voltar ao Vaticano", "folha"),
            ("Papa Leão XIV deixa hospital após cirurgia de câncer no pulmão", "folha")]
    contents = [{"id": f"s{n}", "title": title, "source_id": source, "published_at": f"2026-10-17T{n:02d}:00:00.000Z", "event_id": None}
                for n, (title, source) in enumerate(rows)]
    threads = story_threads(contents)
    assert len({threads[f"s{n}"] for n in range(8)}) == 8
    assert len({threads[f"s{n}"] for n in range(8, 12)}) == 1


def test_common_names_and_templated_descriptions_do_not_join_stories():
    from newzi_backend.threads import story_threads
    rows = [("Atuações da Ponte: Da Hora marca, mas defesa não resiste à pressão; dê suas notas", "ge",
             "Confira as notas dos jogadores da Ponte na derrota pelo Brasileirão."),
            ("Atuações do Mirassol: André Luís e Eduardo garantem vitória; dê suas notas", "ge",
             "Confira as notas dos jogadores do Mirassol na vitória pelo Brasileirão."),
            ("Atuações do Botafogo: Tiquinho é o melhor em vitória sobre a Chapecoense; dê suas notas", "ge",
             "Confira as notas dos jogadores do Botafogo na vitória pelo Brasileirão."),
            ("Atuações: Lucas muda o jogo e é o melhor em vitória do São Paulo; dê suas notas", "ge",
             "Confira as notas dos jogadores do São Paulo na vitória pelo Brasileirão."),
            ("Atuações do Vasco: Puma e Tchê Tchê são os piores em derrota; dê suas notas", "ge",
             "Confira as notas dos jogadores do Vasco na derrota pelo Brasileirão."),
            ("Eleições nos EUA: democratas superam republicanos na arrecadação de fundos", "g1", ""),
            ("Déficit das contas públicas dos EUA sobe a US$ 1,99 trilhão, maior em 5 anos", "g1", "")]
    filler = [(f"Prefeitura dos EUA anuncia obra número {n}", f"site{n}", "") for n in range(10)]   # "EUA" is common
    contents = [{"id": f"s{n}", "title": title, "source_id": source, "description": description,
                 "published_at": f"2026-10-17T{n % 24:02d}:00:00.000Z", "event_id": None}
                for n, (title, source, description) in enumerate(rows + filler)]
    threads = story_threads(contents)
    assert len({threads[f"s{n}"] for n in range(len(rows))}) == len(rows)


def test_threads_follow_headlines_not_background_in_descriptions():
    # Production cases: g1 described the pope's call with Putin with his hospital stay, and one
    # outlet's several pope headlines must still join another outlet's "Papa recebe alta".
    from newzi_backend.threads import story_threads
    stay = "Papa Leão XIV celebrou missa dentro do hospital Gemelli após cirurgia para retirar tumor no pulmão."
    rows = [("Vaticano divulga primeiras FOTOS de papa Leão XIV após cirurgia para retirada de câncer", "g1", stay),
            ("Papa fala ao telefone com Putin, oferece mediação na guerra e pede corredor humanitário", "g1", stay),
            ("Papa Leão 14 recebe alta do hospital, podendo voltar ao Vaticano", "dw", ""),
            ("Papa Leão 14 tem alta hospitalar e volta ao Vaticano", "dw", ""),
            ("Papa Leão 14 tem alta após cirurgia para tratar câncer", "dw", ""),
            ("Papa Leão 14 deixa o Gemelli após cirurgia no pulmão", "dw", ""),
            ("Papa recebe alta do hospital depois de cirurgia para remover câncer no pulmão", "g1", "")]
    contents = [{"id": f"s{n}", "title": title, "source_id": source, "description": description,
                 "published_at": f"2026-10-17T{n:02d}:00:00.000Z", "event_id": None}
                for n, (title, source, description) in enumerate(rows)]
    threads = story_threads(contents)
    assert threads["s1"] != threads["s0"]                                         # Putin is another story
    assert len({threads[f"s{n}"] for n in (0, 2, 3, 4, 5, 6)}) == 1                # one pope's-health story


CLASSIFIED_HEADLINES = [
    # (headline, the feed's own categories, expected primary topic, topics it must not get) — real
    # production headlines that used to land in the wrong topic.
    ("Criança de 2 anos é baleada dentro de casa após ataque a tiros em Coruripe, AL", ["brazil"],
     "SEGURANCA_PUBLICA", {"CONFLITOS_INTERNACIONAIS", "DEFESA"}),
    ("Motociclista morre após bater em árvore na Avenida Jerônimo de Albuquerque, em São Luís", ["brazil"],
     "SEGURANCA_PUBLICA", {"DEFESA"}),
    ("Xiaomi libera pacote de segurança de outubro para 15 dispositivos; confira a lista", ["technology"],
     "TECHNOLOGY", {"SEGURANCA_PUBLICA"}),
    ("Manifestantes fazem ato pró-Lula em BH", ["brazil"], "POLITICS", set()),
    ("Deputada Erika Hilton critica plataformas por notícias falsas", ["business"], "POLITICS", {"BUSINESS"}),
    ("Cebola com chocolate? Aí está o segredo do bombom que virou atração em SC", ["brazil"],
     None, {"ARTIFICIAL_INTELLIGENCE"}),
    ("Paris residents tell Al Jazeera they’re dismayed by protest damage", ["world"], None, {"JUSTICA_BRASILEIRA"}),
    ("Papa Leão conduz oração no Vaticano após cirurgia e diz que retomará trabalho aos poucos", ["world"],
     "HEALTH", {"MERCADO_DE_TRABALHO"}),
    ("Rebaixado, América-MG vence e complica Operário-PR na briga por acesso na Série B", ["sports"],
     "FUTEBOL", set()),
    ("Bolsa Família com reajuste começa a ser pago amanhã; confira o calendário", ["economy"],
     "POLITICAS_PUBLICAS", {"FINANCE"}),
    ("Áudio: Dia Nacional da Vacinação é comemorado neste sábado", ["politics"], None, {"CONGRESSO_NACIONAL"}),
    ("Nottingham Forest x Arsenal: onde assistir ao vivo, horário e transmissão", ["politics", "brazil"],
     "FUTEBOL_INTERNACIONAL", {"POLITICS"}),
    ("Ajax x PSV: onde assistir ao vivo, horário e transmissão", ["politics", "brazil"], "SPORTS", {"POLITICS"}),
    ("Britain's Kartal misses out on maiden WTA 1000 title in Wuhan", ["sports"], "TENIS", set()),
    ("NFL London LIVE! Jaguars face rival Texans at Wembley", ["world"], "SPORTS", set()),
    ("Community starts up GoFundMe for 7-year-old Oregon school shooting survivor", ["world"], None, {"EDUCATION", "ESCOLAS"}),
    ("A “tempestade perfeita” no acesso dos jovens à habitação", ["world"], None, {"METEOROLOGIA"}),
    ("Croácia: Euronews faz primeira viagem em robotáxi sem condutor da Europa", ["world"], "TECHNOLOGY", {"TURISMO"}),
    ("Paris tem carros queimados e vidros estilhaçados após protestos se transformarem em tumulto", ["world"],
     None, {"AUTOMOVEIS"}),
]


def test_a_passing_mention_in_the_description_is_not_a_second_topic():
    from types import SimpleNamespace
    from newzi_engine.processors.classify import classify_for_index
    article = SimpleNamespace(title="Mega-Sena sorteia R$ 170 milhões acumulados neste domingo",
                              description="As apostas podem ser feitas nas lotéricas, pelo aplicativo ou pela internet.",
                              source_tags=["brazil"], categories=[])
    result = classify_for_index(article, ["brazil"])
    assert result["primary"] == "SOCIEDADE_BRASILEIRA"
    assert "TECHNOLOGY" not in {tag for tag, _ in result["tags"]}


def test_an_unclassified_article_takes_the_topics_of_its_story(repo):
    from newzi_backend.content import compose
    index(repo, "ge_match", "ge", "Real Madrid x Sevilla em LaLiga: onde assistir", event_id="match", topic="FUTEBOL")
    index(repo, "jp_match", "jovem_pan", "Real Madrid x Sevilla: onde assistir ao vivo", event_id="match", topic="POLITICS",
          hours_ago=0.5)
    repo.db.execute("UPDATE indexed_content SET classification_reason=? WHERE id=?", ("CLASSIFIED", "ge_match"))
    repo.db.execute("UPDATE indexed_content SET classification_reason=? WHERE id=?", ("NO_SIGNAL_FALLBACK", "jp_match"))
    index(repo, "senado", "folha", "Senado aprova reforma do setor elétrico", topic="POLITICS")
    repo.db.commit()
    items = compose(repo, ["POLITICS"], "pt-BR", 5, now=NOW, briefing_date=NOW.date().isoformat())["items"]
    match = [item for item in items if "Sevilla" in item["headline"]]
    assert not any(item["user_interest_matches"] for item in match)


def test_a_weak_secondary_topic_does_not_reach_a_reader(repo):
    from newzi_backend.content import compose
    index(repo, "lottery", "g1", "Mega-Sena sorteia R$ 170 milhões neste domingo", topic="SOCIEDADE_BRASILEIRA")
    repo.db.execute("UPDATE content_taxonomy SET score=14 WHERE content_id='lottery'")
    repo.db.execute("INSERT INTO content_taxonomy(content_id,taxonomy_id,score) VALUES('lottery','TECHNOLOGY',5)")
    index(repo, "chip", "verge", "Nvidia lança novo chip para data centers", topic="TECHNOLOGY")
    repo.db.commit()
    items = compose(repo, ["TECHNOLOGY"], "pt-BR", 5, now=NOW, briefing_date=NOW.date().isoformat())["items"]
    lottery = [item for item in items if "Mega-Sena" in item["headline"]]
    assert not any(item["user_interest_matches"] for item in lottery)
    assert any(item["user_interest_matches"] for item in items if "Nvidia" in item["headline"])


def test_headlines_land_in_their_topic():
    from types import SimpleNamespace
    from newzi_engine.processors.classify import classify_for_index
    for title, categories, expected, forbidden in CLASSIFIED_HEADLINES:
        result = classify_for_index(SimpleNamespace(title=title, description="", source_tags=categories, categories=[]), categories)
        tags = {tag for tag, _ in result["tags"]}
        assert expected is None or result["primary"] == expected, (title, result["primary"])
        assert not tags & forbidden, (title, tags & forbidden)


def test_old_stories_never_fill_a_briefing(repo):
    index(repo, "old", "ge", "Botafogo anuncia novo técnico", hours_ago=24 * 5, topic="SPORTS")
    index(repo, "recent", "lance", "Seleção é convocada para amistosos", hours_ago=30, topic="SPORTS")
    assert [item["event_id"] for item in sports_briefing(repo)] == ["recent"]


def test_recluster_splits_an_over_merged_event(repo):
    from newzi_backend.content import recluster_content
    index(repo, "g1", "verge", "Google releases Gemini 4 Argon, its most powerful AI model", event_id="blob")
    index(repo, "g2", "wired", "Google rolls out Gemini 4 Argon, its most advanced AI model", event_id="blob")
    index(repo, "m1", "folha", "Filme sobre criador do ChatGPT é aclamado após Amazon largar projeto", event_id="blob")
    recluster_content(repo)
    event = {row["id"]: row["event_id"] for row in repo.db.execute("SELECT id,event_id FROM indexed_content")}
    assert event["g1"] == event["g2"] != event["m1"] and "blob" not in event.values()


def test_a_cycle_places_only_its_changed_stories(repo):
    """Settled stories keep their events, as stored; a late story still joins one published after it."""
    from newzi_engine.clustering.events import cluster_articles
    articles = [story("late", "engadget", "Google's first Gemini 4 model is Argon", hours_ago=5),
                story("g1", "verge", "Google releases Gemini 4 Argon, its most powerful AI model", hours_ago=2),
                story("g2", "wired", "Google rolls out Gemini 4 Argon, its most advanced AI model", hours_ago=1),
                story("m1", "folha", "Filme sobre criador do ChatGPT é aclamado após Amazon largar projeto", hours_ago=1)]
    seeds = {"g1": "gemini", "g2": "gemini", "m1": "gemini"}   # an over-merge a cycle must not redo
    events, audit = cluster_articles(articles, SETTINGS, diagnostics=True, focus_ids={"late"}, seed_events=seeds)
    assert {event.event_id: sorted(event.article_ids) for event in events} == {"gemini": ["g1", "g2", "late", "m1"]}
    assert audit["metrics"]["articles_placed"] == 1


def test_a_cycle_prepares_each_story_once_with_the_same_events(repo):
    """One news cycle clusters overlapping windows; a story's fingerprint is reused while its text is the same."""
    from newzi_engine.clustering import events as clustering
    stories = lambda: [story("g1", "verge", "Google releases Gemini 4 Argon, its most powerful AI model", hours_ago=3),
                       story("g2", "wired", "Google rolls out Gemini 4 Argon, its most advanced AI model", hours_ago=2),
                       story("a1", "engadget", "Apple unveils the iPhone 18 Pro with a new camera", hours_ago=2),
                       story("a2", "verge", "Apple iPhone 18 Pro unveiled with new camera system", hours_ago=1),
                       story("m1", "folha", "Filme sobre criador do ChatGPT é aclamado após Amazon largar projeto", hours_ago=1)]
    windows = lambda articles: [articles[:4], articles[1:]]
    expected = [groups(window) for window in windows(stories())]
    prepared, calls = {}, []
    original = clustering.prepare_similarity_features
    clustering.prepare_similarity_features = lambda article: calls.append(article.article_id) or original(article)
    try:
        got = [sorted(sorted(event.article_ids) for event in clustering.cluster_articles(window, SETTINGS, prepared=prepared))
               for window in windows(stories())]
        assert got == expected and sorted(calls) == ["a1", "a2", "g1", "g2", "m1"]      # each story once
        # A story whose text changed is prepared again.
        changed = stories(); changed[0].title = "Google delays Gemini 4 Argon"
        calls.clear()
        clustering.cluster_articles(changed[:4], SETTINGS, prepared=prepared)
        assert calls == ["g1"]
    finally:
        clustering.prepare_similarity_features = original


def test_headlines_need_min_shared_uncommon_words_to_resemble_each_other():
    """story_threads skips threads sharing fewer uncommon words with a story; that is only safe while
    _similarity is zero for every such pair, which this checks for each way a pair can qualify."""
    from itertools import combinations
    from newzi_backend.threads import MIN_SHARED_UNCOMMON, _similarity
    pool = ["lula", "papa", "alta", "cirurg", "cancer", "pulmao", "hospit", "vatica"]
    weight = {word: 1.0 for word in pool}
    for names in (frozenset(), frozenset({"lula"}), frozenset({"lula", "papa"})):
        for size in range(len(pool) + 1):
            for shared in combinations(pool, size):
                a = frozenset(shared) | {"extraa"}; b = frozenset(shared) | {"extrab"}
                if _similarity(a, b, {**weight, "extraa": 1.0, "extrab": 1.0}, names, frozenset(pool)) > 0:
                    assert len(shared) >= MIN_SHARED_UNCOMMON


def test_tokens_hands_out_a_set_of_its_own():
    from newzi_engine.utils.text import tokens
    first = tokens("Google releases Gemini 4 Argon")
    first.add("changed")
    assert "changed" not in tokens("Google releases Gemini 4 Argon")


def test_stories_stored_outside_the_worker_still_reach_the_index(repo):
    from newzi_backend.content import sync_content_incremental
    from newzi_engine.storage import Store
    sync_content_incremental(repo, [])      # first sync: full rebuild, records the index version
    collected = story("cli_story", "verge", "Google releases Gemini 4 Argon, its most powerful AI model")
    Store().upsert_articles([collected])      # e.g. `engine/main.py` run by hand: stored, never indexed
    metrics = sync_content_incremental(repo, [])
    assert metrics["reconciled_articles"] == 1
    assert repo.db.execute("SELECT event_id FROM indexed_content WHERE id='cli_story'").fetchone()["event_id"]
    assert sync_content_incremental(repo, [])["reconciled_articles"] == 0


def test_source_health_names_what_is_wrong_with_each_feed(repo):
    import json
    from newzi_backend.source_health import source_health_report
    from newzi_engine.collectors.registry import load_sources
    from newzi_engine.storage import Store
    broken, abandoned, healthy = (source["id"] for source in load_sources()[:3])
    store = Store()
    for _ in range(3):
        store.save_source_result(broken, {"status": "FAILED", "http_status": 404}, error="404 Not Found")
    store.save_source_result(abandoned, {"status": "SUCCESS", "http_status": 200, "feed_items": 73, "items_too_old": 73,
                                         "feed_newest_item": "2023-01-10T01:39:00+00:00"})
    store.save_source_result(abandoned, {"status": "NOT_MODIFIED", "http_status": 304})   # a 304 keeps the diagnosis
    store.save_source_result(healthy, {"status": "SUCCESS", "http_status": 200, "feed_items": 5, "items_too_old": 0})
    index(repo, "fresh", healthy, "A story published an hour ago")
    report = source_health_report(repo, store=store)
    by_id = {row["id"]: row for row in report["sources"]}
    assert (by_id[broken]["status"], by_id[broken]["diagnosis"]) == ("BROKEN", "FEED_URL_NOT_FOUND")
    assert (by_id[abandoned]["status"], by_id[abandoned]["diagnosis"]) == ("SILENT", "FEED_ABANDONED")
    assert by_id[abandoned]["feed_newest_item"].startswith("2023-01-10")
    assert (by_id[healthy]["status"], by_id[healthy]["articles_24h"]) == ("OK", 1)
    assert report["status"] == "degraded" and report["sources"][0]["id"] == broken
    assert "404" in json.dumps(by_id[broken])


def test_a_new_feed_url_is_fetched_without_the_old_url_state(repo, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from newzi_backend import scheduling
    from newzi_engine.storage import Store
    scheduling._engine_collect_sources(); engine_main = scheduling._ENGINE_MAIN
    source = {"id": "moved", "name": "Moved", "feed_url": "https://new.example/feed", "categories": []}
    store = Store()
    for _ in range(3):   # the old address failed: circuit open, plus a cache validator from it
        store.save_source_result("moved", {"status": "FAILED", "http_status": 404}, {"etag": "old"}, error="404", feed_url="https://old.example/rss")
    assert datetime.fromisoformat(store.get_source_health()["moved"]["circuit_open_until"]) > datetime.now(timezone.utc) + timedelta(minutes=1)
    calls = []

    class Collector:
        def __init__(self, settings): self.last_metrics = {"status": "SUCCESS", "http_status": 200}; self.validators = {}
        def collect(self, src, validators=None): calls.append(validators); return [], None
    monkeypatch.setattr(engine_main, "load_sources", lambda: [source])
    monkeypatch.setattr(engine_main, "RSSCollector", Collector)
    monkeypatch.setattr(engine_main, "enrich_missing_images", lambda *a, **k: {"updated_articles": []})
    engine_main.collect_sources(incremental=True)
    assert calls == [{"etag": None, "last_modified": None}]          # fetched, and without the old ETag
    health = store.get_source_health()["moved"]
    assert health["consecutive_failures"] == 0 and '"feed_url": "https://new.example/feed"' in health["last_metrics_json"]


def test_news_items_and_single_stories_credit_every_outlet(repo):
    from conftest import add_user
    add_user(repo, "reader")
    index(repo, "verge_gemini", "verge", "Google releases Gemini 4 Argon", event_id="gemini", quality=9.0)
    index(repo, "wired_gemini", "wired", "Google rolls out Gemini 4 Argon", event_id="gemini", quality=7.0)
    index(repo, "wired_gemini_2", "wired", "Gemini 4 Argon: what developers get", event_id="gemini", quality=6.0)
    index(repo, "verge_pixel", "verge", "Pixel 11 leaks with a new chip")
    listed = {item["id"]: item for item in repo.latest_news("reader", 10)}
    gemini = next(item for item in listed.values() if item["id"] in ("verge_gemini", "wired_gemini", "wired_gemini_2"))
    assert sorted(source["publisher"] for source in gemini["sources"]) == ["Verge", "Wired"]
    assert len(listed["verge_pixel"]["sources"]) == 1
    story = repo.story("reader", "wired_gemini_2")
    assert story["headline"] == "Gemini 4 Argon: what developers get" and story["primary_taxonomy_id"] == "TECHNOLOGY"
    assert [source["article_id"] for source in story["sources"]] == ["wired_gemini_2", "verge_gemini"]
    assert repo.story("reader", "missing") is None


def test_following_everything_gives_every_domain_a_place(repo):
    from newzi_backend.content import compose
    from newzi_backend.scheduling import BriefingProfile
    from newzi_engine.topic_registry import taxonomy
    for n in range(5):   # one busy domain used to fill the whole briefing
        index(repo, f"tech{n}", f"outlet{n}", f"Technology story number {n}", quality=9.0)
    index(repo, "sport", "espn", "Final do campeonato termina nos pênaltis", topic="SPORTS")
    index(repo, "health", "fiocruz", "Nova vacina contra a dengue é aprovada", topic="HEALTH")
    profile = BriefingProfile.from_preferences({"content_scope": "all", "topics": [], "language": "pt-BR", "briefing_size": 3, "country_scope": "BOTH"})
    assert profile.topics == tuple(taxonomy().roots()) and "SPORTS" in profile.topics
    items = compose(repo, profile.topics, profile.language, profile.briefing_size, now=NOW)["items"]
    assert {"sport", "health"} <= {item["sources"][0]["article_id"] for item in items}


def test_trending_ranks_what_many_outlets_cover_now(repo):
    from conftest import add_user
    from newzi_backend.trending import trending_events, trending_stories
    for n, hours in enumerate((0.5, 1, 1.5, 2)):          # four outlets in the last two hours
        index(repo, f"now{n}", f"outlet{n}", "Terremoto atinge capital e deixa feridos", event_id="quake", hours_ago=hours)
    for n, hours in enumerate((9, 10, 11)):               # three outlets, but most of a day ago
        index(repo, f"old{n}", f"paper{n}", "Governo anuncia pacote de obras", event_id="works", hours_ago=hours, country="BR")
    for n in range(2):                                     # two outlets only: not trending
        index(repo, f"small{n}", f"site{n}", "Prefeitura inaugura praça", event_id="square")
    for n in range(4):                                     # widely covered, but a deal
        index(repo, f"deal{n}", f"shop{n}", "As melhores ofertas de celular do dia", event_id="deals")
    events = trending_events(repo, now=NOW)
    assert [event["event_id"] for event in events] == ["quake", "works"] and events[0]["outlets"] == 4
    assert [event["event_id"] for event in trending_events(repo, "LOCAL", now=NOW)] == ["works"]   # Brazil only
    add_user(repo, "reader", topics=("SPORTS",))           # trending ignores the user's topics
    items = trending_stories(repo, "reader", now=NOW)
    assert items[0]["trending"] == {"rank": 1, "outlets": 4} and len(items[0]["sources"]) == 4


def test_football_overview_cache_and_audience(monkeypatch):
    from datetime import datetime, timezone
    from newzi_backend import football
    calls = []
    team = lambda name: {"shortName": name}
    bsa, cli, pl = {"code": "BSA"}, {"code": "CLI"}, {"code": "PL", "name": "Premier League"}
    now = datetime(2026, 10, 14, 22, 30, tzinfo=timezone.utc)

    def fetch(path, params=None):
        calls.append(path)
        if path.endswith("/standings"):
            return {"season": {"currentMatchday": 30}, "standings": [{"type": "HOME", "table": [{"position": 9}]}, {"type": "TOTAL", "table": [
                {"position": 1, "team": {"shortName": "Palmeiras", "tla": "PAL"}, "points": 61, "playedGames": 29, "won": 19, "draw": 4, "lost": 6, "goalDifference": 25},
                {"position": 2, "team": team("Flamengo"), "points": 58, "playedGames": 29}]}]}
        return {"matches": [   # provider order is not chronological
            {"id": 4, "utcDate": "2026-10-18T21:30:00Z", "status": "TIMED", "competition": bsa, "homeTeam": team("Flamengo"), "awayTeam": team("Corinthians"), "score": {"fullTime": {}}},
            {"id": 5, "utcDate": "2026-10-15T00:30:00Z", "status": "SCHEDULED", "competition": cli, "homeTeam": team("Fluminense"), "awayTeam": team("Palmeiras"), "score": {"fullTime": {}}},
            {"id": 1, "utcDate": "2026-10-14T19:00:00Z", "status": "FINISHED", "competition": pl, "homeTeam": team("Arsenal"), "awayTeam": team("Spurs"), "score": {"fullTime": {"home": 2, "away": 1}}},
            {"id": 2, "utcDate": "2026-10-13T19:00:00Z", "status": "TIMED", "competition": pl, "homeTeam": team("Leeds"), "awayTeam": team("Everton"), "score": {"fullTime": {}}},
            {"id": 3, "utcDate": "2026-10-14T22:00:00Z", "status": "IN_PLAY", "competition": bsa, "homeTeam": team("Grêmio"), "awayTeam": team("Inter"), "score": {"fullTime": {"home": 1, "away": 1}}}]}
    clock = [0.0]
    service = football.FootballService(fetch=fetch, clock=lambda: clock[0])
    overview = service.overview(now=now)
    assert calls == ["/matches"] and [m["home"] for m in overview["live"]] == ["Grêmio"]
    assert overview["live"][0]["home_tla"] == "GRÊ" and overview["live"][0]["competition"] == {"code": "BSA", "name": "Brasileirão"}
    # Soonest first, every competition; finished games and a stale "scheduled" one from yesterday are left out.
    assert [m["id"] for m in overview["upcoming"]] == [5, 4] and overview["upcoming"][0]["competition"]["name"] == "Libertadores"
    assert [(c["code"], c["table"]) for c in overview["competitions"]] == [("BSA", True), ("CLI", False)]
    service.overview(now=now); assert len(calls) == 1                   # cached
    clock[0] = 61.0
    service.overview(now=now); assert len(calls) == 2                   # a live game refreshes every minute

    table = service.standings("BSA")
    assert table["matchday"] == 30 and table["competition"] == {"code": "BSA", "name": "Brasileirão"} and len(table["groups"]) == 1
    assert table["groups"][0]["name"] is None and table["groups"][0]["rows"][0] == {
        "position": 1, "team": "Palmeiras", "team_id": None, "tla": "PAL", "crest": None, "played": 29, "won": 19, "draw": 4, "lost": 6,
        "goal_difference": 25, "points": 61, "form": [], "zone": "libertadores"}
    assert football._group_name("GROUP_B") == "Grupo B"
    clock[0] = 4000.0
    service.fetch = lambda path, params=None: (_ for _ in ()).throw(ConnectionError("down"))
    assert service.standings("BSA")["groups"][0]["rows"][0]["team"] == "Palmeiras"   # stale but served when the provider fails
    assert service.overview(now=now)["upcoming"][0]["id"] == 5

    assert football.follows_football({"topics": ["BRASILEIRAO"]}) and football.follows_football({"topics": ["SPORTS"]})
    assert football.follows_football({"content_scope": "all", "topics": []})
    assert not football.follows_football({"topics": ["FORMULA_1", "TECHNOLOGY"]})
    monkeypatch.delenv("FOOTBALL_DATA_TOKEN", raising=False)
    assert football.football_for({"topics": ["FUTEBOL"]}) == {"available": False, "reason": "NOT_CONFIGURED"}
    monkeypatch.setenv("FOOTBALL_DATA_TOKEN", "test-key")
    assert football.football_for({"topics": ["TECHNOLOGY"]}) == {"available": False, "reason": "NOT_FOLLOWED"}
    monkeypatch.setattr(football, "_service", service)
    assert football.football_for({"topics": ["TECHNOLOGY"]}, require_follow=False)["available"]   # Explore: everyone
    assert football.football_standings("bsa")["available"] and football.football_standings("XYZ")["reason"] == "UNKNOWN_COMPETITION"


def test_trending_stories_join_latest_news_with_their_flag():
    from newzi_backend.product_backend import with_trending
    story = lambda sid, hour, *others: {"id": sid, "headline": sid, "published_at": f"2026-10-15T{hour:02d}:00:00.000Z",
                                        "sources": [{"article_id": sid}, *({"article_id": other} for other in others)]}
    latest = [story("tech1", 20), story("verge_quake", 19), story("tech2", 17)]
    trending = [{**story("g1_quake", 19, "verge_quake"), "trending": {"rank": 1, "outlets": 4}},
                {**story("ge_final", 18, "espn_final"), "trending": {"rank": 2, "outlets": 3}}]
    merged = with_trending(latest, trending)
    # No duplicate quake story, and an older trending story does not jump above newer news.
    assert [item["id"] for item in merged] == ["tech1", "verge_quake", "ge_final", "tech2"]
    assert merged[1]["trending"] == {"rank": 1, "outlets": 4} and "trending" not in merged[0]


def test_subscription_plans_and_access(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from newzi_backend.product_backend import ProductRepository
    from newzi_backend.subscriptions import subscription_for
    repo = ProductRepository(tmp_path / "product.db")
    uid = repo.create_dev_user()["id"]
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("PREMIUM_ENFORCED", raising=False)
    basic = subscription_for(repo, uid, now)
    assert basic["tier"] == "basic" and basic["limits"]["briefing_times"] == 1 and basic["limits"]["favorite_teams"] == 1 and not basic["purchases_enabled"]
    assert [plan["id"] for plan in basic["plans"]] == ["annual", "monthly"] and not basic["will_renew"]
    # Until purchases work the limits are not enforced: everyone keeps every feature.
    assert basic["entitlements"]["premium"] and not basic["entitlements"]["enforced"] and basic["entitlements"]["features"]["keyword_alerts"]
    monkeypatch.setenv("PREMIUM_ENFORCED", "true")
    locked = subscription_for(repo, uid, now)["entitlements"]
    assert not locked["premium"] and not any(locked["features"].values()) and locked["limits"]["history_days"] == 7

    def store(status, expires_at, auto_renew=1):
        repo.db.execute("INSERT INTO subscriptions(user_id,period,status,store,expires_at,auto_renew,updated_at) VALUES(?,?,?,?,?,?,?) "
                        "ON CONFLICT(user_id) DO UPDATE SET status=excluded.status,expires_at=excluded.expires_at,auto_renew=excluded.auto_renew",
                        (uid, "annual", status, "google_play", expires_at, auto_renew, "2026-10-14T00:00:00.000000+00:00"))
        repo.db.commit()
    store("active", "2027-10-14T12:00:00.000000+00:00")
    premium = subscription_for(repo, uid, now)
    assert premium["tier"] == "premium" and premium["period"] == "annual" and premium["will_renew"] and premium["limits"]["briefing_times"] == 3
    assert premium["entitlements"]["premium"] and premium["entitlements"]["limits"]["favorite_teams"] == 10
    store("grace", "2026-10-21T12:00:00.000000+00:00")
    assert subscription_for(repo, uid, now)["payment_issue"]
    store("canceled", "2026-11-01T12:00:00.000000+00:00", 0)
    canceled = subscription_for(repo, uid, now)
    assert canceled["tier"] == "premium" and not canceled["will_renew"]          # paid period still running
    store("active", "2026-10-01T12:00:00.000000+00:00")
    assert subscription_for(repo, uid, now)["tier"] == "basic"                  # expired
    monkeypatch.setenv("BILLING_ENABLED", "1")
    assert subscription_for(repo, uid, now)["purchases_enabled"]


def test_indexing_and_clustering_never_hold_the_write_lock_during_slow_work(repo, monkeypatch):
    """API writes (a device registration, a notification switch) must not wait behind a news cycle."""
    from newzi_backend import content
    from newzi_engine.clustering import events
    held = []
    classify, cluster = content.classify_for_index, events.cluster_articles

    def classify_checked(*args, **kwargs):
        held.append(("classify", repo.db.in_transaction)); return classify(*args, **kwargs)

    def cluster_checked(*args, **kwargs):
        held.append(("cluster", repo.db.in_transaction)); return cluster(*args, **kwargs)
    monkeypatch.setattr(content, "classify_for_index", classify_checked)
    monkeypatch.setattr(events, "cluster_articles", cluster_checked)
    stories = [story(f"s{index}", source, title, hours_ago=index)
               for index, (source, title) in enumerate([("verge", "Google releases Gemini 4 Argon"), ("wired", "Google rolls out Gemini 4 Argon"),
                                                        ("folha", "Filme sobre criador do ChatGPT é aclamado"), ("g1", "Chuva forte atinge São Paulo")])]
    content.sync_content(repo, stories)
    content._cluster_incremental_content(repo, stories)
    assert {kind for kind, _ in held} == {"classify", "cluster"}
    assert not any(in_transaction for _, in_transaction in held)
