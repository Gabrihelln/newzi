# Analytics Newzi: painel de métricas do produto

> **Para quem for implementar (Claude ou outra pessoa):** leia este documento inteiro antes de começar e siga as
> etapas da seção 11 **na ordem**. Cada etapa diz se é **[Claude]** (código, terminal, testes) ou **[Gabriel]**
> (precisa das contas do dono do projeto: Hostinger, App Store Connect, Google Play, RevenueCat, Firebase).
> Comandos na VPS são sempre passados ao Gabriel para ele rodar (ninguém acessa a VPS diretamente).
> Ao terminar uma etapa, marque o `[ ]` como `[x]` neste arquivo.

Proposta registrada em 2026-10-22. **Etapa 1 (painel somente leitura) no ar desde 2026-10-27** em https://painel.newzi.app;
as demais etapas ainda não.

## 1. A ideia

**Analytics Newzi** é o nome do painel e do conjunto de métricas do Newzi. É um site privado, num subdomínio do
`newzi.app`, onde o dono do projeto vê tudo o que o aplicativo entrega: quantas pessoas usam, por quanto tempo,
o que usam, se ouvem o áudio, se as notificações funcionam, se as assinaturas crescem e se o sistema está
saudável. Pelo mesmo painel ele também envia avisos e promoções por push.

O objetivo **não é auditoria nem controle de usuários**. É saber se as funcionalidades e o sistema estão valendo
a pena para quem usa, como métricas de venda de um produto:

- **Uso:** quem volta, com que frequência e por quanto tempo.
- **Valor:** quais recursos as pessoas realmente usam (áudio, Explorar, salvos, esportes, alertas).
- **Negócio:** se o uso vira assinatura e se a assinatura se mantém.
- **Qualidade:** se o conteúdo, o áudio e as notificações chegam bem e sem erro.

### Princípios

1. **Números agregados primeiro.** O painel mostra totais, médias, taxas e tendências. O detalhe de um usuário
   existe para suporte e para entender casos (ex.: "por que essa pessoa não recebe o áudio?"), não para vigiar.
2. **Só dados que o Newzi já trata ou que servem para melhorar o produto.** Nada de localização, contatos,
   identificador de publicidade (IDFA/AAID) ou rastreio em outros apps e sites.
3. **Os dados ficam com o Newzi**, no banco que já existe na VPS. Nenhuma venda ou compartilhamento.
4. **Transparência:** política de privacidade e textos de privacidade das lojas atualizados antes de coletar
   qualquer dado novo de uso (seção 10).
5. **Leve para o servidor:** a VPS é pequena (Hostinger KVM 1) e o banco é SQLite. Os números pesados são
   calculados uma vez por dia (seção 2.4).

## 2. Como funciona (arquitetura)

```
Navegador → analytics.newzi.app (Nginx + HTTPS)
               ├─ /          → site do painel (arquivos estáticos em /var/www/newzi-analytics)
               └─ /api/...   → backend atual em 127.0.0.1:8090, rotas novas /admin/*
                                 ├─ banco atual (/var/lib/newzi)
                                 ├─ resumo diário (tabelas analytics_*)
                                 └─ envio de push (FCM, o mesmo do app)
```

### 2.1 Subdomínio

- **`painel.newzi.app`** (decidido em 2026-10-27). Registro `A` criado no hPanel apontando para a VPS.
- Nginx: `deploy/nginx/newzi-painel.conf.example`. Serve os arquivos de `/opt/newzi/admin` direto do checkout e
  encaminha só `/api/v1/admin/` ao backend (o resto de `/api/` dá 404 nesse host). Mesmo domínio para site e API:
  sem CORS, e o cookie da sessão é `SameSite=Strict`.
- HTTPS pelo Certbot, como em `api.newzi.app` e `newzi.app`.
- Os outros projetos que rodam na VPS não são tocados.

### 2.2 Backend

- Um grupo novo de rotas **`/admin/*`** no FastAPI que já roda (`backend/src/newzi_backend/api/routes/admin.py`).
  Usa o mesmo banco e as mesmas classes de serviço.
- Todas as rotas `/admin/*` são **somente leitura**, exceto o envio de push (seção 8) e o Premium dado pelo
  painel (seção 7.1), que pedem confirmação explícita e ficam registrados.
- Não há servidor, banco ou serviço novo.

### 2.3 Acesso

- **Login com e-mail e senha próprios do painel** (decidido em 2026-10-27), sem Google e sem Firebase. Um único
  acesso: `gabrielaraujo.n96@gmail.com`. Não é a conta do app: é uma senha só do painel.
- Em `/etc/newzi/newzi.env` ficam `ADMIN_EMAIL=...` e `ADMIN_PASSWORD_HASH=...` (hash scrypt/bcrypt, nunca a
  senha em texto). O hash é gerado pelo Gabriel na VPS com um script do repositório, que pede a senha sem
  mostrá-la; a senha nunca passa pelo Claude nem pelo git.
- Após o login, sessão em cookie `HttpOnly`, `Secure`, `SameSite=Strict`, válida por 12 h; botão Sair.
- Contra tentativa de senha: atraso crescente e bloqueio temporário após 5 erros seguidos; cada login (certo
  ou errado) fica registrado.
- Trocar a senha = gerar um hash novo e reiniciar a API (todas as sessões caem).
- Toda ação de escrita (envio de push, Premium dado ou retirado) é gravada numa tabela de registro (`admin_actions`), com quem fez,
  quando e o quê.

### 2.4 Resumo diário (adiado)

