# Newzi no iOS: guia para rodar e testar no iPhone

> **Para o Claude no Mac:** leia este documento inteiro antes de começar e execute as etapas **na ordem**.
> Cada etapa diz se é **[Claude]** (você faz no código/terminal) ou **[Gabriel]** (precisa da conta/navegador
> do dono do projeto: Apple, Firebase, Google). Quando chegar numa etapa [Gabriel], explique o que ele precisa
> fazer e espere ele confirmar. Ao terminar uma etapa, marque o `[ ]` como `[x]` neste arquivo.
> Não pule a seção **Regras do projeto**.

## 0. Ao voltar ao Mac: comece por aqui (atualizado em 2026-10-18, à noite, depois do splash novo)

Desde a última sessão no Mac (registro de 2026-10-18 na seção 11, commit `f6c4678`), o `main` recebeu todos os
commits de `e3af3c0` até o último (Esportes, alertas dos times, Home só com imagens, animação do logo e splash),
feitos e testados **só no Android**. Nenhum deles mexe em código nativo do iOS nem traz pod novo além dos dois
citados no passo 2. Faça nesta ordem e marque cada item:

1. [x] **Código** [Claude]: `git pull` em `main`; `cd mobile && npm ci`. O `postinstall` roda o `patch-package`
   (`mobile/patches/react-native-video+6.19.3.patch`, que só muda o código **Android** do player; no iOS não
   faz nada). Se o `npm ci` reclamar do patch, veja se o arquivo continua com fim de linha LF (`.gitattributes`).
2. [x] **Pods** [Claude]: `cd mobile/ios && pod install` (use `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8` se der erro de
   Unicode). Entram dois pods novos: **`react-native-image-picker` 8.2.1** (foto do perfil) e
   **`@callstack/liquid-glass` 0.8.2** (`LiquidGlass`, barra de navegação). O Liquid Glass usa APIs do iOS 26:
   compile com o **Xcode 26**. Confira também que o `RNAppleAuthentication` continua no `Podfile.lock`.
3. [x] **Compilar e instalar** no iPhone (seção 6.2) e rodar `npm run typecheck` em `mobile/`.
4. [x] **Testar o que mudou** (roteiro abaixo) em modo claro **e** escuro; anotar na seção 11 o que falhar.
5. [x] **Pendências antigas** que continuam abertas: 5.5 (áudio em segundo plano e tela de bloqueio), 5.6 passo 4
   (login Google e Apple, sair/entrar, excluir conta Apple), 6.1 (simulador) e o roteiro completo da seção 7.
6. [x] Se tudo estiver bem, **novo build no TestFlight** (seção 8): aumentar `CURRENT_PROJECT_VERSION` antes.

### 0.1 O que mudou e precisa ser testado no iPhone
| Área | O que conferir no iPhone | Onde está o código |
|---|---|---|
| **Notificações (onboarding)** | Na etapa "Ative as notificações", com "Resumo diário"/"Notícias urgentes" ligados, "Ativar" mostra o pedido de permissão do iOS; recusar não trava o cadastro; "Agora não" pula sem pedir | `OnboardingScreen.tsx` (etapa 7), `push/push.ts` |
| **Perfil › Notificações** | Cartão azul (permitido) ou laranja com "Ativar permissão" (bloqueado/sem resposta: no iOS, "Ativar" abre os Ajustes depois da 1ª recusa); cada chave salva sozinha; ao voltar dos Ajustes o cartão muda | `NotificationSettingsScreen.tsx` |
| **Push** | Não existe mais aviso dentro do app com ele aberto (decisão do Gabriel). Notícia urgente: título = manchete, texto = resumo curto da matéria; tocar abre a matéria. Resumo diário: "10 notícias selecionadas para você · 5 min" | backend `breaking.py`, `notifications.py`; `navigation/notificationRouting.ts` |
| **Novidades e promoções** | O app inscreve todo aparelho nos tópicos FCM `novidades` e `promocoes` ao abrir; testar com uma campanha do Firebase Console para o tópico; tocar com dado `screen=Subscription` (ou `story_id`) abre a tela | `push/topics.ts` |
| **Login** | Botão da Apple só no iPhone; Google e Apple funcionando (5.6) | `AuthScreens.tsx`, `services/firebaseAuth.ts` |
| **Segurança e privacidade** | "Alterar senha" (senha atual + nova + confirmação) para contas de e-mail; contas Google/Apple mostram aviso no lugar | `ProfileScreen.tsx` |
| **Dados pessoais / Editar perfil** | Cartão com foto ou iniciais, selos, "Este aparelho: iPhone · ativo agora", zona de perigo; **Trocar foto** pela câmera e pela galeria (o iOS pede permissão com os textos `NSCameraUsageDescription` e `NSPhotoLibraryUsageDescription` já no `Info.plist`); a foto nova aparece no cabeçalho | `AccountScreen.tsx`, `EditProfileScreen.tsx`, `services/profilePhoto.ts` |
| **Resumo diário** | Cartão "Próximo resumo" muda ao mexer no horário; barra "Salvar alterações" fixa só com mudança; prévia (▶) da voz toca | `DailyBriefingSettingsScreen.tsx` |
| **Preferências de conteúdo** | Cartão de resumo, busca, chips, domínios com progresso, "Acompanhar tudo", contador de alterações e confirmação ao sair sem salvar | `ContentPreferencesScreen.tsx` |
| **Cabeçalho e busca** | Mesmo cabeçalho (logo + avatar de 42 px) em Início, Explorar, Salvos e Perfil, sem pular ao trocar de aba; **nenhuma lupa** em lugar nenhum (a busca é só o campo do Explorar) | `AppHeader.tsx` |
| **Barra de navegação** | Quase até as bordas, ícones espalhados, player no meio, sombra; **Liquid Glass no iOS 26** (5.6.1); nada encoberto pela barra inferior do iPhone | `navigation/RootNavigator.tsx` |
| **Mascote** | O robô saiu do app inteiro: avatar sem foto = iniciais; capas = "capa da edição" desenhada (folhas sobre degradê de manhã/tarde/noite) | `EditionCover.tsx` |
| **Explorar** | "Seus assuntos" com "Editar", cards "Em alta" com ranking, "+N hoje" e ícone do assunto, ordenação em pílula | `ExploreScreen.tsx` |
| **Player e Capítulos** | Capa da edição, fechar/compartilhar, selo "Agora", controles capítulo · −15 · play · +15 · capítulo; Capítulos com faixa "Tocando" e card inteiro clicável | `BriefingAudioScreen.tsx`, `AudioChaptersScreen.tsx` |
| **Tela de bloqueio / Central de Controle** | O "Now Playing" mostra a **capa da edição** como capa de álbum (o iOS baixa `https://api.newzi.app/api/v1/covers/edition.png?...`), título "Resumo da tarde · 18 out" e artista "Newzi". Confira também se os botões de avançar/voltar pulam 15 s (no Android o patch ajustou; no iOS o `react-native-video` define o salto sozinho: se não for 15 s, ajustar só para iOS) | `audio/AudioEngine.tsx`, `audio/player.ts`, backend `covers.py` |
| **Salvar** | Ícone de salvar fica totalmente preenchido ao salvar (cards, leitura, player, Salvos) | `Icon.tsx` (`filled`) |
| **Esportes (futebol)** | Card de futebol do Explorar → Esportes: "Meus times" (anel vermelho e placar ao vivo), jogos ao vivo em **card com degradê azul** (150°, `#0F2C5C`→`#163E80`; no intervalo mais apagado), escudos do mesmo tamanho e **nome inteiro do time** (até 2 linhas, ex. "Red Bull Bragantino"), próximos jogos por dia e campeonato com estrela e sino; Tabelas (pílulas, Jogos com rodada, Tabela com zonas, últimos resultados e seus times); Times favoritos (busca, **grade de 4 colunas sem sobra à direita**, avisos de início, gols, resultado e notícias). Escudos oficiais vêm de `https://api.newzi.app/api/v1/football/crests/{id}.png?v=2` (o servidor recorta e escala todos para o mesmo quadrado) | `FootballScreen.tsx`, `FootballTablesScreen.tsx`, `FavoriteTeamsScreen.tsx`, `FootballParts.tsx`, backend `football*.py` |
| **Alertas do seu time (push)** | Quem marca um time favorito recebe: "Começou: X x Y", "Gol do X!", "Fim de jogo: …" (com a posição na tabela) e notícias do time (até 3 por dia, fora do horário de silêncio). No iOS não há canal: chegam agrupadas pelo `thread_id` `team_alerts`. **Teste sem esperar um jogo**: no VPS, `systemd-run --wait --pipe --collect -p User=newzi -p EnvironmentFile=/etc/newzi/newzi.env -p WorkingDirectory=/opt/newzi /opt/newzi/.venv/bin/python /opt/newzi/backend/football_test_alerts.py EMAIL --team Flamengo` envia as 4 para a conta. **Deixe o app em segundo plano** (com o app aberto o push não aparece, nem no Android). Tocar num alerta de jogo abre Esportes; a notícia abre a matéria | backend `football_alerts.py`, `backend/football_test_alerts.py`; `navigation/notificationRouting.ts` |
| **Só notícias com imagem** | Destaques, Últimas notícias, Explorar, assuntos e busca **não mostram notícia sem foto** (filtro no backend `latest_news` e, na Home, também no app). "Destaques de hoje" **não tem mais "Ver todos"** (Últimas notícias mantém) | backend `product_backend.py`; `HomeScreen.tsx` |
| **Puxar a Home para atualizar** | Sem spinner do sistema: **o próprio logo do cabeçalho anima**, o símbolo gira (e encolhe de leve) e o nome "newzi" esmaece e volta, até terminar; parado, o logo fica idêntico ao de antes. No iOS conferir que o `UIRefreshControl` não aparece (`tintColor="transparent"`) e que o conteúdo desce e volta sem salto estranho; o `progressViewOffset` só vale no Android | `AppHeader.tsx` (`refreshing`), `HomeScreen.tsx`, `assets/onboarding/header-*.png` |
| **Splash de abertura** | No lugar de "Carregando…": ícone do Newzi com as três folhas balançando como papel ao vento e o nome "newzi" subindo embaixo (design em `design/splash`, que não vai para o git). Fica rodando até a conta carregar (internet lenta = mais balanços), no mínimo 1 s; respeita o tema claro/escuro e "Reduzir movimento". A tela nativa (`LaunchScreen.storyboard`, cor `LaunchBackground` `#F7FBFF`/`#0B1426` + `LaunchIcon`) já tem as mesmas cores: conferir que não há flash branco nem salto feio entre o ícone nativo (100 pt) e o splash (132 pt); se incomodar, trocar o `LaunchIcon` por fundo liso | `components/SplashScreen.tsx`, `App.tsx`, `assets/splash/` |

