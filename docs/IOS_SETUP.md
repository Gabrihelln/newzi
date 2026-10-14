# Newzi no iOS: guia para rodar e testar no iPhone

> **Para o Claude no Mac:** leia este documento inteiro antes de começar e execute as etapas **na ordem**.
> Cada etapa diz se é **[Claude]** (você faz no código/terminal) ou **[Gabriel]** (precisa da conta/navegador
> do dono do projeto: Apple, Firebase, Google). Quando chegar numa etapa [Gabriel], explique o que ele precisa
> fazer e espere ele confirmar. Ao terminar uma etapa, marque o `[ ]` como `[x]` neste arquivo.
> Não pule a seção **Regras do projeto**.

Este guia substitui `docs/IOS_BRINGUP_CHECKLIST.md` e a parte de "Mac execution" de
`docs/MOBILE_IOS_COMPATIBILITY.md`, que estão desatualizados (citam `react-native-sound`, trocado por
`react-native-video`).

---

## 1. Onde o projeto está

**Repositório:** `https://github.com/Gabrihelln/newzi` — todo o trabalho está na branch **`main`**.

| Parte | Pasta | Estado |
|---|---|---|
| Backend (API FastAPI) | `backend/` | Funcionando; 53 testes passando (`python -m pytest -q backend/tests`) |
| Engine (coleta de notícias, briefing, áudio, push) | `engine/` | Funcionando; worker com `python engine/main.py --delivery-worker` |
| App Android | `mobile/android/` | Funcionando e testado em aparelho real (Android, via USB) |
| **App iOS** | `mobile/ios/` | **Nunca foi compilado.** O projeto Xcode existe, mas faltam as configurações abaixo |

O app é **um só código React Native** (`mobile/src/`, TypeScript) para Android e iOS. Quase tudo já funciona
no iOS sem mudar código de tela; o que falta é **configuração nativa** (Xcode, Firebase, Apple) e testes.

### O app hoje (o que precisa funcionar no iPhone)
- Login por e-mail/senha (Firebase Auth). Login com Google está **desligado** nas duas plataformas
  (`GOOGLE_WEB_CLIENT_ID` vazio em `mobile/src/config/socialAuth.ts`).
- Onboarding (escolha de assuntos), Home (destaque, últimas, selo "Em alta"), Explorar (assuntos com ícones,
  card de futebol, tela Futebol com jogos e tabelas), Salvos, Perfil.
- Briefing diário em áudio (player com `react-native-video`, tocando em segundo plano e na tela de bloqueio).
- Notificações push (Firebase Cloud Messaging; no iOS passa pelo APNs da Apple).
- Modo escuro (automático pelo sistema ou escolhido em Perfil › Aparência).
- Perfil › Assinatura e plano (Básico × Premium). **A compra ainda não funciona em nenhuma plataforma**
  (ver seção 9).
- Cache offline (MMKV + TanStack Query) e armazenamento seguro do login (Keychain no iOS).

### Identificadores
- Bundle ID iOS / pacote Android: **`com.newzi.app`**
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

O app em modo desenvolvimento procura a API **no mesmo computador que serve o Metro**, na porta **8090**
(`mobile/src/config/env.ts`). Há duas opções:

### Opção A (recomendada): rodar o backend no Mac **[Claude]**
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

Verifique: `curl http://localhost:8090/health`.

### Opção B: usar o backend que roda no Windows
Em `mobile/src/config/devApi.ts`, preencha `DEV_API_URL = 'http://IP-DO-WINDOWS:8090'` (IP da rede local) e
libere a porta 8090 no firewall do Windows. **Não commite esse IP.**

---

## 5. Ajustes no projeto iOS **[Claude]** (o código que falta)

Faça na ordem. Depois de cada bloco, rode `cd mobile/ios && pod install` quando indicado e compile no
simulador (seção 6) para pegar erros cedo.

### 5.1 [ ] Fontes Inter e Newsreader
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

### 5.2 [ ] Firebase (login e push)
**[Gabriel]** No console do Firebase (projeto `newziapp`): *Configurações do projeto › Seus apps ›
Adicionar app › iOS*, bundle ID `com.newzi.app`, apelido "Newzi iOS". Baixe o **`GoogleService-Info.plist`**
e entregue ao Claude.