**Como ficou na etapa 1:** os números são calculados **na hora**, direto das tabelas que já existem
(`backend/src/newzi_backend/admin_metrics.py`). No volume atual o SQLite responde em milissegundos e não há
worker novo para manter. A única tabela nova de uso é `user_activity_days` (uma linha por usuário por dia,
gravada na primeira requisição autenticada do dia). Dias contados no fuso `ANALYTICS_TIMEZONE` (São Paulo).
Quando as telas ficarem lentas, ativar o resumo abaixo.

Plano original, para quando o volume pedir:

- Uma função nova do worker (`analytics`) roda de madrugada, depois do backup das 03:30. Ela calcula os
  números do dia anterior e grava em tabelas de resumo:
  - `analytics_daily(day, metric, segment, value)`: uma linha por métrica, dia e segmento (ex.: `dau`, `premium`, `1240`).
  - `analytics_cohorts(cohort_week, week_offset, users, active)`: retenção por coorte.
- O painel lê o resumo, que é rápido. Consultas ao vivo só no detalhe de um usuário e na tela de sistema.
- Se o resumo de um dia falhar, o painel mostra "sem dados" para esse dia e a tela de sistema avisa.

### 2.5 Site do painel

- Pasta **`admin/`** (nome técnico; o produto se chama Analytics Newzi): `index.html`, `app.js` e `style.css`, em
  JavaScript puro, **sem build e sem dependências**. Gráficos em SVG desenhados pelo próprio `app.js`.
- Deploy: só `git pull`; o Nginx serve a pasta do checkout.
- Modo claro e escuro, e funciona no celular (o Gabriel pode olhar o painel pelo iPhone ou Android).

## 3. O que já existe hoje

Dados que o backend **já grava** e que o painel pode mostrar sem mudar o app:

| Dado | Tabela(s) | O que dá para medir |
|---|---|---|
| Contas | `users` (`created_at`, `status`, `language`, `timezone`, `onboarding_status`) | cadastros por dia, idioma, fuso, quem terminou o onboarding |
| Logins | `auth_sessions` (`created_at`, `expires_at`, `revoked_at`) | logins por dia, sessões ativas, logouts |
| Preferências | `user_preferences` (tópicos, país, horário, tamanho, áudio, voz) | tópicos mais seguidos, horários preferidos, vozes escolhidas, quem desligou o áudio |
| Horários do briefing | `briefing_slots` | quantos briefings por dia cada pessoa configura e em que horários |
| Briefings entregues | `user_briefing_deliveries`, `briefing_editions`, `briefing_edition_items` | briefings gerados por dia, status, atrasos, falhas, voz usada, voz substituída (`voice_fallback_reason`) |
| Escuta do briefing | `briefing_listening_progress` (`progress_seconds`, `duration_seconds`, `completed_at`) | quem ouviu, quanto ouviu, quem ouviu até o fim, onde parou |
| Geração do briefing | `generation_jobs`, `generation_job_phases` | tempo de cada fase, tentativas, erros |
| Geração do áudio | `audio_generation_jobs`, `audio_job_phases`, `audio_artifacts`, `audio_events` | tempo de geração, tamanho e duração dos áudios, falhas, uso das prévias de voz |
| Atualização manual | `manual_refresh_requests` | quantas vezes as pessoas pedem um briefing novo, quanto demora, falhas |
| Notícias coletadas | `content_ingestion_runs`, `indexed_content`, `content_taxonomy` | notícias por dia, por fonte e por tópico, fontes com erro, idioma, imagens |
| Salvos | `saved_stories`, `saved_story_progress`, `saved_briefings`, `saved_collections`, `saved_collection_items` | quem salva, quanto salva, quanto lê do que salvou, uso de coleções |
| Avaliação de matérias | `article_feedback` (`rating`) | avaliações positivas e negativas por fonte e por tópico |
| Alertas (Premium) | `keyword_alerts`, `followed_stories` | quem usa alertas, palavras mais usadas, histórias mais seguidas |
| Esportes | `user_favorite_teams`, `user_followed_matches`, `football_match_audio`, `live_activity_starts` | times mais seguidos, jogos acompanhados, áudios de jogo, Live Activities no iOS |
| Aparelhos | `push_devices` (`platform`, `app_version`, `locale`, `timezone`, `enabled`, `last_seen_at`) | Android x iOS, versões do app em uso, quem permite notificações, **última vez que o app abriu em cada aparelho** |
| Notificações | `notification_settings`, `notification_jobs`, `notification_events` (`notification_sent`, `notification_failed`) | pushes enviados e com falha por tipo, tokens inválidos, quem desligou cada tipo |
| Assinaturas | `subscriptions` (`period`, `status`, `store`, `started_at`, `expires_at`, `auto_renew`), webhook do RevenueCat | assinantes ativos, mensal x anual, renovação automática desligada, vencimentos |
| Saúde do worker | `worker_heartbeats`, `/health/worker` | se cada função do worker está viva |
| Backup | `newzi-backup.timer`, `/var/lib/newzi-backup/copies` | data e tamanho do último backup |

Fora do nosso banco:

- **RevenueCat** (painel e API): receita, testes grátis, conversão, cancelamentos, reembolsos, MRR.
- **App Store Connect** e **Google Play Console**: downloads, avaliações, falhas (crashes), países.
- **Firebase Console**: hoje usado para os avisos e promoções por push (tópicos `novidades` e `promocoes`).

## 4. O que falta

