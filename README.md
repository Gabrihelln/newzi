# NEWZI

Aplicativo React Native de notícias e briefings personalizados, com API Python, ingestão incremental, scheduler, worker e geração de áudio.

## Arquitetura

- `mobile/`: aplicativo React Native para Android e iOS.
- `backend/`: API de produto, autenticação Firebase Admin, persistência, agendamento de entregas, áudio e notificações.
- `engine/`: coleta de fontes, classificação/taxonomia, indexação incremental e composição de briefings.
- `firebase/`: configuração e documentação relacionadas ao Firebase.
- `videos/`: materiais de vídeo do projeto.
- `deploy/`: exemplos de serviços `systemd`, proxy Nginx e implantação em VPS.

A API e o worker usam o banco de produto configurado em `DATABASE_URL`. O engine mantém seu índice/cache em `engine/data/` por padrão; defina `NEWS_ENGINE_DATA_DIR` para persistir esses dados fora do checkout em produção. Áudios são armazenados em `backend/data/audio/` localmente ou em `AUDIO_STORAGE_ROOT`.

## Requisitos

- Python 3.11 ou superior.
- Node.js 22.11 ou superior e npm.
- Android: Android Studio, Android SDK e JDK 17.
- iOS: macOS, Xcode compatível com React Native 0.86, Watchman e CocoaPods; o target atual exige iOS 15.1 ou superior.
- Áudio `edge-tts`: acesso à internet, pacote Python `edge-tts`, `ffmpeg` e `ffprobe`.

Consulte o [ambiente do React Native 0.86](https://reactnative.dev/docs/0.86/set-up-your-environment) para versões de ferramentas e SDKs compatíveis.

## Configuração local

Na raiz do repositório, crie `.env` a partir do modelo e instale as dependências Python:

```sh
cp .env.example .env
python -m pip install -r requirements.txt
```

O backend carrega o `.env` da raiz. O processo do engine lê variáveis diretamente do ambiente; exporte-as no terminal do worker ou configure-as no supervisor. Nunca coloque credenciais privadas no controle de versão. Os bancos, sidecars SQLite e áudio local são ignorados pelo Git.

## Firebase

- Android usa `mobile/android/app/google-services.json`, configuração de cliente do Firebase; restrinja a chave às APIs e aos identificadores do aplicativo.
- O backend precisa de uma conta de serviço Firebase Admin privada quando `FIREBASE_AUTH_ENABLED=true`. Guarde o JSON fora do repositório e informe seu caminho absoluto em `GOOGLE_APPLICATION_CREDENTIALS`.
- Para iOS, registre o bundle ID `com.newzi.app` no Firebase e adicione o `GoogleService-Info.plist` ao target ativo do Xcode. Esse arquivo ainda precisa ser obtido para o projeto iOS.
- Configure o Web Client ID do Google em `mobile/src/config/socialAuth.ts`. O login Apple e os recursos de push precisam ser configurados e validados no target iOS/Firebase antes de uma distribuição.

## Backend

Execute a API a partir da raiz:

```sh
python backend/product_api.py
```

O padrão é `0.0.0.0:8090`. Verifique `/health` e `/ready`. Em produção, use HTTPS via proxy, `APP_ENV=production`, desative endpoints de desenvolvimento e configure autenticação e notificações com credenciais válidas.

## Worker e atualização de notícias

Em outro terminal, com as mesmas variáveis de ambiente do backend, execute o worker contínuo:

```sh
python engine/main.py --delivery-worker
```

O worker coordena atualização periódica de fontes, geração agendada de conteúdo e áudio e notificações. `NEWS_REFRESH_INTERVAL_SECONDS` define o intervalo de atualização; o padrão é 600 segundos. Os comandos de execução única e diagnóstico são ferramentas internas de operação, não etapas normais do usuário.

## Aplicativo mobile

```sh
cd mobile
npm ci
npm run start
```

Em outro terminal dentro de `mobile/`:

```sh
npm run android
```

No macOS, execute `pod install` em `mobile/ios/`, depois rode `npm run ios` a partir de `mobile/`. Abra o `.xcworkspace` gerado pelo CocoaPods para configurar o signing e as capabilities. Use `npm run typecheck` para validar os tipos TypeScript.

No Android Emulator, a API local usa `http://10.0.2.2:8090`; no iOS Simulator, `http://localhost:8090`. `mobile/src/config/devApi.ts` mantém o IP local usado pelo dispositivo físico atual; ajuste-o ao clonar em outra rede. Builds de produção precisam receber `__NEWS_ENGINE_ENV__` e `__NEWS_ENGINE_API_URL__` com um endpoint HTTPS real; o host de produção atual é apenas um placeholder.

## Produção em VPS

Os templates em `deploy/` executam API e worker separadamente como serviços `systemd`, com dados persistentes em `/var/lib/newzi`, atrás de Nginx/HTTPS. A configuração requer usuário Unix, arquivo de ambiente privado, banco/armazenamento durável, Firebase Admin, FCM e backup. Consulte [`deploy/README.md`](deploy/README.md); nenhum servidor é provisionado por este repositório.

## Documentação técnica

Veja `docs/` para arquitetura da API, autenticação, áudio, scheduler, taxonomia, integração mobile, Firebase, iOS e backup. Os documentos de direção visual e prototipagem foram removidos do conjunto operacional.
