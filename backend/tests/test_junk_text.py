import support  # noqa: F401  (isolated environment before engine/backend imports)

import pytest

from newzi_engine.utils.text import strip_junk_text


# Texto lixo taken from real feed descriptions: the text before "→" loses what is not the story.
@pytest.mark.parametrize("raw, clean", [
    # Photo credits, with the caption glued to them (a caption opening the text goes whole, full stops and all)
    ("A IA que imita as relações humanas LightRocket via Getty Images (BBC) O episódio oferece uma ideia.", "O episódio oferece uma ideia."),
    ("Encontro de Donald Trump e Vladimir Putin em 2025. Andrew Harnik/Getty Images via BBC O presidente dos Estados Unidos enfrenta pressão.",
     "O presidente dos Estados Unidos enfrenta pressão."),
    ("A OpenAI suspendeu nesta semana o lançamento do novo sistema depois que pesquisadores independentes apontaram falhas graves "
     "de segurança em testes feitos com agências do governo americano nos últimos dois meses. OpenAI abandona lançamento Andrej Ivanov/AFP via Getty Images "
     "Crescem as dúvidas sobre a segurança.",
     "A OpenAI suspendeu nesta semana o lançamento do novo sistema depois que pesquisadores independentes apontaram falhas graves "
     "de segurança em testes feitos com agências do governo americano nos últimos dois meses. Crescem as dúvidas sobre a segurança."),
    ("Ela conta que as religiões de matriz africana abraçaram a festa há muitas décadas e que hoje as celebrações reúnem famílias "
     "inteiras em vários bairros da cidade. Fiéis na Paróquia de São Cosme Foto: Fernando Frazão/Agência Brasil O padre Luiz Gustavo celebrou.",
     "Ela conta que as religiões de matriz africana abraçaram a festa há muitas décadas e que hoje as celebrações reúnem famílias "
     "inteiras em vários bairros da cidade. O padre Luiz Gustavo celebrou."),
    ("Lula e o presidente do Uruguai, Yamandú Orsi, em Nova York - Foto: @LulaOficial/ X Lula informou que Orsi autorizou o Brasil.",
     "Lula informou que Orsi autorizou o Brasil."),
    ("Presidente de El Salvador, Nayib Bukele, e presidente do Peru, Keiko Fujimori. Jose Cabezas/Reuters/Guadalupe Pardo/Pool via Reuters O autoritário presidente fez escola.",
     "O autoritário presidente fez escola."),
    ("Bryan Cranston e RJ Mitte Reprodução / Redes Sociais Bryan Cranston usou as redes sociais.", "Bryan Cranston usou as redes sociais."),
    # Paywall notice
    ("O Copom manteve a Selic. Matéria exclusiva para assinantes. Para ter acesso completo, acesse o link da matéria e faça o seu cadastro.",
     "O Copom manteve a Selic."),
    # "Saiba mais" / "Leia mais" pointers: the pointer goes, the story stays
    ("Os criminosos aceitam PIX. (saiba mais abaixo) Os vídeos publicados no TikTok nem sempre têm relação.",
     "Os criminosos aceitam PIX. Os vídeos publicados no TikTok nem sempre têm relação."),
    ("Com essa decisão, Dino considerou não haver mais o que julgar no STF. Saiba mais no Repórter Brasil Tarde, da TV Brasil",
     "Com essa decisão, Dino considerou não haver mais o que julgar no STF."),
    ("A falha cancelou 80 voos - saiba mais clicando aqui. A companhia tem 50 aeronaves.", "A falha cancelou 80 voos. A companhia tem 50 aeronaves."),
    ("Os Galaxy Tab S12+ e Ultra já têm data de lançamento; saiba mais . {{WHATSAPP_CHANNEL}}", "Os Galaxy Tab S12+ e Ultra já têm data de lançamento."),
    ("O irmão do papa falou com jornalistas. Leia mais abaixo. Louis disse também que o câncer não era grave.",
     "O irmão do papa falou com jornalistas. Louis disse também que o câncer não era grave."),
    ("🗞️Leia mais notícias do Figueirense ✅Clique aqui para seguir o canal ge Figueirense no WhatsApp Inicialmente marcado para domingo, o duelo foi antecipado.",
     "Inicialmente marcado para domingo, o duelo foi antecipado."),
    # Plugs and feed footers
    ("A medida foi anunciada nesta terça. ✅ Siga o canal de notícias internacionais do g1 no WhatsApp Segundo os investigadores, os acusados fugiram.",
     "A medida foi anunciada nesta terça. Segundo os investigadores, os acusados fugiram."),
    ("O ex-zagueiro chegou ao clube. O post Seedorf desembarca em São Paulo apareceu primeiro em Gazeta Esportiva .", "O ex-zagueiro chegou ao clube."),
    ("Get our breaking news email , free app or daily news podcast Artificial intelligence company OpenAI disclosed another hack.",
     "Artificial intelligence company OpenAI disclosed another hack."),
    ("O recurso chega em novembro. Se você gostou do conteúdo, talvez também se interesse por conferir “ Como usar o Gemini ”. {{WHATSAPP_CHANNEL}}",
     "O recurso chega em novembro."),
])
def test_texto_lixo_is_removed(raw, clean):
    assert strip_junk_text(raw) == clean


# The same words used inside the story stay.
@pytest.mark.parametrize("text", [
    "Os audiolivros são um recurso exclusivo para assinantes do serviço pago Spotify Premium.",
    "A função passa a ser exclusiva para assinantes.",
    "Noah Macon viu a sua avó perder a vida no desastre, mas talvez saiba mais do que aparenta.",
    "Talitha Getty, Marianne Faithfull e Anita Pallenberg frequentavam o Quorum.",
    "Reprodução em ambiente claro foi o teste mais difícil para o projetor.",
    "Vasconcelos ficou em terceiro lugar na categoria Divulgação Científica do prêmio.",
    "Uma pesquisa Reuters/Ipsos mostra o presidente com 40% de aprovação.",
    "A belarussa perdeu por 2 sets a 1, com parciais de 3/6, 6/4 e 7/5.",
    "Siga o fluxo de ativação no aplicativo.",
    "O post se insere no contexto de mensagens nas redes sociais.",
    "Walter White Jr., seu filho na série, foi vivido por RJ Mitte.",
])
def test_story_text_stays(text):
    assert strip_junk_text(text) == text


def test_the_narration_leaves_texto_lixo_out():
    from newzi_backend.audio import AudioScriptComposer
    item = {"id": "i1", "headline": "Valor: Copom mantém juros",
            "summary": "A IA que imita as relações humanas LightRocket via Getty Images (BBC) O Banco Central manteve a Selic em 15% ao ano. "
                       "Matéria exclusiva para assinantes. Para ter acesso completo, acesse o link da matéria e faça o seu cadastro.",
            "why_it_matters": None, "warnings": [], "primary_taxonomy_id": "ECONOMY"}
    narrated = AudioScriptComposer().compose({"status": "READY", "language": "pt-BR", "items": [item]}, "pt-BR")[1][2]
    assert "Banco Central manteve a Selic em 15 por cento ao ano" in narrated
    assert "Getty" not in narrated and "assinantes" not in narrated and "LightRocket" not in narrated