| Lacuna | Por que importa | Como resolver | Precisa de versão nova do app? |
|---|---|---|---|
| **Histórico de atividade** | `push_devices.last_seen_at` guarda só a última vez; não dá para contar ativos por dia | O backend registra, a cada requisição autenticada, o dia de uso de cada usuário numa tabela nova `user_activity_days(user_id, day, first_at, last_at, requests, platform, app_version)` | **Não** |
| **Tempo de uso (sessões)** | Saber quanto tempo a pessoa fica no app | O app envia início e fim de sessão (seção 9) | **Sim** |
| **Navegação** | Saber quais telas e abas são usadas | O app envia as telas vistas (seção 9) | **Sim** |
| **Ações dentro do app** | Abriu a matéria original, trocou de voz, pesquisou, compartilhou | O app envia eventos (seção 9) | **Sim** |
| **Abertura pelo push** | Saber se a notificação funciona | Hoje o toque no push só navega dentro do app (`openFromNotification`) e não avisa o backend. O app passa a enviar `push_opened` com o id do job | **Sim** (ajuste pequeno) |
| **Receita e conversão completas** | Ver vendas sem abrir o RevenueCat | Ler a API do RevenueCat no resumo diário | **Não** |
| **Envio de push pelo painel** | Não depender do Firebase Console | Tela de envio no painel usando o FCM do backend (seção 8) | **Não** |

## 5. O que precisa ou não de versão nova na Apple (e no Google Play)

**Não precisa de versão nova** (só servidor e site):

- O painel inteiro: acesso, telas e gráficos.
- Tudo da seção 3.
- Usuários ativos por dia, semana e mês pelo servidor (`user_activity_days`).
- Envio de push pelo painel: o app já recebe pushes do backend e já entra nos tópicos `novidades` e `promocoes`.
- Vendas pela API do RevenueCat.

**Precisa de versão nova** (Apple e Google Play):

- Sessões e tempo de uso, telas visitadas, ações dentro do app, abertura pelo push.
- Plano: entrar na próxima versão (1.1) junto com outras melhorias, para passar por uma revisão só.
- Os textos de privacidade da App Store (App Privacy) podem ser editados no App Store Connect sem build, mas
  precisam estar corretos **antes** de sair a versão que coleta os dados de uso.

## 6. Catálogo de análises

Tudo o que dá para analisar sobre o Newzi. Coluna **Fonte**: **E** = dado que já existe; **S** = registro novo
no servidor (sem versão nova do app); **A** = evento novo do app (versão nova); **R** = API do RevenueCat;
**L** = consoles das lojas (consulta manual, fora do painel).

### 6.1 Crescimento

| Métrica | Como calcular | Fonte |
|---|---|---|
| Cadastros por dia, semana e mês | `users.created_at` | E |
| Total de contas ativas | `users.status` | E |
| Cadastros por forma de login (e-mail, Google, Apple) | origem da conta no Firebase / `users` | E (conferir campo) |
| Downloads x cadastros | downloads das lojas ÷ cadastros | L + E |
| Contas excluídas | exclusões de conta por período | E (conferir registro de exclusão) |
| Crescimento líquido | cadastros − exclusões | E |
| Plataforma de origem | `push_devices.platform` do primeiro aparelho | E |

### 6.2 Engajamento e uso

| Métrica | Como calcular | Fonte |
|---|---|---|
| Usuários ativos por dia (DAU), semana (WAU) e mês (MAU) | usuários com linha em `user_activity_days` no período | S |
| "Grude" do app (DAU/MAU) | DAU ÷ MAU; quanto mais perto de 1, mais uso diário | S |
| Dias de uso por semana por usuário | média de dias ativos em 7 dias | S |
| Horário de uso | hora das requisições ou das sessões | S / A |
| Sessões por dia por usuário | eventos `session_start` | A |
| Duração média da sessão | `session_end − session_start` | A |
| Tempo total por usuário por dia | soma das sessões | A |
| Telas mais vistas | eventos `screen_view` | A |
| Caminho mais comum dentro do app | sequência de `screen_view` por sessão | A |
| Funcionalidades nunca usadas | recursos com poucos eventos em relação aos ativos | A |
| Atualizações manuais do briefing | `manual_refresh_requests` por usuário e por dia | E |

### 6.3 Retenção e abandono

| Métrica | Como calcular | Fonte |
|---|---|---|
| Retenção D1, D7, D30 | dos que se cadastraram no dia X, quantos voltaram 1, 7 e 30 dias depois | S |
| Curva de retenção por coorte semanal | `analytics_cohorts` | S |
| Usuários em risco | ativos no mês passado sem uso há 7+ dias | S |
| Usuários perdidos | sem uso há 30+ dias | S |
| Reativação | perdidos que voltaram (ex.: depois de um push) | S |
| Retenção por plataforma, idioma, tópico | retenção dividida por segmento | S + E |
| Retenção de quem ouve o áudio x quem não ouve | coortes cruzadas com `briefing_listening_progress` | S + E |

### 6.4 Onboarding

| Métrica | Como calcular | Fonte |
|---|---|---|
| Taxa de conclusão do onboarding | `users.onboarding_status` | E |
| Onde as pessoas desistem | passo do onboarding em que param | A |
| Tópicos escolhidos no onboarding | `user_preferences.topics_json` | E |
| Permissão de notificação aceita no onboarding | `push_devices.enabled` logo após o cadastro | E |
| Tempo até o primeiro briefing ouvido | primeira `briefing_listening_progress` − `users.created_at` | E |

### 6.5 Briefing

| Métrica | Como calcular | Fonte |
|---|---|---|
| Briefings entregues por dia e por horário | `user_briefing_deliveries` | E |
| Entregas no horário x atrasadas | `delivered_at` comparado com `delivery_time` | E |
| Falhas de geração e o motivo | `generation_jobs.error_code`, `user_briefing_deliveries.generation_error_code` | E |
| Tempo de cada fase da geração | `generation_job_phases` | E |
| Tamanho dos briefings (itens) | `briefing_editions.item_count` | E |
| Tópicos que mais aparecem nos briefings | `briefing_edition_items.primary_taxonomy_id` | E |
| Tópicos sem notícia suficiente | avisos `FALLBACK_NO_FRESH_CONTENT_FOR_TOPIC` em `warnings_json` | E |
| Histórias repetidas de outro dia | avisos `FALLBACK_RECENT_EVENT_REUSE` | E |
| Quantas fontes por história | `sources_json` | E |
| Briefings abertos (tela do briefing vista) | `screen_view` da tela do briefing | A |
| Briefings salvos | `saved_briefings` | E |

