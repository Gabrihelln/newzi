# Implantação em VPS

Os arquivos nesta pasta são templates. Eles não instalam pacotes, não criam credenciais e não alteram um servidor remoto.

## Processos e dados

- `newzi-api.service` executa `backend/product_api.py` em `127.0.0.1:8090`.
- `newzi-worker.service` executa `engine/main.py --delivery-worker`, que mantém a atualização de fontes e o processamento agendado.
- Ambos reiniciam após falha e rodam como o usuário Unix `newzi`.
- Banco do produto, índice do engine, MP3s e temporários persistem em `/var/lib/newzi/`.
- `newzi-api.conf.example` publica a API pelo Nginx com HTTPS.

## Preparar o servidor

1. Instale Python 3.11+, Nginx, `ffmpeg`/`ffprobe` e as bibliotecas de sistema necessárias ao `firebase-admin` e ao `edge-tts`.
2. Crie o usuário/grupo `newzi`, coloque o checkout em `/opt/newzi` e garanta que esse usuário possa ler o código.
3. Crie `/opt/newzi/.venv`, instale `requirements.txt` e configure o Firebase Admin JSON fora do checkout, em `/etc/newzi/firebase-admin.json`. Restrinja `/etc/newzi` a `root:newzi` (`0750`) e o JSON a `root:newzi` (`0640`) para o serviço poder lê-lo sem torná-lo público.
4. Instale os modelos de tradução (CPU, ~130 MB), usados para narrar notícias de outro idioma no idioma do briefing:
   `sudo -u newzi env TRANSLATION_MODELS_DIR=/var/lib/newzi/models/translation /opt/newzi/.venv/bin/python -m newzi_backend.translation --download`
   (execute a partir de `/opt/newzi/backend/src` ou com `PYTHONPATH=/opt/newzi/backend/src`). Sem os modelos, essas notícias são narradas no idioma original.
5. Crie `/etc/newzi/newzi.env` com permissões `0600`, dono `root`, contendo pelo menos:

```dotenv
APP_ENV=production
API_HOST=127.0.0.1
API_PORT=8090
ENABLE_DEV_ENDPOINTS=false
DATABASE_URL=sqlite:////var/lib/newzi/product_backend.sqlite3
NEWS_ENGINE_DATA_DIR=/var/lib/newzi/engine
AUDIO_STORAGE_ROOT=/var/lib/newzi/audio
NEWS_AUDIO_TMP=/var/lib/newzi/tmp
TRANSLATION_MODELS_DIR=/var/lib/newzi/models/translation
NEWS_REFRESH_INTERVAL_SECONDS=600
FIREBASE_AUTH_ENABLED=true
FIREBASE_PROJECT_ID=YOUR_FIREBASE_PROJECT_ID
GOOGLE_APPLICATION_CREDENTIALS=/etc/newzi/firebase-admin.json
NOTIFICATIONS_ENABLED=false
PUSH_PROVIDER=development
TTS_PROVIDER=edge-tts
TTS_VOICE=newzi_lucas
```

Com `PUSH_PROVIDER=fcm`, o backend envia pelo Firebase Admin SDK usando a conta de serviço de `GOOGLE_APPLICATION_CREDENTIALS`; o SDK gera e renova sozinho o token OAuth. `FCM_PROJECT_ID` é opcional (padrão: `FIREBASE_PROJECT_ID`). Firebase Admin e FCM devem usar o mesmo projeto.

6. Ajuste `server_name` e os caminhos do certificado no Nginx. Emita o certificado TLS, instale o arquivo de configuração e valide com `nginx -t`.
7. Copie os dois `.service` para `/etc/systemd/system/`, execute `systemctl daemon-reload`, habilite `newzi-api` e `newzi-worker` e verifique seus logs com `journalctl -u newzi-api -u newzi-worker`.
8. Valide `https://api.seu-dominio/health` e `/ready`, autenticação Firebase, atualização de fontes, briefing, geração/playback de áudio e notificações antes de liberar o app.

## Segurança e operação

- Libere publicamente apenas SSH e HTTPS; a porta `8090` permanece acessível somente em loopback.
- Mantenha `/etc/newzi/` e `/var/lib/newzi/` fora do checkout e restrinja permissões.
- Faça backup consistente do SQLite e de `/var/lib/newzi/audio/`. Para SQLite em WAL, use a API de backup do SQLite ou pare os serviços durante cópia simples; copiar apenas o arquivo `.sqlite3` enquanto o processo grava pode perder transações do WAL.
- Monitore `systemctl`, `/health`, `/ready`, espaço em disco, filas de áudio e logs. Teste a restauração do backup.
- O worker aplica retenção uma vez por dia: remove variantes de áudio sem uso (7 dias), telemetria e jobs finalizados (30 dias) e matérias fora da janela (90 dias); briefings, entregas e itens salvos são preservados. Ajuste com `RETENTION_*` ou rode manualmente com `python -m newzi_backend.retention` (a partir de `backend/src`).
- O SQLite atende um único host. Para PostgreSQL, defina `DATABASE_URL=postgresql://usuario:senha@host:5432/newzi` (dependência `psycopg`, já em `requirements.txt`); API e worker criam e atualizam o esquema sozinhos. O armazenamento local de áudio continua exigindo um único host ou um volume compartilhado.

## Atualizações

Atualize o checkout sem remover `/var/lib/newzi` ou os arquivos privados em `/etc/newzi`. Instale dependências, reinicie os serviços e verifique health, logs e backups. As migrações de banco são versionadas (`backend/src/newzi_backend/migrations.py`, tabela `schema_versions`) e aplicadas automaticamente na inicialização da API e do worker, uma única vez e sob trava; faça backup antes de atualizar.