Este guia substitui `docs/IOS_BRINGUP_CHECKLIST.md` e a parte de "Mac execution" de
`docs/MOBILE_IOS_COMPATIBILITY.md`, que estão desatualizados (citam `react-native-sound`, trocado por
`react-native-video`).

---

## 1. Onde o projeto está

**Repositório:** `https://github.com/Gabrihelln/newzi` — todo o trabalho está na branch **`main`**.

| Parte | Pasta | Estado |
|---|---|---|
| Backend (API FastAPI) | `backend/` | No ar em `https://api.newzi.app`; 91 testes passando (`python -m pytest -q backend/tests`) |
| Engine (coleta de notícias, briefing, áudio, push) | `engine/` | Funcionando; worker com `python engine/main.py --delivery-worker` |
| App Android | `mobile/android/` | Funcionando e testado em aparelho real (Android, via USB) |
| **App iOS** | `mobile/ios/` | Compila e roda no iPhone; build 4 (versão 1.0) no TestFlight. Faltam os testes da seção 0 e as pendências da 5.x |

O app é **um só código React Native** (`mobile/src/`, TypeScript) para Android e iOS. Quase tudo já funciona
no iOS sem mudar código de tela; o que falta é **configuração nativa** (Xcode, Firebase, Apple) e testes.

### O app hoje (o que precisa funcionar no iPhone)
- Login por e-mail/senha (Firebase Auth), **Google** (Android e iPhone) e **Apple** (só iPhone); troca de senha
  dentro do app. "Esqueci minha senha" com o app deslogado ficou para depois (decisão do Gabriel).
- Onboarding (assuntos e avisos), Home (destaque, últimas, selo "Em alta"), Explorar (busca, assuntos, "Em alta",
  card de futebol, tela Futebol com jogos e tabelas), Salvos, Perfil (dados pessoais com foto, resumo diário,
  preferências de conteúdo, notificações, segurança). **Sem mascote** e **sem botões de busca** fora do Explorar.
- Briefing diário em áudio (player com `react-native-video`, tocando em segundo plano e na tela de bloqueio).
- Notificações push (Firebase Cloud Messaging; no iOS passa pelo APNs da Apple): resumo diário, notícias urgentes
  (3+ veículos, só para quem segue o assunto) e novidades/promoções enviadas pelo Firebase Console a tópicos.
- Modo escuro (automático pelo sistema ou escolhido em Perfil › Aparência).
- Perfil › Assinatura e plano (Básico × Premium). **A compra ainda não funciona em nenhuma plataforma**
  (ver seção 9).
- Cache offline (MMKV + TanStack Query, sem faixa de "Sem conexão" por decisão do Gabriel) e armazenamento
  seguro do login (Keychain no iOS).