**[Claude]**
1. Coloque o arquivo em `mobile/ios/NewsEngineNative/GoogleService-Info.plist` e adicione ao target.
2. `AppDelegate.swift`: importe `FirebaseCore` e chame `FirebaseApp.configure()` no início de
   `application(_:didFinishLaunchingWithOptions:)`, **antes** de `factory.startReactNative`.
3. `Podfile`: o React Native Firebase exige frameworks estáticos. Logo abaixo de `prepare_react_native_project!`:
   ```ruby
   use_frameworks! :linkage => :static
   $RNFirebaseAsStaticFramework = true
   ```
   (remova o bloco `linkage = ENV['USE_FRAMEWORKS']` ou deixe-o coerente com isso). Confira na documentação do
   `@react-native-firebase` versão **26.4.0** se ainda é essa a recomendação para React Native 0.86.
4. `cd mobile/ios && pod install` e compile.
5. Teste o login por e-mail/senha no simulador.

### 5.3 [ ] Push (precisa do Apple Developer Program e de iPhone real)
**[Gabriel]**
1. Em https://developer.apple.com/account › *Keys* › **+**: crie uma chave com **Apple Push Notifications
   service (APNs)**. Baixe o `.p8` (só é possível baixar uma vez; **guarde fora do Git**) e anote o
   *Key ID* e o *Team ID*.
2. No Firebase › *Configurações do projeto › Cloud Messaging › App iOS*: envie o `.p8` com Key ID e Team ID.

**[Claude]**
1. Xcode › target › *Signing & Capabilities*: adicione **Push Notifications** e, em **Background Modes**,
   marque **Remote notifications** (o modo **Audio** já está ligado no `Info.plist`). Isso cria
   `NewsEngineNative.entitlements` com `aps-environment`.
2. O código JS já pede permissão e registra o token (`mobile/src/push/push.ts`, plataforma `IOS`), e o
   backend já envia com payload APNs (`backend/src/newzi_backend/notifications.py`). Confira se o
   `@react-native-firebase/messaging` precisa de algo no `AppDelegate` nesta versão (normalmente não, ele faz
   o swizzling sozinho).
3. Teste no iPhone: permitir notificações → em Perfil › Notificações, conferir; enviar um push de teste pelo
   backend (rotas de dev em `backend/src/newzi_backend/api/routes/dev.py`) com o app aberto (aviso dentro do
   app), em segundo plano e fechado; tocar na notificação deve abrir a tela certa
   (`mobile/src/navigation/notificationRouting.ts`).

### 5.4 [ ] Rede local no iPhone (modo desenvolvimento)
- iPhone e Mac na **mesma rede Wi-Fi**. O app em debug baixa o código do Metro pelo IP do Mac e usa o mesmo
  IP na porta 8090 para a API (automático, `mobile/src/config/env.ts`).
- O iOS pede permissão de **Rede Local** na primeira vez; aceite. Adicione ao `Info.plist` uma explicação:
  ```xml
  <key>NSLocalNetworkUsageDescription</key>
  <string>Usado em desenvolvimento para conectar ao computador que roda o Newzi.</string>
  ```
- O `Info.plist` já permite HTTP local (`NSAllowsLocalNetworking`) e bloqueia o resto (`NSAllowsArbitraryLoads`
  = false). **Não ligue `NSAllowsArbitraryLoads`.**
- Se o Mac tiver firewall ativo, libere as portas 8081 (Metro) e 8090 (API).

### 5.5 [ ] Áudio em segundo plano e tela de bloqueio
O player (`mobile/src/audio/AudioEngine.tsx`) usa `playInBackground`, `playWhenInactive`,
`ignoreSilentSwitch="ignore"` e `showNotificationControls`. No iPhone, valide:
- o áudio toca com a chave de silencioso ligada;
- continua com a tela bloqueada e com o app em segundo plano;
- os controles aparecem na tela de bloqueio/Central de Controle e funcionam (play/pause/avançar).
Se algo falhar, ajuste somente as props/configuração do `react-native-video` 6.19.3 para iOS.