### 6.6 Áudio

| Métrica | Como calcular | Fonte |
|---|---|---|
| % de briefings ouvidos | entregas com `progress_seconds > 0` ÷ entregas | E |
| % ouvidos até o fim | `completed_at` preenchido ÷ entregas | E |
| Quanto do áudio é ouvido, em média | `progress_seconds ÷ duration_seconds` | E |
| Onde as pessoas param | distribuição de `progress_seconds`, cruzada com os segmentos do roteiro (`audio_script_segments`): qual notícia estava tocando | E |
| Vozes mais usadas | `user_preferences.audio_voice_id`, `selected_voice_id` | E |
| Prévias de voz ouvidas | `audio_events` (`voice_preview_created`, `voice_preview_cache_hit`) | E |
| Voz substituída por falha | `voice_fallback_reason` | E |
| Tempo de geração do áudio | `audio_job_phases` | E |
| Falhas de geração do áudio | `audio_generation_jobs.status`, `error_code` | E |
| Duração média dos áudios | `audio_artifacts.duration_ms` | E |
| Resumo estendido (Premium) x padrão | escuta de cada tipo | E |
| Áudio das matérias salvas | uso de `/me/saved/audio` | S |
| Velocidade de reprodução, pular e voltar | eventos do player | A |
| Escuta em segundo plano e tela bloqueada | eventos do player | A |
| Uso dos capítulos do áudio | eventos de toque em capítulo | A |
| Texto lixo que escapou da limpeza | busca por padrões conhecidos no roteiro (`audio_script_segments.text`) | E |

### 6.7 Notícias, Home e Explorar

| Métrica | Como calcular | Fonte |
|---|---|---|
| Notícias abertas por dia | requisições a `/me/news/{id}` | S |
| Matérias originais abertas (clique para o site do veículo) | evento `story_source_opened` | A |
| Notícias mais abertas | contagem por história | S |
| Tópicos mais lidos x mais seguidos | leitura por tópico ÷ seguidores do tópico | S + E |
| Uso do Explorar e da busca | eventos de busca (sem guardar o texto, ou guardando só os termos agregados) | A |
| Buscas sem resultado | buscas com zero itens | A |
| Assuntos em alta abertos | requisições a `/me/trending` | S |
| Compartilhamentos | evento `story_shared` | A |
| Avaliações das matérias | `article_feedback` por fonte e tópico | E |

### 6.8 Salvos, coleções e alertas

| Métrica | Como calcular | Fonte |
|---|---|---|
| Quem salva matérias e quantas | `saved_stories` | E |
| Quanto lê do que salvou | `saved_story_progress.progress` | E |
| Uso de coleções | `saved_collections`, `saved_collection_items` | E |
| Alertas por palavra-chave (Premium) | `keyword_alerts` | E |
| Histórias seguidas (Premium) | `followed_stories` | E |
| Alertas que viraram push e foram abertos | `notification_jobs` + `push_opened` | E + A |

### 6.9 Esportes

| Métrica | Como calcular | Fonte |
|---|---|---|
| Times mais seguidos | `user_favorite_teams` | E |
| Jogos acompanhados | `user_followed_matches` | E |
| Áudios de jogo ouvidos | `football_match_audio` + requisições do arquivo | E + S |
| Live Activities iniciadas (iOS) | `live_activity_starts` | E |
| Alertas de gol, início e fim enviados e abertos | `notification_jobs` por tipo + `push_opened` | E + A |
| Uso da aba Esportes | `screen_view` | A |

### 6.10 Notificações

| Métrica | Como calcular | Fonte |
|---|---|---|
| Quem permite notificações | `push_devices.enabled` | E |
| Quem desligou cada tipo | `notification_settings` | E |
| Enviadas por tipo (briefing, urgente, time, alertas) | `notification_jobs.notification_type`, `notification_events` | E |
| Falhas e tokens inválidos | `notification_failed`, `invalidated_at` | E |
| Taxa de abertura por tipo | `push_opened` ÷ enviadas | A |
| Melhor horário para avisos | abertura por hora do envio | A |
| Pushes urgentes por dia por usuário | contagem (regra atual: até 5 por dia, intervalo de 45 min) | E |
| Notificação que fez a pessoa voltar | abertura seguida de sessão de quem estava em risco | A + S |
| Avisos e promoções enviados pelo painel | `admin_actions` | S |
| Quem desativou notificações depois de muitos pushes | `enabled` mudando para 0 depois de vários envios | E |

### 6.11 Assinaturas e receita

| Métrica | Como calcular | Fonte |
|---|---|---|
| Assinantes ativos (mensal x anual) | `subscriptions` | E |
| Novas assinaturas por dia | `subscriptions.started_at` | E |
| Testes grátis iniciados e convertidos | eventos do RevenueCat | R |
| Taxa de conversão gratuito → Premium | assinantes ÷ usuários ativos | E + S |
| Tempo até assinar | `started_at − users.created_at` | E |
| Renovação automática desligada (risco de cancelar) | `auto_renew = 0` | E |
| Cancelamentos e reembolsos | eventos do RevenueCat | R |
| Receita e MRR | API do RevenueCat | R |
| Receita por plataforma (App Store x Google Play) | `subscriptions.store` + RevenueCat | E + R |
| Uso dos recursos Premium | resumo estendido, alertas, histórico completo, busca nos briefings | E + S |
| O que o assinante usa mais que o gratuito | comparação de uso entre os dois grupos | E + S + A |
| Telas de oferta vistas x compras | `screen_view` da tela de assinatura ÷ compras | A + E |