### Identificadores
- Bundle ID iOS: **`app.newzi.ios`** / pacote Android: **`com.newzi.app`**. São diferentes porque o
  `com.newzi.app` ficou preso ao Personal Team gratuito usado nos primeiros testes e a Apple não libera
  para outra equipe. **O bundle ID do iOS não pode mudar depois de publicado.**
- Equipe Apple (Developer Program): **`3253WT48Q3`** (conta `gabrielaraujo.n96@icloud.com`)
- Nome exibido: **Newzi**
- Projeto Firebase: **`newziapp`**
- Alvo Xcode: `NewsEngineNative` (nome interno antigo; **não renomeie**, o módulo JS se chama `Newzi`)
- iOS mínimo: **15.1**

---

## 2. Regras do projeto (valem para qualquer mudança)

1. **Nada de Expo** (sem Expo Go, EAS ou pacotes `expo-*`). O projeto é React Native CLI puro.
2. **Não altere o visual do modo claro.** Cores do tema ficam em `mobile/src/theme/index.ts`; cores
   específicas do modo claro usam `colors.tone('#hexOriginal', colors.token)`.
3. **Nunca commite segredos:** `.env`, chaves `.p8`/`.p12`, contas de serviço `*.json` do Firebase Admin,
   certificados, perfis de provisionamento. O `.gitignore` já cobre esses casos; confira antes de cada commit.
   O `GoogleService-Info.plist` é configuração de cliente (como o `google-services.json` do Android, que já
   está no repositório) e pode ser commitado.
4. **Não mexa no comportamento do Android** ao ajustar o iOS. Depois de qualquer mudança em `mobile/src`,
   rode `npm run typecheck` em `mobile/`.
5. Só faça commit/push quando o Gabriel pedir.
6. Escreva o código no mesmo estilo dos arquivos vizinhos.

---

## 3. Preparar o Mac

### 3.1 Ferramentas **[Gabriel instala / Claude confere]**
| Ferramenta | Versão | Como |
|---|---|---|
| macOS | atual | — |
| **Xcode** | o mais recente estável da App Store | depois de instalar, abra uma vez e aceite os componentes; rode `sudo xcode-select -s /Applications/Xcode.app` |
| Homebrew | atual | https://brew.sh |
| **Node** | **22.11 ou superior** (Windows usa 22.14) | `brew install node@22` ou nvm |
| Watchman | atual | `brew install watchman` |
| **CocoaPods** | atual | `brew install cocoapods` |
| Python | **3.11** (para rodar o backend no Mac) | `brew install python@3.11` |
| ffmpeg | atual (áudio do briefing) | `brew install ffmpeg` |

Confira: `xcodebuild -version`, `node -v`, `pod --version`, `python3.11 --version`.

### 3.2 Conta Apple **[Gabriel]**
- **Para rodar no próprio iPhone em testes simples**, basta um Apple ID grátis no Xcode
  (Xcode › Settings › Accounts). Limitações: o app expira em 7 dias e **push não funciona**.
- **Para push, Sign in with Apple, TestFlight e App Store**, é obrigatório o **Apple Developer Program**
  (US$ 99/ano) em https://developer.apple.com/programs/. Pode levar de 1 a 2 dias para aprovar.
  Recomendado assinar logo, porque push e o teste completo dependem disso.

### 3.3 Código **[Claude]**
```sh
git clone https://github.com/Gabrihelln/newzi.git
cd newzi                 # a branch main já vem selecionada
cd mobile && npm ci
```

---

## 4. Backend para os testes

O app, também em modo desenvolvimento, usa o **backend online `https://api.newzi.app`**, que roda 24h na VPS
(`mobile/src/config/env.ts`). Não é preciso rodar backend no Mac: confira `https://api.newzi.app/health` no
Safari do iPhone e pule para a seção 5.

Só se for testar uma mudança de backend antes de subir para a VPS:

### Opcional: rodar o backend no Mac **[Claude]**
```sh
cd newzi
cp .env.example .env            # o Gabriel preenche os valores (ver abaixo)
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python backend/product_api.py   # API em 0.0.0.0:8090 (confira API_HOST=0.0.0.0 no .env)
# em outro terminal, com o mesmo venv:
python engine/main.py --delivery-worker
```
**[Gabriel]** O `.env` não está no Git. Copie os valores do `.env` da máquina Windows
(`G:\Projetos\news\.env`): Firebase Admin (`GOOGLE_APPLICATION_CREDENTIALS` apontando para o JSON da
conta de serviço, que também precisa ser copiado para fora do repositório), `FOOTBALL_DATA_TOKEN` e o resto.
Os bancos SQLite (`backend/data/`, `engine/data/`) também não vão para o Git: ou o Mac começa com bancos
novos (o worker coleta notícias em alguns minutos), ou copie as pastas do Windows.

Verifique: `curl http://localhost:8090/health`. Para o app usar esse backend, preencha em
`mobile/src/config/devApi.ts` `DEV_API_URL = 'http://localhost:8090'` (simulador) ou `'http://IP-DO-MAC:8090'`
(iPhone na mesma Wi-Fi). **Não commite essa alteração.**

---

## 5. Ajustes no projeto iOS **[Claude]** (o código que falta)

Faça na ordem. Depois de cada bloco, rode `cd mobile/ios && pod install` quando indicado e compile no
simulador (seção 6) para pegar erros cedo.

### 5.1 [x] Fontes Inter e Newsreader
O app usa as fontes `Inter` (interface) e `Newsreader` (títulos editoriais). No Android elas estão em
`mobile/android/app/src/main/assets/fonts/` (`Inter.ttf`, `Newsreader.ttf`); **no iOS não estão no target**,
então o iPhone mostraria a fonte do sistema.
1. Crie `mobile/ios/NewsEngineNative/Fonts/` e copie os dois `.ttf` para lá.
2. Adicione os arquivos ao target `NewsEngineNative` (aparecem em *Build Phases › Copy Bundle Resources*).
3. No `Info.plist`, adicione:
   ```xml
   <key>UIAppFonts</key>
   <array>
     <string>Inter.ttf</string>
     <string>Newsreader.ttf</string>
   </array>
   ```
4. Confira que os nomes de família são `Inter` e `Newsreader` (são variable fonts; `fontWeight` deve variar).
   Se o iOS registrar outro nome, ajuste somente para iOS em `mobile/src/theme/index.ts` com `Platform.select`.

Observação: existe uma pasta antiga `mobile/ios/ios/` ignorada pelo Git; não use.

### 5.2 [x] Firebase (login e push)
**[Gabriel]** No console do Firebase (projeto `newziapp`): *Configurações do projeto › Seus apps ›
Adicionar app › iOS*, bundle ID `app.newzi.ios`, apelido "Newzi iOS". Baixe o **`GoogleService-Info.plist`**
e entregue ao Claude.

**[Claude]**
1. Coloque o arquivo em `mobile/ios/NewsEngineNative/GoogleService-Info.plist` e adicione ao target.
2. `AppDelegate.swift`: importe `FirebaseCore` e chame `FirebaseApp.configure()` no início de
   `application(_:didFinishLaunchingWithOptions:)`, **antes** de `factory.startReactNative`.