### 5.6 [ ] Login com Google e Sign in with Apple (só quando o Gabriel decidir ligar)
Hoje o botão do Google está desligado. Quando for ligar:
- **[Gabriel]** criar o Web Client ID no Google Cloud/Firebase.
- **[Claude]** preencher `GOOGLE_WEB_CLIENT_ID`; no iOS passar também `iosClientId` em
  `GoogleSignin.configure` (`mobile/src/services/firebaseAuth.ts`) e adicionar ao `Info.plist` o URL scheme
  `REVERSED_CLIENT_ID` que vem no `GoogleService-Info.plist`.
- **Regra da Apple (diretriz 4.8):** se o app oferecer login com Google, **precisa oferecer também "Entrar com
  a Apple"**. Isso exige a capability *Sign in with Apple*, o provedor Apple ativado no Firebase Auth e o botão
  no app. Sem isso a App Store recusa.

### 5.7 [ ] Privacidade (PrivacyInfo.xcprivacy)
O arquivo `mobile/ios/NewsEngineNative/PrivacyInfo.xcprivacy` já existe. Depois do `pod install`, confira se
os motivos de uso de APIs sensíveis (UserDefaults, data de arquivos, espaço em disco, tempo de boot) estão
declarados para o app e para as bibliotecas (MMKV, Firebase, device-info). A App Store recusa o envio sem isso.

### 5.8 [ ] Endereço da API para builds de release
`mobile/src/config/env.ts` usa endereços de exemplo (`*.example.com`) para staging/produção, e um build de
**release** recusa iniciar com eles (por segurança). Antes do TestFlight, o backend precisa estar publicado
em HTTPS e esse endereço precisa ser configurado (o mesmo vale para o Android).

---

## 6. Compilar e rodar

### 6.1 [ ] Simulador
```sh
cd mobile
npm run start          # terminal 1: Metro
npm run ios            # terminal 2: compila e abre no simulador
```
Ou abra **`mobile/ios/NewsEngineNative.xcworkspace`** (o `.xcworkspace`, nunca o `.xcodeproj`) no Xcode e
rode o esquema `NewsEngineNative`. No simulador, `localhost:8090` já é o Mac. Push não funciona no simulador.

### 6.2 [ ] iPhone real
1. Conecte o iPhone por cabo, desbloqueie e confie no Mac. Em iOS 16+, ative
   *Ajustes › Privacidade e Segurança › Modo de Desenvolvedor*.
2. Xcode › target › *Signing & Capabilities*: marque *Automatically manage signing* e escolha o **Team**
   do Gabriel. O bundle ID continua `com.newzi.app`.
3. Escolha o iPhone como destino e rode. Na primeira vez, no iPhone:
   *Ajustes › Geral › VPN e Gerenciamento de Dispositivos* › confiar no desenvolvedor.
4. Com o Metro rodando no Mac e os dois na mesma Wi-Fi, o app carrega o código e acessa a API sozinho.

### Problemas comuns
| Sintoma | Causa provável |
|---|---|
| `pod install` falha | Node fora do PATH do Xcode: confira `mobile/ios/.xcode.env` (`NODE_BINARY=$(command -v node)`); rode de novo |
| "No bundle URL present" | Metro não está rodando ou o iPhone não alcança o Mac (Wi-Fi, firewall, permissão de Rede Local) |
| App abre mas diz que não conecta ao servidor | Backend parado ou fora de `0.0.0.0:8090`; teste `http://IP-DO-MAC:8090/health` no Safari do iPhone |
| Erro de assinatura | Team não selecionado ou bundle ID já usado em outra conta |
| Fonte diferente do Android | Etapa 5.1 incompleta |

---

## 7. Roteiro de teste no iPhone **[Claude + Gabriel]**

Marque cada item depois de testar no **aparelho real**, em modo **claro e escuro**:
- [ ] Cadastro, login, sair, abrir de novo com a sessão restaurada
- [ ] Onboarding: escolher assuntos e "acompanhar tudo"
- [ ] Home: destaque, últimas notícias, selo "Em alta", abrir notícia, salvar, avaliar
- [ ] Explorar: busca, assuntos com ícones próprios, "Ver mais assuntos", card de futebol → tela Futebol
      (abas Jogos e Tabelas, filtro por campeonato)