### 6.12 Personalização

| Métrica | Como calcular | Fonte |
|---|---|---|
| Tópicos mais e menos seguidos | `user_preferences.topics_json` | E |
| Mudanças de tópicos ao longo do tempo | alterações das preferências | S (guardar histórico) |
| Horários de briefing preferidos | `briefing_slots`, `briefing_time` | E |
| Alcance: nacional, mundo ou ambos | `country_scope`, `content_scope` | E |
| Tamanho do briefing escolhido | `briefing_size` | E |
| Idioma de leitura | `user_preferences.language` | E |
| Tema claro x escuro | evento ou preferência enviada pelo app | A |

### 6.13 Qualidade do conteúdo

| Métrica | Como calcular | Fonte |
|---|---|---|
| Notícias coletadas por dia e por fonte | `content_ingestion_runs`, `indexed_content` | E |
| Fontes com erro ou paradas | `errors_json`, `source_metrics_json`, `source_health` | E |
| Fontes que mais entram nos briefings | `sources_json` dos itens | E |
| Fontes com pior avaliação | `article_feedback` por fonte | E |
| Notícias sem imagem | `indexed_content.image_url` vazio | E |
| Notícias sem tópico ou com classificação fraca | `classification_confidence` | E |
| Notícias em inglês que chegariam a leitor em português | avisos `SOURCE_LANGUAGE_FALLBACK`, `TRANSLATION_*` | E |
| Texto lixo que ainda aparece | busca dos padrões de `strip_junk_text` nas descrições servidas | E |
| Histórias contadas por mais de um veículo | tamanho dos eventos (`event_id`) | E |
| Tempo entre a publicação e a chegada no briefing | `published_at` → entrega | E |

### 6.14 Saúde técnica e operação

| Métrica | Como calcular | Fonte |
|---|---|---|
| Funções do worker vivas | `worker_heartbeats`, `/health/worker` | E |
| Fila de geração (briefing e áudio) | jobs `PENDING` e atrasados | E |
| Tempo de resposta da API | tempo por rota, registrado pelo backend | S |
| Erros da API (5xx) por rota | contagem por rota | S |
| Erros de rede no app ("Sem conexão") | evento `api_error` | A |
| Falhas (crashes) do app | Xcode Organizer, App Store Connect, Google Play Console | L |
| Último backup e tamanho | `/var/lib/newzi-backup/copies` | E |
| Espaço em disco, memória e CPU da VPS | leitura do sistema pelo backend | S |
| Tamanho do banco e da pasta de áudios | arquivos em `/var/lib/newzi` | S |
| Validade dos certificados HTTPS | data de vencimento | S |

### 6.15 Aparelhos e versões

| Métrica | Como calcular | Fonte |
|---|---|---|
| Android x iOS | `push_devices.platform` | E |
| Versões do app em uso (quem ainda não atualizou) | `push_devices.app_version` | E |
| Idioma e fuso do aparelho | `locale`, `timezone` | E |
| Modelo do aparelho e versão do sistema | enviado pelo app | A |
| Aparelhos por conta | `push_devices` por `user_id` | E |

### 6.16 Cruzamentos que respondem "vale a pena?"

- Quem ouve o áudio volta mais? (retenção de ouvintes x não ouvintes)
- Quem ouve o áudio assina mais? (conversão por grupo)
- Quem segue um time volta mais nos dias de jogo?
- Quantos tópicos uma pessoa precisa seguir para continuar usando? (retenção por número de tópicos)
- O briefing estendido (Premium) é ouvido até o fim tanto quanto o padrão?
- Notificações urgentes trazem a pessoa de volta ou fazem desligar as notificações?
- Qual horário de briefing tem mais escuta?
- O que os assinantes usam que os gratuitos não usam? (argumento de venda)
- Quais recursos quase ninguém usa e poderiam ser simplificados ou retirados?
- Qual fonte gera mais leitura e qual gera mais avaliação negativa?

### 6.17 Avisos automáticos do painel

O painel destaca no topo, e opcionalmente manda um push ou e-mail ao Gabriel:

- Uma função do worker parou.
- Briefings ou áudios falhando acima do normal no dia.
- Uma fonte importante sem notícias novas há mais de 24 h.
- Fila de áudio atrasada.
- Taxa de escuta ou de abertura de push caiu muito em relação à semana anterior.
- Backup do dia não rodou.
- Disco da VPS acima de 80%.
- Assinaturas com renovação desligada acima do normal.

## 7. Telas do painel

1. **Visão geral:** DAU, WAU e MAU, cadastros, retenção D1/D7/D30, assinantes, receita do mês, taxa de escuta do
   áudio e os avisos da seção 6.17. Cada número mostra a variação em relação ao período anterior.
2. **Usuários:** busca por e-mail; lista com filtros (plano, plataforma, ativo/inativo). Detalhe: plano, tópicos,
   horários, voz, aparelhos e versões, últimos dias de uso, briefings recebidos e ouvidos, pushes recebidos e
   abertos, salvos e alertas. Uso pensado para suporte. No detalhe também fica o botão **Dar Premium**
   (seção 7.1).