3. `Podfile`: o React Native Firebase exige frameworks estáticos. Logo abaixo de `prepare_react_native_project!`:
   ```ruby
   use_frameworks! :linkage => :static
   $RNFirebaseAsStaticFramework = true
   $RNFirebaseDisableSPM = true
   ```
   (A versão 26 do RNFirebase usa Swift Package Manager por padrão, o que gera símbolos duplicados com
   frameworks estáticos; `$RNFirebaseDisableSPM` faz o Firebase vir pelo CocoaPods.)
   (remova o bloco `linkage = ENV['USE_FRAMEWORKS']` ou deixe-o coerente com isso). Confira na documentação do
   `@react-native-firebase` versão **26.4.0** se ainda é essa a recomendação para React Native 0.86.
4. `cd mobile/ios && pod install` e compile.
5. Teste o login por e-mail/senha no simulador.

### 5.3 [x] Push (precisa do Apple Developer Program e de iPhone real)
**[Gabriel]**
1. Em https://developer.apple.com/account › *Keys* › **+**: crie uma chave com **Apple Push Notifications
   service (APNs)**. Baixe o `.p8` (só é possível baixar uma vez; **guarde fora do Git**) e anote o
   *Key ID* e o *Team ID*.
2. No Firebase › *Configurações do projeto › Cloud Messaging › App iOS*: envie o `.p8` com Key ID e Team ID.

**[Claude]**
1. Feito: `NewsEngineNative/NewsEngineNative.entitlements` (`aps-environment`, ligado por
   `CODE_SIGN_ENTITLEMENTS`) e `remote-notification` em `UIBackgroundModes`. A assinatura automática ligou o
   Push no App ID `app.newzi.ios` (perfil "iOS Team Provisioning Profile: app.newzi.ios"). No archive para a
   App Store, o Xcode troca `development` por `production` sozinho.
2. O código JS já pede permissão e registra o token (`mobile/src/push/push.ts`, plataforma `IOS`), e o
   backend já envia com payload APNs (`backend/src/newzi_backend/notifications.py`). Confira se o
   `@react-native-firebase/messaging` precisa de algo no `AppDelegate` nesta versão (normalmente não, ele faz
   o swizzling sozinho). Conferido: não precisa; ele registra o APNs sozinho.
4. Teste rápido sem a VPS: Firebase › *Messaging* › nova campanha › *Mensagens do Firebase Notifications*,
   app iOS `app.newzi.ios`. As rotas de dev de push ficam desligadas em produção.
3. Teste no iPhone: permitir notificações → em Perfil › Notificações, conferir; enviar um push de teste com o
   app aberto (**não aparece nada**: o aviso dentro do app foi removido de propósito), em segundo plano e
   fechado; tocar na notificação deve abrir a tela certa (`mobile/src/navigation/notificationRouting.ts`).
   Para testar num aparelho só: Firebase Console › Messaging › "Enviar mensagem de teste" com o token do
   aparelho (o token está em `push_devices` no banco da VPS).

### 5.4 [x] Rede local no iPhone (modo desenvolvimento)
- iPhone e Mac na **mesma rede Wi-Fi**. O app em debug baixa o código do Metro pelo IP do Mac; a API é a
  online (`https://api.newzi.app`), salvo se `DEV_API_URL` apontar para um backend local.
- O iOS pede permissão de **Rede Local** na primeira vez; aceite. Adicione ao `Info.plist` uma explicação:
  ```xml
  <key>NSLocalNetworkUsageDescription</key>
  <string>Usado em desenvolvimento para conectar ao computador que roda o Newzi.</string>
  ```
- O `Info.plist` já permite HTTP local (`NSAllowsLocalNetworking`) e bloqueia o resto (`NSAllowsArbitraryLoads`
  = false). **Não ligue `NSAllowsArbitraryLoads`.**
- Se o Mac tiver firewall ativo, libere a porta 8081 (Metro) e, só com backend local, a 8090 (API).

### 5.5 [x] Áudio em segundo plano e tela de bloqueio
O player (`mobile/src/audio/AudioEngine.tsx`) usa `playInBackground`, `playWhenInactive`,
`ignoreSilentSwitch="ignore"` e `showNotificationControls`. No iPhone, valide:
- o áudio toca com a chave de silencioso ligada;
- continua com a tela bloqueada e com o app em segundo plano;
- os controles aparecem na tela de bloqueio/Central de Controle e funcionam (play/pause/avançar);
- a **capa da edição** aparece como capa de álbum e o título é "Resumo da manhã/tarde/noite · dia" (seção 0.1).
Se algo falhar, ajuste somente as props/configuração do `react-native-video` 6.19.3 para iOS. O patch em
`mobile/patches/` é só do Android (notificação de mídia única, ícone do app, saltos de 15 s).

### 5.6 [x] Login social: Google e Apple (código e configuração prontos em 2026-10-18; falta testar no Mac)
Regra do produto: **Android só tem Google; iPhone tem Google e Apple** (o botão da Apple só aparece no iOS,
`appleSignInAvailable` em `mobile/src/services/firebaseAuth.ts`). Pela **diretriz 4.8** da Apple, um app com
login do Google precisa oferecer também "Entrar com a Apple" no iPhone, e é o que o app faz.

**Já feito no código [Claude]**
- Google: `loginWithGoogle` (`@react-native-google-signin/google-signin` 16.1.4); o `iosClientId` vem sozinho
  do `GoogleService-Info.plist`.
- Apple: login nativo com `@invertase/react-native-apple-authentication` 2.5.1 (nonce + `AppleAuthProvider`
  do Firebase); o nome da pessoa (que a Apple manda só no primeiro acesso) vai para o perfil.
- Entitlement `com.apple.developer.applesignin` já está em `NewsEngineNative.entitlements`.
- Excluir conta revoga o acesso da Apple antes (`revokeAppleAccessIfLinked`, exigência 5.1.1(v)).
- E-mail oculto da Apple (`@privaterelay.appleid.com`) funciona como e-mail normal no backend.

**[Gabriel] Firebase e Apple — feito em 2026-10-18** (Google já testado no Android; Sign in with Apple marcado no App ID)
1. Firebase › Authentication › *Sign-in method*: ativar **Google** (e-mail de suporte) e **Apple** (só ativar;
   para app nativo de iPhone não precisa de Services ID nem chave).
2. Configurações do projeto › app Android `com.newzi.app` › *Adicionar impressão digital*: SHA-1 de debug
   `5E:8F:16:06:2E:A3:CD:2C:4A:0D:54:78:76:BA:A6:F3:8C:AB:F6:25` (e, quando existir, o da chave de release).
