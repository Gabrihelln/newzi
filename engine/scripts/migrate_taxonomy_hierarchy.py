"""Apply the reviewed parent map while preserving every existing topic ID."""
import json
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "config" / "taxonomy.json"
ROOTS = {
    "BRAZIL", "WORLD", "POLITICS", "ECONOMY", "BUSINESS", "TECHNOLOGY",
    "SCIENCE", "HEALTH", "EDUCATION", "ENVIRONMENT", "CULTURE",
    "ENTERTAINMENT", "SPORTS", "ENERGIA", "AGRONEGOCIO", "TRANSPORTES",
    "TURISMO", "SOCIETY",
}
PARENT_GROUPS = {
    "BRAZIL": "REGIOES_DO_BRASIL POLITICAS_PUBLICAS ELEICOES_NO_BRASIL GOVERNO_FEDERAL CONGRESSO_NACIONAL JUSTICA_BRASILEIRA SEGURANCA_PUBLICA SOCIEDADE_BRASILEIRA SUS LEGISLACAO_BRASILEIRA ECONOMIA_BRASILEIRA CULTURA_BRASILEIRA POLITICA_REGIONAL ELEICOES_MUNICIPAIS ADMINISTRACAO_PUBLICA",
    "REGIOES_DO_BRASIL": "ESTADOS CIDADES",
    "WORLD": "GEOPOLITICA DIPLOMACIA CONFLITOS_INTERNACIONAIS ELEICOES_NO_MUNDO GOVERNOS_ESTRANGEIROS DEFESA ORGANIZACOES_INTERNACIONAIS AMERICA_LATINA ESTADOS_UNIDOS EUROPA ASIA AFRICA ORIENTE_MEDIO GEOPOLITICA_GLOBAL TRATADOS_INTERNACIONAIS SANCOES_ECONOMICAS RELACOES_CHINA_ESTADOS_UNIDOS UNIAO_EUROPEIA",
    "POLITICS": "ELEICOES GOVERNO CONGRESSO JUSTICA PARTIDOS_POLITICOS LEGISLACAO RELACOES_EXTERIORES CORRUPCAO TRANSPARENCIA_PUBLICA POLITICA_TRIBUTARIA POLITICA_EXTERNA REFORMA_POLITICA DIREITO_CONSTITUCIONAL",
    "ECONOMY": "FINANCE MACROECONOMIA INFLACAO JUROS EMPREGO MERCADO_FINANCEIRO INVESTIMENTOS BANCOS CREDITO IMPOSTOS COMERCIO PIB FINANCAS_PESSOAIS MERCADO_DE_TRABALHO TRABALHO CONSUMO COMMODITIES CAMBIO MERCADO_DE_CAPITAIS SEGUROS FUNDO_DE_INVESTIMENTO COMERCIO_EXTERIOR DESIGUALDADE_ECONOMICA FINTECHS",
    "BUSINESS": "STARTUPS EMPRESAS EMPREENDEDORISMO GESTAO VAREJO INDUSTRIA FUSOES_E_AQUISICOES PEQUENAS_EMPRESAS GOVERNANCA_CORPORATIVA COMERCIO_ELETRONICO E_COMMERCE LOGISTICA FRANQUIAS CAPITAL_DE_RISCO LIDERANCA_EMPRESARIAL IMOVEIS",
    "TECHNOLOGY": "ARTIFICIAL_INTELLIGENCE CYBERSECURITY SOFTWARE HARDWARE INTERNET BIG_TECH TELECOMUNICACOES ROBOTICA COMPUTACAO_EM_NUVEM PRIVACIDADE_DIGITAL GAMES PLATAFORMAS_DIGITAIS INOVACAO SEMICONDUTORES DESENVOLVIMENTO_DE_SOFTWARE REDES_SOCIAIS COMPUTACAO_QUANTICA TECNOLOGIA_FINANCEIRA OPEN_SOURCE REALIDADE_VIRTUAL",
    "SCIENCE": "PESQUISA_CIENTIFICA ESPACO FISICA BIOLOGIA QUIMICA MATEMATICA ARQUEOLOGIA GENETICA NEUROCIENCIA OCEANOGRAFIA PALEONTOLOGIA CIENCIAS_DA_TERRA NANOTECNOLOGIA METEOROLOGIA",
    "ESPACO": "ASTRONOMIA EXPLORACAO_ESPACIAL",
    "HEALTH": "MEDICINA SAUDE_PUBLICA FARMACEUTICA NUTRICAO BEM_ESTAR SAUDE_MENTAL DOENCAS VACINAS HOSPITAIS PESQUISA_MEDICA SAUDE_MATERNA SAUDE_INFANTIL ENVELHECIMENTO TERAPIAS SAUDE_PREVENTIVA SAUDE_GLOBAL SAUDE_DIGITAL TECNOLOGIA_MEDICA",
    "NUTRICAO": "ALIMENTACAO_SAUDAVEL",
    "PESQUISA_MEDICA": "PESQUISA_CLINICA",
    "EDUCATION": "UNIVERSIDADES ESCOLAS CARREIRA ENSINO_SUPERIOR PESQUISA_ACADEMICA EDUCACAO_BASICA FORMACAO_PROFISSIONAL ALFABETIZACAO POLITICA_EDUCACIONAL EDUCACAO_INCLUSIVA BOLSAS_DE_ESTUDO ENSINO_TECNICO MERCADO_PROFISSIONAL DESENVOLVIMENTO_DE_CARREIRA TECNOLOGIA_EDUCACIONAL",
    "UNIVERSIDADES": "PESQUISA_ACADEMICA BOLSAS_DE_ESTUDO",
    "ENVIRONMENT": "CLIMA SUSTENTABILIDADE BIODIVERSIDADE DESMATAMENTO CONSERVACAO AMAZONIA OCEANOS RECURSOS_HIDRICOS POLUICAO DESASTRES_NATURAIS",
    "ENERGIA": "PETROLEO_E_GAS ENERGIA_RENOVAVEL MINERACAO TRANSICAO_ENERGETICA",
    "AGRONEGOCIO": "AGRICULTURA ALIMENTACAO AGRICULTURA_SUSTENTAVEL SEGURANCA_ALIMENTAR",
    "TRANSPORTES": "MOBILIDADE AUTOMOVEIS AVIACAO INFRAESTRUTURA TRANSPORTE_PUBLICO",
    "CULTURE": "LIVROS ARTE ARTES_VISUAIS PATRIMONIO PATRIMONIO_HISTORICO DANCA TEATRO FOTOGRAFIA DESIGN QUADRINHOS MODA ARQUITETURA",
    "ENTERTAINMENT": "CINEMA TELEVISAO STREAMING MUSICA CELEBRIDADES CRIADORES_DIGITAIS CULTURA_POP FESTIVAIS ANIMACAO DOCUMENTARIOS PRODUCAO_AUDIOVISUAL INDUSTRIA_MUSICAL CULTURA_DIGITAL PODCASTS TELEVISAO_BRASILEIRA",
    "SPORTS": "FUTEBOL FORMULA_1 BASQUETE TENIS OLIMPIADAS VOLEI ATLETISMO AUTOMOBILISMO ESPORTES_OLIMPICOS SURFE LUTAS RUGBY GOLFE CICLISMO ESPORTES_ELETRONICOS FUTEBOL_FEMININO FUTEBOL_INTERNACIONAL CORRIDA",
    "TURISMO": "VIAGENS GASTRONOMIA GASTRONOMIA_BRASILEIRA",
    "SOCIETY": "DIREITOS_HUMANOS POVOS_INDIGENAS MIGRACAO AJUDA_HUMANITARIA SOCIEDADE_BRASILEIRA",
}