3. **Engajamento:** sessões, tempo de uso, telas, funcionalidades e caminhos (completa a partir da etapa 4).
4. **Retenção:** tabela de coortes semanais e usuários em risco.
5. **Briefing e áudio:** entregas, atrasos, falhas, escuta, conclusão, onde param, vozes.
6. **Conteúdo:** fontes, coleta, tópicos, qualidade e avaliações.
7. **Notificações:** permissões, envios, falhas, aberturas, e a tela **Enviar push** (seção 8).
8. **Assinaturas:** assinantes, conversão, testes grátis, cancelamentos, receita.
9. **Esportes:** times, jogos, alertas, áudios de jogo.
10. **Sistema:** worker, filas, API, backup, disco, certificados.

Períodos: hoje, 7 dias, 30 dias, 90 dias e personalizado. Exportar qualquer tabela em CSV.

### 7.1 Dar Premium pelo painel

Pedido do Gabriel (2026-10-27): dar Premium a um usuário (cortesia, parceria, suporte, teste) direto pelo
painel, **com data inicial e data final**, sem precisar rodar `backend/premium_test_account.py` na VPS.

**Na tela:**

- No detalhe do usuário (tela Usuários), ou buscando por e-mail: **Dar Premium**, com:
  - **Data inicial** (padrão: agora) e **data final** (obrigatória). Data inicial no futuro deixa o Premium
    agendado: o usuário só passa a ter acesso nesse dia.
  - **Motivo** (cortesia, parceria, suporte, teste, outro) e uma observação livre.
- Também: **alterar as datas** de um Premium dado pelo painel e **retirar** (encerra na hora).
- O detalhe mostra o plano atual com a origem: loja (App Store / Google Play, via RevenueCat) ou painel, e as
  datas. Uma lista **Premium dado pelo painel** mostra todos os ativos, agendados e encerrados.
- Antes de salvar, o painel mostra o resumo ("fulano@... terá Premium de 01/11/2026 a 31/01/2027") e pede
  confirmação. Tudo vai para `admin_actions` (quem deu, para quem, datas, motivo).
- Para várias pessoas de uma vez (ex.: lista de parceiros), aceitar uma lista de e-mails com as mesmas datas.

**No banco (o que a implementação precisa resolver):**

Hoje `grant_manual` grava em `subscriptions` com `store='manual'`, mas essa tabela tem **uma linha por usuário**,
e isso traz três problemas que o painel não pode repetir:

1. **Não há data inicial de verdade.** O acesso só olha `status` e `expires_at` (`_active` em
   `subscriptions.py`); `started_at` é ignorado. Para agendar, a regra de acesso precisa exigir também
   `started_at <= agora`.
2. **Loja e painel se sobrescrevem.** Se o usuário assina na loja, o webhook do RevenueCat apaga o Premium dado
   pelo painel; se o painel dá Premium a quem já paga, sobrescreve a assinatura da loja. E `revoke_manual`
   apaga a linha inteira, inclusive uma assinatura paga.
3. **Sem histórico.** Ao vencer ou ser retirado, não sobra registro (mesmo problema da seção 8.3).

Proposta: uma tabela própria, **`premium_grants`** (`id`, `user_id`, `starts_at`, `ends_at`, `reason`, `note`,
`granted_by`, `created_at`, `revoked_at`, `revoked_by`). O usuário é Premium se tiver **assinatura da loja
ativa ou um grant vigente** (`starts_at <= agora < ends_at` e não retirado). Assim os dois nunca se apagam, o
histórico fica completo e o app continua recebendo o plano pelo mesmo `/me/subscription` e entitlements, sem
versão nova. O que for dado por `grant_manual` hoje migra para essa tabela, e o script da VPS passa a usar a
mesma função (fica como reserva, para quando o painel estiver fora do ar).

**Efeitos no resto do painel:**

- Métricas de assinatura e receita (6.11) **separam** Premium pago de Premium dado pelo painel; o dado não conta
  como conversão nem receita.
- Nos públicos de push (8.3), "Premium agora" inclui os dois, com um filtro para só pagos ou só cortesia.
- Quando o Premium dado estiver para vencer, o painel pode avisar (ex.: 3 dias antes), e opcionalmente mandar um
  push ao usuário convidando a assinar.
- O app mostra o Premium dado como "Premium até DD/MM", sem botão de gerenciar assinatura na loja (não há o que
  cancelar na loja). Conferir na implementação que a tela de assinatura trata `store='manual'` assim.

## 8. Envio de push pelo painel

Substitui o uso do Firebase Console para avisos e promoções. Decisões do Gabriel (2026-10-22):
**sem limite de envios**, envio **na hora** ou **agendado** para qualquer data e horário, e escolha livre de quem
recebe.

### 8.1 Tipo

- **Aviso** (novidades do app, comunicados) ou **Promoção** (ofertas do Premium). O tipo define o canal da
  notificação no Android (`announcements` ou `promotions`) e entra no registro.

### 8.2 Quando

- **Enviar agora:** sai na hora e a pessoa recebe na hora.
- **Agendar:** escolher data e horário (ex.: daqui a dois ou três dias, às 19h). Quantos agendamentos quiser.
- Lista de agendados com opções de **editar**, **cancelar** e **enviar agora**.
- O worker confere os agendados a cada minuto e envia no horário marcado.
- **Sem limite** por dia ou por pessoa e **sem bloqueio de horário**: a notificação sai exatamente quando for
  escolhida. O painel só mostra um lembrete informativo se o horário cair entre 22h e 7h, sem impedir o envio.

### 8.3 Para quem

Escolher um público (e, se quiser, combinar com os filtros extras):