3. Baixar de novo `google-services.json` (para `mobile/android/app/`) e `GoogleService-Info.plist` (para
   `mobile/ios/NewsEngineNative/`): só com o Google ativado eles trazem os IDs de cliente.
4. Authentication › Google › *Configuração do SDK da Web*: copiar o **ID do cliente da Web** e passar ao Claude.

**[Claude] no Mac**
1. Feito: `GOOGLE_WEB_CLIENT_ID` em `mobile/src/config/socialAuth.ts`.
2. Feito: URL scheme `REVERSED_CLIENT_ID` (`com.googleusercontent.apps.300896912437-5puthemqhigh4g5f3v3l1hhqmhesvbga`) no `Info.plist`.
3. `cd mobile/ios && pod install`; no Xcode, conferir em *Signing & Capabilities* que **Sign in with Apple**
   aparece (a assinatura automática liga a capability no App ID `app.newzi.ios`).
4. Testar no iPhone: entrar com Google, entrar com Apple (inclusive "Ocultar meu e-mail"), sair e entrar de
   novo, e excluir uma conta criada com a Apple.

### 5.6.1 [x] Barra de navegação em Liquid Glass (iOS 26)
A barra flutuante usa `@callstack/liquid-glass` 0.8.2 (`LiquidGlassView`, `mobile/src/navigation/RootNavigator.tsx`):
no iOS 26 ela vira vidro; em iOS anterior (e no Android, onde a biblioteca não tem código nativo) continua a barra
sólida com sombra. **[Claude] no Mac:** `pod install`, compilar com o Xcode 26 e conferir a barra num iPhone com
iOS 26, nos temas claro e escuro.

### 5.7 [x] Privacidade (PrivacyInfo.xcprivacy)
O arquivo `mobile/ios/NewsEngineNative/PrivacyInfo.xcprivacy` já existe. Depois do `pod install`, confira se
os motivos de uso de APIs sensíveis (UserDefaults, data de arquivos, espaço em disco, tempo de boot) estão
declarados para o app e para as bibliotecas (MMKV, Firebase, device-info). A App Store recusa o envio sem isso.

### 5.8 [x] Endereço da API para builds de release
Todos os ambientes usam `https://api.newzi.app` (`mobile/src/config/env.ts`), publicado na VPS.

### 5.9 [x] Exigências da revisão da App Store
- **Excluir conta (diretriz 5.1.1(v))**: Perfil › Dados pessoais › Excluir conta chama `DELETE /api/v1/me`,
  que apaga os dados do usuário no banco e o usuário no Firebase Auth. **O backend da VPS precisa ser
  atualizado** para a rota existir.
- **Premium escondido no iOS** até a compra pela App Store funcionar (diretriz 2.1): `PREMIUM_OFFERED` em
  `mobile/src/config/store.ts` esconde "Assinatura e plano" e "Adicionar outro horário". Os textos da
  assinatura citam a loja da plataforma (`STORE_NAME`). Ao ligar a compra no iOS (seção 9), remover essa trava.
- **Só iPhone** (`TARGETED_DEVICE_FAMILY = 1`): a Apple não testa no iPad nem pede capturas de iPad.
- **`ITSAppUsesNonExemptEncryption = false`** no `Info.plist` (o app só usa HTTPS).
- **Dynamic Island**: a tela "Outros resumos" (Histórico) não tinha área segura no topo; corrigido.

---

## 6. Compilar e rodar

### 6.1 [x] Simulador
```sh
cd mobile
npm run start          # terminal 1: Metro
npm run ios            # terminal 2: compila e abre no simulador
```
Ou abra **`mobile/ios/NewsEngineNative.xcworkspace`** (o `.xcworkspace`, nunca o `.xcodeproj`) no Xcode e
rode o esquema `NewsEngineNative`. O simulador usa a API online. Push não funciona no simulador.

### 6.2 [x] iPhone real
1. Conecte o iPhone por cabo, desbloqueie e confie no Mac. Em iOS 16+, ative
   *Ajustes › Privacidade e Segurança › Modo de Desenvolvedor*.
2. Xcode › target › *Signing & Capabilities*: marque *Automatically manage signing* e escolha o **Team**
   do Gabriel (`3253WT48Q3`, a do Developer Program). O bundle ID é `app.newzi.ios`.
3. Escolha o iPhone como destino e rode. Na primeira vez, no iPhone:
   *Ajustes › Geral › VPN e Gerenciamento de Dispositivos* › confiar no desenvolvedor.
4. Com o Metro rodando no Mac e os dois na mesma Wi-Fi, o app carrega o código e acessa a API online sozinho.

### Problemas comuns
| Sintoma | Causa provável |
|---|---|
| `pod install` falha | Node fora do PATH do Xcode: confira `mobile/ios/.xcode.env` (`NODE_BINARY=$(command -v node)`); rode de novo |
| "No bundle URL present" | Metro não está rodando ou o iPhone não alcança o Mac (Wi-Fi, firewall, permissão de Rede Local) |
| App abre mas diz que não conecta ao servidor | Teste `https://api.newzi.app/health` no Safari do iPhone; se falhar, veja `systemctl status newzi-api` na VPS. Com `DEV_API_URL` local: backend parado ou fora de `0.0.0.0:8090` |
| Erro de assinatura | Team não selecionado ou bundle ID já usado em outra conta |
| Fonte diferente do Android | Etapa 5.1 incompleta |
| Erro de compilação no `LiquidGlass` | Xcode anterior ao 26 (as APIs de vidro são do iOS 26 SDK): use o Xcode 26 |
| "Trocar foto" não abre a câmera | Falta `pod install` (`react-native-image-picker`) ou a permissão de câmera foi negada em Ajustes › Newzi |
| `pod install` quebra com `Unicode Normalization not appropriate for ASCII-8BIT` | Locale do terminal: rode `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 pod install` |
| Debug não linka: `Undefined symbols … Sealable`/`getDebugName` | `Pods/React-Core-prebuilt` ficou na versão Release (depois de um archive) sem o arquivo `.last_build_configuration`. Em `mobile/ios/Pods`: `printf Release > React-Core-prebuilt/.last_build_configuration` e `node ../../node_modules/react-native/scripts/replace-rncore-version.js -c Debug -r 0.86.3 -p "$PWD"` |

---

## 7. Roteiro de teste no iPhone **[Claude + Gabriel]**

Marque cada item depois de testar no **aparelho real**, em modo **claro e escuro**:
- [x] Cadastro, login, sair, abrir de novo com a sessão restaurada
- [x] Onboarding: escolher assuntos e "acompanhar tudo"
- [x] Home: destaque, últimas notícias, selo "Em alta", abrir notícia, salvar, avaliar
- [x] Explorar: busca pelo campo (única busca do app), "Seus assuntos" › Editar, cards "Em alta", ordenação,
      "Ver mais assuntos", card de futebol → tela Futebol (abas Jogos e Tabelas, filtro por campeonato)