def main():
    data = json.loads(PATH.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    by_id = {node["id"]: node for node in nodes}
    if "SOCIETY" not in by_id:
        node = {
            "id": "SOCIETY", "slug": "sociedade", "name": "Sociedade",
            "description": "Direitos, migração, grupos sociais e vida coletiva.",
            "aliases": ["Society", "Vida em sociedade"], "active": True,
            "display_order": 145, "type": "domain",
            "terms": {"sociedade": 7, "direitos humanos": 8, "migração": 7, "humanitário": 6},
        }
        nodes.append(node)
        by_id[node["id"]] = node
    for node in (
        {"id": "GENERATIVE_AI", "slug": "ia-generativa", "name": "IA generativa", "description": "Modelos generativos, aplicações e conteúdo criado por inteligência artificial.", "aliases": ["Generative AI", "Generative artificial intelligence"], "active": True, "display_order": 1001, "type": "subject", "parent_id": "ARTIFICIAL_INTELLIGENCE", "terms": {"ia generativa": 10, "generative ai": 10, "geração por inteligência artificial": 8}},
        {"id": "MACHINE_LEARNING", "slug": "aprendizado-de-maquina", "name": "Aprendizado de máquina", "description": "Métodos e sistemas de aprendizado de máquina.", "aliases": ["Machine learning", "ML"], "active": True, "display_order": 1002, "type": "subject", "parent_id": "ARTIFICIAL_INTELLIGENCE", "terms": {"aprendizado de máquina": 10, "aprendizagem de máquina": 9, "machine learning": 10}},
        {"id": "AI_REGULATION", "slug": "regulacao-de-ia", "name": "Regulação de IA", "description": "Leis, políticas e governança da inteligência artificial.", "aliases": ["AI regulation", "Regulação da inteligência artificial"], "active": True, "display_order": 1003, "type": "subject", "parent_id": "ARTIFICIAL_INTELLIGENCE", "terms": {"regulação de ia": 10, "regulação da inteligência artificial": 10, "ai regulation": 9}},
    ):
        if node["id"] not in by_id:
            nodes.append(node)
            by_id[node["id"]] = node
    for parent, children in PARENT_GROUPS.items():
        for child in children.split():
            if parent not in by_id or child not in by_id:
                raise ValueError(f"unknown taxonomy ID in parent map: {parent} -> {child}")
            by_id[child]["parent_id"] = parent
    for node in nodes:
        if node["id"] in ROOTS:
            node.pop("parent_id", None)
            node["type"] = "domain"
        else:
            node["type"] = "subject"
    unmapped = [node["id"] for node in nodes if node["id"] not in ROOTS and not node.get("parent_id")]
    if unmapped:
        raise ValueError("unmapped taxonomy IDs: " + ", ".join(unmapped))
    data["version"] = max(2, int(data.get("version", 1)))
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"nodes": len(nodes), "roots": len(ROOTS), "parent_links": sum(bool(node.get("parent_id")) for node in nodes)})


if __name__ == "__main__":
    main()