| Público | Quem entra |
|---|---|
| **Todos** | todos os aparelhos com notificação permitida, inclusive quem instalou e ainda não entrou na conta (tópicos `novidades`/`promocoes`) |
| **Todos com conta** | todos os usuários cadastrados com notificação permitida |
| **Premium agora** | assinatura ativa hoje |
| **Sem Premium agora** | quem não tem assinatura ativa hoje (nunca teve + ex-Premium) |
| **Nunca foi Premium** | nunca teve assinatura |
| **Já foi Premium** | teve assinatura alguma vez (inclui quem ainda é) |
| **Ex-Premium** | teve assinatura e deixou de ter (venceu ou cancelou) |
| **Usuário específico** | um ou mais usuários, por ID ou e-mail (também serve para teste) |

Filtros extras, opcionais: plataforma (Android, iPhone), tópico seguido, time seguido, idioma, versão do app,
ativos ou inativos há X dias.

Como o histórico do Premium é lido: a tabela `subscriptions` tem uma linha por usuário com `status` e
`expires_at`. "Ex-Premium" e "Já foi Premium" dependem de essa linha continuar no banco quando a assinatura
vence ou é cancelada. **Conferir na implementação**; se ela for apagada ou sobrescrita, criar um histórico
(`subscription_history`) e usar os eventos do RevenueCat como reforço. Premium dado manualmente para teste ou
suporte (`grant_manual`) fica identificado e pode ser excluído do público.

### 8.4 Conteúdo e destino

- Título, texto e, opcionalmente, imagem.
- **Ao tocar:** abrir o app numa tela (início, briefing, uma notícia, assinatura).
- Prévia de como fica no Android e no iPhone.

### 8.5 Antes de enviar e depois

- O painel mostra **quantas pessoas e quantos aparelhos** vão receber e pede uma confirmação ("ENVIAR"), para
  evitar um envio errado para todos.
- **Registro:** cada envio e cada agendamento vai para `admin_actions` com tipo, texto, público, horário e
  resultado (enviados, falhas, tokens inválidos e, a partir da etapa 4, aberturas).
- Histórico de tudo o que foi enviado, com a opção de **duplicar** um envio para reaproveitar o texto.

### 8.6 Apple (diretriz 4.5.4)

Promoções por push exigem consentimento. A decisão atual é que a permissão de notificações do sistema basta. Se a
Apple pedir, será preciso uma opção no app para aceitar ou não promoções.

## 9. Eventos do app (versão 1.1)

O app junta os eventos e envia em lote para `POST /me/events` quando volta ao primeiro plano, ou a cada poucos
minutos. Sem internet, guarda e envia depois. Cada evento tem nome, horário, id da sessão, plataforma e versão
do app. Tabela nova `app_events(id, user_id, session_id, name, props_json, created_at, platform, app_version)`.

| Evento | Quando | Propriedades |
|---|---|---|
| `session_start` | app abre ou volta ao primeiro plano | origem (`icone`, `push`, `widget`) |
| `session_end` | app vai para segundo plano | duração em segundos |
| `screen_view` | troca de tela ou aba | nome da tela |
| `push_opened` | toque numa notificação | `job_id`, tipo |
| `briefing_play` / `briefing_pause` / `briefing_complete` | player do briefing | `delivery_id`, posição |
| `audio_seek` / `audio_speed` / `audio_chapter` | controles do player | posição, velocidade, capítulo |
| `story_opened` | notícia aberta | `story_id`, de onde veio (home, explorar, briefing, push) |
| `story_source_opened` | abriu a matéria no site do veículo | `story_id`, fonte |
| `story_shared` | compartilhou | `story_id` |
| `search` | busca no Explorar | quantidade de resultados (o texto da busca não é guardado por padrão) |
| `onboarding_step` | cada passo do onboarding | passo, concluído ou pulado |
| `paywall_view` / `purchase_started` | tela de assinatura | origem, plano |
| `voice_changed` | trocou a voz | voz nova |
| `theme_changed` | trocou claro ou escuro | tema |
| `api_error` | falha de rede ou de servidor | rota, código |

Regras:

- Nada de texto livre digitado pela pessoa, além do que já é guardado hoje (ex.: palavras dos alertas).
- Retenção: eventos brutos ficam **90 dias**; depois disso só o resumo diário (seção 2.4) permanece.
- Na exclusão da conta, os eventos da pessoa são apagados junto com os outros dados dela (`app_events` e
  `user_activity_days` entram no mesmo fluxo de exclusão de conta que já existe).

## 10. Privacidade e lojas

Antes de lançar a versão com eventos do app (etapa 4):

1. **Política de privacidade:** incluir que o Newzi coleta dados de uso do app (telas, tempo de uso, interações e
   escuta) para melhorar o produto, que os dados ficam nos servidores do Newzi, por quanto tempo ficam e como
   pedir a exclusão. Atualizar também `docs/DATA_INVENTORY.md`.
2. **App Store Connect → App Privacy:** marcar "Uso de dados → Interação com o produto" (e "Diagnóstico", se
   coletar erros), **vinculados à identidade do usuário**, finalidade "Análises" e "Funcionalidade do app",
   **sem rastreamento**.
3. **Google Play Console → Segurança dos dados:** declarar "Atividade no app" e "Diagnóstico do app", com a
   finalidade "Análises".
4. **Sem pedido de rastreamento (ATT) no iOS:** não usamos identificador de publicidade nem cruzamos dados com
   outros apps e sites. Se isso mudar algum dia, o pedido passa a ser obrigatório.
5. **LGPD:** base legal "legítimo interesse" para métricas de melhoria do produto, com a informação na política.
   Avaliar oferecer, nas configurações do app, "Compartilhar dados de uso" ligado por padrão, que a pessoa pode
   desligar (seção 12).
6. **Acesso ao painel:** só o e-mail de `ADMIN_EMAIL`, com a senha do painel. Nada do painel é público.