- [x] Salvos: lista, organizados por assunto, continuar lendo
- [x] Briefing: tocar, pausar, −15/+15 s, capítulo anterior/próximo, velocidade, Capítulos (tocar no card leva ao
      capítulo; pausar pela faixa do topo), mini player, tela de bloqueio com capa, segundo plano, silencioso
- [x] Perfil: dados pessoais, editar perfil (foto pela câmera e pela galeria, nome), preferências de conteúdo,
      resumo diário (horário, tamanho, idioma, cobertura, áudio e voz), notificações, segurança (alterar senha),
      aparência (automático/claro/escuro). Assinatura e plano ficam escondidos no iOS (5.9); recursos Premium aparecem enquanto `PREMIUM_ENFORCED` estiver desligado (seção 9)
- [x] Push: permissão (onboarding e Perfil), recebimento em segundo plano/fechado (aberto não mostra nada),
      toque abrindo a tela certa; campanha do Console para o tópico `novidades`
- [x] Sem internet: o app mostra o conteúdo em cache (sem faixa amarela)
- [x] Barra de navegação: Liquid Glass no iOS 26; nada coberto pela barra
- [x] Áreas seguras: nada escondido pelo notch/Dynamic Island nem pela barra inferior; teclado não cobre campos
- [x] Imagens: fotos em WebP aparecem (o iOS usa o proxy de WebP em `ArticleImage.tsx`)

Registre problemas encontrados ao final deste arquivo (seção 11).

---

## 8. Publicar para testes (TestFlight)
**[Gabriel]** No App Store Connect: *Apps › +* › novo app iOS, bundle ID `app.newzi.ios`, nome Newzi,
idioma principal Português (Brasil).
**[Claude]** Xcode › *Product › Archive* (esquema Release, destino "Any iOS Device") › *Distribute App ›
App Store Connect*. Requer as etapas 5.7 e 5.8.
**[Gabriel]** Em TestFlight, adicionar testadores. Antes da App Store: textos, capturas de tela, rótulos de
privacidade ("Privacidade do app") e política de privacidade publicada.

---

## 9. Newzi Premium (recursos prontos; a compra é a próxima fase)
O plano (definido com o Gabriel em 2026-10-19). O grátis continua dando conta de se informar todo dia; o Premium
deixa o Newzi mais seu, mais rápido e mais completo. Voz, velocidade e o áudio guardado ao tocar seguem iguais
para todos.

| Área | Básico (grátis) | Premium |
|---|---|---|
| Resumo | 1 por dia, no horário escolhido | Até 3 por dia (cada um com horário e tema), "Gerar agora" (5/dia) e versão estendida |
| Áudio | Voz, velocidade e cache de quem já tocou | Baixar para ouvir offline, fila contínua, ouvir as matérias salvas |
| iPhone | Widget "Destaques do dia" pequeno | Tamanhos médio e grande, widget por assunto e por time (iOS 17), placar na tela de bloqueio |
| Futebol | 1 time, início, gols, resultado e notícias | Até 10 times, lembrete 15 min antes, resumo do jogo em áudio |
| Alertas | Urgentes e assuntos seguidos | Palavras-chave (até 20) e "acompanhar história" (7 dias) |
| Salvos e histórico | Salvos sem limite e 7 dias de histórico | Coleções, offline, histórico completo e busca nos resumos |

Escalação, cartão vermelho e pênalti ficam para depois: o plano grátis da football-data.org não traz eventos do
jogo (precisa de plano pago ou de outra API).

**Onde está:** o servidor decide tudo em `backend/src/newzi_backend/subscriptions.py` (`LIMITS`, `FEATURES`,
`GET /api/v1/me/entitlements`); o app lê isso em `mobile/src/services/premium.tsx` e abre o `PremiumSheet` pelo
`requestPremium`. Recursos: `briefing_slots.py`, `collections.py`, `alerts.py`, `match_audio.py`,
`saved_audio.py`, `live_activities.py` (backend); `ExtraBriefingsCard`, `OnDemandBriefing`, `Collections`,
`PersonalAlerts`, `AudioQueueSection`, `audio/queue.ts`, `services/offline.ts`, `services/iosWidgets.ts` (app);
`mobile/ios/NewziWidgets/` (widgets e Live Activity) e `NewziWidgetBridge.swift` (ponte nativa).

**Travas desligadas:** com `PREMIUM_ENFORCED` desligado (padrão) todo mundo usa tudo, como antes. Para testar os
dois lados: `PREMIUM_ENFORCED=true` no `.env` da VPS, reiniciar API e worker, e
`python backend/premium_test_account.py EMAIL grant|revoke|status`. No iOS, enquanto `PREMIUM_OFFERED` for
falso, um recurso travado some (nada de oferta que não dá para comprar, diretriz 2.1).

**Deploy do backend:** `pip install -r requirements.txt` (firebase-admin 6.9, para o token da Live Activity). As
migrações `0011_briefing_slots` e `0012_premium_features` rodam sozinhas na primeira subida.

### 9.1 [x] Widgets e Live Activities no iPhone **[Gabriel + Claude]**
1. **[Gabriel]** No developer.apple.com (ou deixando o Xcode criar com a assinatura automática): App Group
   **`group.app.newzi.ios`** ligado aos App IDs `app.newzi.ios` e `app.newzi.ios.NewziWidgets` (o novo alvo da
   extensão). Sem isso o build no iPhone falha na assinatura.
2. **[Claude]** O alvo `NewziWidgets` (iOS 16.1+) já está no projeto e embutido no app; o app ganhou o App Group,
   `NSSupportsLiveActivities` e o esquema de URL `newzi://`. Compilar no iPhone e conferir: widget pequeno, médio
   e grande, widgets "Seu assunto" e "Meu time" (iOS 17), e um jogo ao vivo de um time favorito na tela de
   bloqueio e na Dynamic Island.
3. A Live Activity iniciada pelo servidor (push-to-start) precisa de iOS 17.2+; abaixo disso o app inicia a
   atividade quando é aberto durante o jogo. Os pushes vão pelo FCM: a chave APNs já está no Firebase.

### 9.2 [ ] A compra (App Store pelo RevenueCat)
Feito em 2026-10-19 (Windows):
- **App Store Connect:** contrato de apps pagos, banco e impostos (Brasil e W-8BEN) enviados; grupo "Newzi Premium"
  com `newzi_premium_monthly` (R$ 14,90) e `newzi_premium_annual` (R$ 119,90), sem oferta nem teste grátis, Family
  Sharing desligado; chave de compras (`.p8`, guardada fora do repositório).
- **RevenueCat:** projeto Newzi, app "Newzi iOS" (`app.newzi.ios`) com a chave `.p8`; notificações do servidor da
  App Store (URL do RevenueCat em produção e sandbox, versão 2); produtos, entitlement `premium` e oferta `default`
  com `$rc_monthly` e `$rc_annual`.