- [ ] Salvos: lista, organizados por assunto, continuar lendo
- [ ] Briefing: tocar, pausar, avançar, velocidade, capítulos, tela de bloqueio, segundo plano, silencioso
- [ ] Perfil: editar perfil, preferências de conteúdo, briefing diário (horário; "Adicionar outro horário"
      abre o aviso Premium), voz, notificações, aparência (automático/claro/escuro), assinatura e plano
- [ ] Push: permissão, recebimento com app aberto/em segundo plano/fechado, toque abrindo a tela certa
- [ ] Sem internet: o app mostra o conteúdo em cache
- [ ] Áreas seguras: nada escondido pelo notch/Dynamic Island nem pela barra inferior; teclado não cobre campos
- [ ] Imagens: fotos em WebP aparecem (o iOS usa o proxy de WebP em `ArticleImage.tsx`)

Registre problemas encontrados ao final deste arquivo (seção 11).

---

## 8. Publicar para testes (TestFlight)
**[Gabriel]** No App Store Connect: *Apps › +* › novo app iOS, bundle ID `com.newzi.app`, nome Newzi,
idioma principal Português (Brasil).
**[Claude]** Xcode › *Product › Archive* (esquema Release, destino "Any iOS Device") › *Distribute App ›
App Store Connect*. Requer as etapas 5.7 e 5.8.
**[Gabriel]** Em TestFlight, adicionar testadores. Antes da App Store: textos, capturas de tela, rótulos de
privacidade ("Privacidade do app") e política de privacidade publicada.

---

## 9. Assinatura Premium no iOS (próxima fase, não fazer agora)
O plano (definido com o Gabriel):
- **Básico** (grátis): 1 horário de briefing por dia.
- **Premium** mensal (R$ 14,90) ou anual (R$ 119,90): até 4 horários de briefing escolhidos pela pessoa,
  assuntos sem limite, salvos ilimitados/offline, alertas personalizados. **Sem teste grátis.**
- Tudo fica em **Perfil › Assinatura e plano** (`mobile/src/components/SubscriptionScreen.tsx`) e no aviso
  `PremiumSheet.tsx`. O backend já tem a tabela `subscriptions`, `GET /api/v1/me/subscription` e a regra
  em `backend/src/newzi_backend/subscriptions.py`; `BILLING_ENABLED` está desligado.

O que falta (em andamento primeiro no Android, depois no iOS):
1. Biblioteca **RevenueCat** (`react-native-purchases`) no app, com login pelo `uid` do Firebase.
2. **Android:** produto `newzi_premium` (planos `mensal`/`anual`) na Play Console.
   **iOS:** no App Store Connect, grupo de assinaturas "Newzi Premium" com os produtos mensal e anual, os
   mesmos preços, aceitar o *Paid Apps Agreement* e preencher dados bancários/fiscais; ligar os produtos ao
   mesmo entitlement `premium` no RevenueCat; capability **In-App Purchase** no Xcode.
3. Webhook do RevenueCat → backend gravando `subscriptions` (backend precisa estar em HTTPS público).
4. Briefings em vários horários: hoje o banco permite **um briefing por usuário por dia**
   (`UNIQUE(user_id,briefing_date)` em `generation_jobs` e `UNIQUE(user_id,local_date)` em
   `user_briefing_deliveries`, ver `backend/src/newzi_backend/migrations.py` e `scheduling.py`). Precisa de
   nova migração, agendador por horário e ajustes na Home/configuração do briefing.
5. Termos de uso e política de privacidade publicados (`TERMS_URL`, `PRIVACY_URL` no `.env`).

---

## 10. Outras pendências do projeto (contexto)
- Backend e worker ainda rodam só em máquina local; falta publicar em servidor com HTTPS (`deploy/` tem
  nginx e systemd prontos).
- Android: configuração de produção, build de release assinado, Crashlytics.
- Login com Google desligado (ver 5.6).
- Copa do Brasil não está no plano gratuito do football-data.org; a tabela da Libertadores também não.

---

## 11. Registro de andamento no Mac
(Claude: anote aqui, com data, o que foi feito, o que falhou e o que ficou para depois.)