As etapas 1 a 3 só usam dados que o Newzi já trata para funcionar. Mesmo assim, revisar a política para citar
métricas agregadas de uso do serviço.

## 11. Etapas de implementação

### Etapa 1: painel com o que já existe (sem versão nova do app)

1. [x] **[Gabriel]** Criar o registro `A` `painel` no hPanel apontando para o IP da VPS (feito em 2026-10-27).
2. [x] **[Gabriel]** Acesso: só `gabrielaraujo.n96@gmail.com`, por senha (seção 2.3).
3. [x] **[Claude]** Backend: rotas `/api/v1/admin/*` somente leitura (`api/routes/admin.py`), login por senha do
   painel (`admin.py`, seção 2.3), script `backend/admin_password.py`, tabelas `admin_sessions` e `admin_actions`
   (migração `0013_admin_panel`), testes em `backend/tests/test_admin.py`.
4. [x] **[Claude]** Backend: tabela `user_activity_days`, preenchida a cada requisição autenticada (uma escrita
   por usuário por dia, para não pesar no SQLite), mais testes.
5. [ ] ~~**[Claude]** Worker: função `analytics` com o resumo diário (`analytics_daily`, `analytics_cohorts`),
   rodando depois do backup.~~ Adiado: números calculados na hora (seção 2.4).
6. [x] **[Claude]** Site `admin/`: login, Visão geral, Usuários, Briefing e áudio, Conteúdo, Notificações
   (só leitura), Assinaturas (dados do banco), Esportes, Sistema, mais Retenção (coortes) e exportar CSV.
7. [x] **[Claude]** Arquivos de deploy: bloco do Nginx em `deploy/nginx`, passos no `deploy/README.md`.
8. [x] **[Gabriel]** (feito em 2026-10-27; no ar em https://painel.newzi.app) Na VPS, com os comandos passados pelo Claude: `git pull`, gerar a senha do painel
   (`ADMIN_EMAIL` e `ADMIN_PASSWORD_HASH`), Nginx,
   Certbot, build do site, reiniciar `newzi-api` e `newzi-worker`.
9. [ ] **[Gabriel]** Entrar no painel e conferir os números com o que conhece do app.

### Etapa 2: envio de push e Premium pelo painel (sem versão nova do app)

1. [ ] **[Claude]** Conferir se `subscriptions` guarda quem deixou de ser Premium; se não, criar
   `subscription_history` (seção 8.3).
2. [ ] **[Claude]** Tela Enviar push (seção 8): tipo, públicos e filtros, conteúdo, prévia, confirmação, envio na
   hora, agendamento (editar, cancelar, enviar agora) e registro. Worker enviando os agendados a cada minuto.
3. [ ] **[Claude]** Testes; envio de teste para um usuário só.
4. [ ] **[Claude]** Premium pelo painel (seção 7.1): tabela `premium_grants`, regra de acesso loja + grant com
   data inicial, migração dos `store='manual'`, rotas para dar, alterar e retirar, tela no detalhe do usuário e
   lista dos grants, `premium_test_account.py` usando a mesma função, testes (agendado, vencido, retirado, junto
   com assinatura da loja).
5. [ ] **[Gabriel]** Testar no próprio celular (Android e iPhone) e decidir se o Firebase Console deixa de ser usado.

### Etapa 3: vendas completas (sem versão nova do app)

1. [ ] **[Gabriel]** Criar uma chave de API (somente leitura) no RevenueCat e colocar em `/etc/newzi/newzi.env`.
2. [ ] **[Claude]** Resumo diário lendo a API do RevenueCat: testes grátis, conversões, cancelamentos, reembolsos, receita, MRR.

### Etapa 4: eventos do app (versão 1.1, Apple e Google Play)

1. [ ] **[Gabriel]** Aprovar a lista de eventos da seção 9 e a decisão sobre a opção "Compartilhar dados de uso".
2. [ ] **[Claude]** Backend: `POST /me/events`, tabela `app_events`, limpeza após 90 dias, testes.
3. [ ] **[Claude]** App: envio em lote, `push_opened`, sessões, telas e eventos; testado no Android e no iPhone.
4. [ ] **[Claude]** Painel: tela Engajamento completa e taxa de abertura dos pushes.
5. [ ] **[Gabriel]** Atualizar a política de privacidade, o App Privacy no App Store Connect e a Segurança dos
   dados no Google Play (seção 10) **antes** de enviar a versão.
6. [ ] **[Gabriel]** Enviar a versão 1.1 para revisão nas duas lojas.

### Etapa 5: avisos automáticos

1. [ ] **[Claude]** Regras da seção 6.17 no resumo diário e um aviso por push ou e-mail para o Gabriel.

## 12. Decisões em aberto (Gabriel)

- [x] Subdomínio: **`painel.newzi.app`** (decidido em 2026-10-27).
- [x] Acesso: só `gabrielaraujo.n96@gmail.com`, **por senha própria do painel**, sem login Google
  (decidido em 2026-10-27, seção 2.3).
- [ ] Opção "Compartilhar dados de uso" no app: ter ou não, e se vem ligada por padrão.
- [ ] Retenção dos eventos brutos: 90 dias (sugerido) ou outro prazo.
- [x] Limite de avisos e promoções: **nenhum**. Envio na hora ou agendado, quantos quiser, com escolha do público
  (decidido em 2026-10-22, seção 8).
- [ ] Se o Firebase Console continua sendo usado para push depois da etapa 2.
- [ ] Premium pelo painel (7.1): avisar o usuário por push quando o Premium dado começar ou estiver para vencer,
  ou não avisar.
- [ ] Se os avisos automáticos (6.17) chegam por push no celular do Gabriel, por e-mail, ou só no painel.