- **App:** `react-native-purchases` 10.11.0 (`mobile/src/services/purchases.ts`), logado com o **id do backend**
  (`users.id`, não o `uid` do Firebase); a tela Assinatura e plano compra e restaura com o preço da loja; o aviso de
  cancelar a assinatura na tela de excluir conta; `PREMIUM_OFFERED` liberado no iOS.
- **Backend:** `revenuecat.py`, webhook `POST /api/v1/webhooks/revenuecat` e `POST /api/v1/me/subscription/sync`.

Falta:
1. [x] **[Gabriel + Claude]** Webhook no RevenueCat (Integrations › Webhooks) com a URL
   `https://api.newzi.app/api/v1/webhooks/revenuecat` e o mesmo valor de `REVENUECAT_WEBHOOK_AUTH`; chave secreta
   (`REVENUECAT_SECRET_KEY`) e `BILLING_ENABLED=true` no `.env` da VPS.
2. [x] **[Claude, no Mac]** `npm ci`, `pod install` (entra o pod `RNPurchases`), capability **In-App Purchase** no alvo
   do app, `CURRENT_PROJECT_VERSION` +1 e build no TestFlight. Testar compra, restauração e cancelamento com uma
   conta sandbox (Usuários e Acesso › Contas de sandbox) e conferir a compra em RevenueCat › Customers.
3. **[Gabriel]** Print da tela de compra e nota em "Informações para a equipe de revisão" de cada assinatura; as
   assinaturas vão para revisão junto com a primeira versão do app.
4. [x] Termos de uso e política de privacidade publicados: `TERMS_URL=https://newzi.app/termos.html` e
   `PRIVACY_URL=https://newzi.app/privacidade.html` no `.env` da VPS (a Apple recusa sem eles).
5. Ligar `PREMIUM_ENFORCED` quando as compras estiverem funcionando.
6. **Android:** chave do Google no RevenueCat (`API_KEYS.android` em `purchases.ts`) e produtos na Play Console.

---

## 10. Outras pendências do projeto (contexto)
- Backend e worker rodam na VPS em `https://api.newzi.app` (`deploy/` tem nginx e systemd).
- Android: configuração de produção, build de release assinado, Crashlytics.
- Login social: Google no Android; Google e Apple no iPhone (ver 5.6).
- "Esqueci minha senha" com o app deslogado: decidir depois (provável e-mail de redefinição do próprio Firebase).
- Fotos de perfil ficam em `/var/lib/newzi/avatars` na VPS e ainda **não entram no backup diário**.
- Regra 4.5.4 da App Store (push de promoção pede aceite no app): hoje a permissão do sistema é o único filtro;
  se a revisão reclamar, criar o aceite e o jeito de desistir.
- Copa do Brasil não está no plano gratuito do football-data.org; a tabela da Libertadores também não.

---

## 11. Registro de andamento no Mac
(Claude: anote aqui, com data, o que foi feito, o que falhou e o que ficou para depois.)

### 2026-10-14 — primeira compilação no iMac (Intel, macOS, Xcode 26.1)
**Feito**
- Ferramentas: Xcode 26.1, CocoaPods 1.16.2 e Node 25.2.1 já estavam instalados. O Homebrew não tem
  pacotes prontos para Mac Intel e compila tudo do código-fonte (horas), então: Python 3.11 via `uv`
  (`uv python install 3.11`, venv em `.venv/`) e `ffmpeg`/`ffprobe` 9.0.2 prontos de https://evermeet.cx/ffmpeg/
  em `/usr/local/bin`. Watchman não foi instalado (o Metro funciona sem ele).
- 5.1 Fontes no target e em `UIAppFonts`; o iOS reconhece `Inter` e `Newsreader` sem ajuste no tema.
- 5.2 `GoogleService-Info.plist` no target, `FirebaseApp.configure()` no `AppDelegate`, Podfile com
  frameworks estáticos e `$RNFirebaseDisableSPM = true`. Cadastro e login por e-mail funcionando no iPhone.
- `react-native-svg` 15.15.3 → 15.15.4: a 15.15.3 não compila com RN 0.86 (`RNSVGImage.mm`); a 15.15.4 só
  muda esse arquivo iOS, o Android não é afetado.
- Ícone: o `AppIcon.appiconset/Contents.json` tinha a chave `"platform": "ios"`, que o Xcode não reconhece,
  e o app saía sem ícone. Tela de abertura nova: ícone centralizado sobre `#F7FBFF` (claro) / `#0B1426`
  (escuro), como a do Android 12+.
- 5.4 `NSLocalNetworkUsageDescription`. Sem a permissão de Rede Local o app usa o bundle embutido e procura a
  API em `localhost` ("Sem conexão com o Newzi"): conferir *Ajustes › Privacidade e Segurança › Rede Local*.
- 5.7 `pod install` agregou ao `PrivacyInfo.xcprivacy` os motivos das bibliotecas (UserDefaults, data de
  arquivos, tempo de boot, espaço em disco) e colocou o arquivo no target.
- 6.2 Assinatura automática com o Personal Team gratuito (`YY79UQMX9Q`): app no iPhone 14 Pro Max (iOS 26.6),
  mas expira em 7 dias e não recebe push. Ao entrar no Apple Developer Program, trocar o Team no Xcode.
- App: horário do briefing escolhido numa roda dentro do card (onboarding e Perfil › Briefing diário), sem
  teclado; botão "Sair da conta" no fim da tela Perfil (saiu de Dados pessoais).
- Backend no Mac: 51 de 53 testes passam. `test_contract` falha porque o golden guarda o caminho de áudio do
  Windows; `test_delivery_worker_batches_audio_and_push…` depende do horário (falha perto da meia-noite UTC).

**Pendente**
- Algo fica escondido pelo Dynamic Island (falta identificar a tela).
- 5.3 Push (precisa do Apple Developer Program), 5.5 áudio em segundo plano, 6.1 simulador, seção 7.
- O Firebase deixa de publicar versões novas no CocoaPods depois de outubro de 2026: planejar a migração para SPM.

### 2026-10-15 — conta do Apple Developer Program
- Team trocado para a equipe paga `3253WT48Q3` (`gabrielaraujo.n96@icloud.com`).
- O Xcode recusou registrar `com.newzi.app` na equipe paga ("not available"), porque o Personal Team já o
  registrou. Bundle ID do iOS trocado para `app.newzi.ios`, com novo app iOS no Firebase e novo
  `GoogleService-Info.plist`. O Android continua `com.newzi.app`.
- Exigências da revisão (5.9): excluir conta no app e no backend, Premium escondido no iOS, só iPhone,
  `ITSAppUsesNonExemptEncryption`, área segura da tela Histórico.
- 5.3 Push, parte do código: entitlements, `remote-notification` e Push no App ID. Falta a chave APNs no
  Firebase e o teste no iPhone.
- Push do Firebase Console chegou no iPhone (aberto, segundo plano, fechado e tela bloqueada). O push do
  resumo pela VPS não chegou, por dois motivos corrigidos: (1) o aparelho só era registrado no backend no
  onboarding ou em Perfil › Notificações; agora o app registra ao abrir com a sessão ativa, se a permissão
  já foi dada (`registerDeviceIfPermitted` em `mobile/src/push/push.ts`); (2) mudar o horário não movia o
  resumo do dia; agora move, se o push dele ainda não saiu. Precisa atualizar a VPS e testar de novo.
- "Últimas notícias" parecia parada: a lista era ordenada por relevância (frescor numa escala de 30 dias) e as
  "Em alta" iam sempre ao topo. Agora sai da mais recente para a mais antiga. O golden do contrato foi
  regenerado e normaliza caminhos do Windows com espaço: os 55 testes do backend passam.
- TestFlight: primeiro build enviado (versão 1.0, build 1), pelo terminal: `xcodebuild archive` (Release,
  `generic/platform=iOS`) e `xcodebuild -exportArchive` com `method=app-store-connect`, `destination=upload`,
  `teamID=3253WT48Q3`. Avisos de dSYM do React/Hermes são esperados (frameworks pré-compilados). **A cada novo
  envio, aumentar `CURRENT_PROJECT_VERSION`** (o build); a Apple recusa número repetido.

### 2026-10-18 — login social no iPhone (build local de Debug)
- `npm ci` e `pod install`: entrou o pod `RNAppleAuthentication` 2.5.1.
- `@invertase/react-native-apple-authentication` importa `prop-types` só no arquivo do iOS e não declara a
  dependência; o empacotamento do JS falhava no iPhone. `prop-types` 15.8.1 entrou no `package.json`.
- O app assinado traz `com.apple.developer.applesignin` e `aps-environment`. Build de Debug instalado no
  iPhone pelo terminal (`xcodebuild … -destination id=<UDID>` e `xcrun devicectl device install app`).
- Falta: testar Google, Apple, sair/entrar e excluir conta Apple (5.6, passo 4) e as telas novas vindas do Android.

### 2026-10-18 (noite) — Esportes, splash e build 4 no TestFlight
- `npm ci` (patch do `react-native-video` aplicado) e `pod install`: entraram `LiquidGlass` e
  `react-native-image-picker` 8.2.1; `RNAppleAuthentication` continua. `npm run typecheck` passou.
- Build de Debug no iPhone 14 Pro Max (iOS 26.6.2) com Xcode 26.1: o roteiro da seção 0.1 ficou igual ao Android.
  O produto do build se chama `Newzi.app` (`build/dd/Build/Products/Debug-iphoneos/Newzi.app`).
- `CURRENT_PROJECT_VERSION` 3 → 4; `xcodebuild archive` (Release) e `-exportArchive` com `ExportOptions.plist`:
  upload aceito pelo App Store Connect (versão 1.0, build 4). Falta o Gabriel liberar o build para os testadores.

### 2026-10-19 — Newzi Premium e build 5 no TestFlight
- Recursos Premium (seção 9) e a extensão `NewziWidgets` (widgets e Live Activity) entraram no projeto. O Xcode
  registrou sozinho o App Group `group.app.newzi.ios` e o App ID `app.newzi.ios.NewziWidgets` na assinatura
  automática (`-allowProvisioningUpdates`).
- `CURRENT_PROJECT_VERSION` 4 → 5 (app e extensão precisam ter o mesmo); archive e upload aceitos (versão 1.0, build 5).
- **Limite deste Mac:** o iPhone foi para o iOS 27 e o Xcode 26.1 não instala nele pelo cabo (`devicectl` falha com
  `0xE8000003`; o `xcodebuild` não aceita o aparelho como destino). O Xcode 27 exige macOS Tahoe 26.6 e chip Apple,
  e o iMac Pro 2017 (Intel) não roda o Tahoe. Daqui em diante, testes no iPhone são pelo TestFlight (ou por um Mac
  com chip Apple). Compilar para `generic/platform=iOS` e para o simulador continua funcionando.

### 2026-10-19 (noite) — compra no sandbox e build 6 no TestFlight
- `npm ci` e `pod install`: entraram `RNPurchases` 10.11.0, `PurchasesHybridCommon` 19.5.0 e `RevenueCat` 5.92.0.
  In-App Purchase não tem chave de entitlement (já vem no App ID); nada a mudar no `.entitlements`.
- Webhook do RevenueCat ativo na VPS (sem `Authorization` a API responde 401, não 503).
- Teste num **iPhone 8 (iOS 16.7.16)**, que o Xcode 26.1 ainda instala: build de Release para o aparelho com
  `-allowProvisioningUpdates -allowProvisioningDeviceRegistration` (registra o aparelho) e instalação com
  `ios-deploy` (o `devicectl` só fala com iOS 17+). Compra do mensal na conta sandbox, renovação em 5 min e
  cancelamento em Ajustes › App Store › Conta sandbox apareceram no RevenueCat › Customers.
- `CURRENT_PROJECT_VERSION` 5 → 6 (app e extensão); archive e upload aceitos (versão 1.0, build 6). Os avisos
  de dSYM do React, ReactNativeDependencies e hermesvm (frameworks pré-compilados) não impedem o envio.
- `PREMIUM_ENFORCED` não depende do app: o app segue `GET /me/entitlements`. Ligar no `.env` da VPS e reiniciar
  API e worker.

### 2026-10-19 (noite) — revisão para a App Store e build 7
- Testes das seções 5, 7 e 9.1 confirmados pelo Gabriel; páginas legais no ar (`termos.html`, `privacidade.html`).
- `NewziWidgets/PrivacyInfo.xcprivacy`: a extensão lê o App Group pelo `UserDefaults` (motivo `1C8F.1`); sem ele a
  Apple manda o aviso ITMS-91053.
- Idioma do app em pt-BR: `developmentRegion` do projeto, `CFBundleDevelopmentRegion`, `CFBundleLocalizations` e
  `pt-BR.lproj/InfoPlist.strings` (botões do sistema em português e a App Store lista "Português").
- Fase "Remove development-only Info.plist keys" no alvo do app: no Release tira `NSLocalNetworkUsageDescription`,
  que só serve ao Debug ligado a um computador na mesma Wi-Fi (`devApi.ts`).
- Barra de navegação: vidro `regular` (antes `clear`) com tinta de 55% no claro e no escuro; o vidro transparente
  deixava os nomes das abas ilegíveis sobre as imagens.
- A foto do perfil só muda pelo botão "Trocar foto" (Editar perfil): o selo da câmera saiu da foto em Perfil, Dados
  pessoais e Editar perfil (`ProfileAvatar` não tem mais `onCamera`).
- `CURRENT_PROJECT_VERSION` 6 → 7; archive e upload aceitos (versão 1.0, build 7), o build escolhido para a revisão.

