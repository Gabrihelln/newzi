# Implantação em VPS

Os arquivos nesta pasta são templates. Eles não instalam pacotes, não criam credenciais e não alteram um servidor remoto.

## Processos e dados

- `newzi-api.service` executa `backend/product_api.py` em `127.0.0.1:8090`.
- `newzi-worker.service` executa `engine/main.py --delivery-worker`, que mantém a atualização de fontes e o processamento agendado.
- O worker é dividido em papéis: `news` (coleta), `schedule`, `generation` (edições), `audio` (TTS), `notifications` (push), `breaking` (detecção de breaking news) e `retention`. Por padrão um processo roda todos. Para isolar filas, troque `newzi-worker` por instâncias de `newzi-worker@.service`, uma por grupo de papéis, separados por `:`. Exemplo: `newzi-worker@news`, `newzi-worker@audio` e `newzi-worker@schedule:generation:notifications:breaking:retention`. Cada papel precisa estar em pelo menos uma instância; dois processos com o mesmo papel não pegam o mesmo job.
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
8. Valide `https://api.seu-dominio/health`, `/ready` e `/health/worker`, autenticação Firebase, atualização de fontes, briefing, geração/playback de áudio e notificações antes de liberar o app.

## Segurança e operação

- Libere publicamente apenas SSH e HTTPS; a porta `8090` permanece acessível somente em loopback.
- Mantenha `/etc/newzi/` e `/var/lib/newzi/` fora do checkout e restrinja permissões.
- Faça backup consistente do SQLite e de `/var/lib/newzi/audio/`. Para SQLite em WAL, use a API de backup do SQLite ou pare os serviços durante cópia simples; copiar apenas o arquivo `.sqlite3` enquanto o processo grava pode perder transações do WAL.
- Backup diário do banco: `deploy/systemd/newzi-backup.timer` roda `deploy/backup/newzi_backup.py` às 06:30 UTC. O script copia o banco com a API de backup do SQLite (com os serviços no ar), confere a integridade da cópia, compacta e guarda as 14 mais recentes em `/var/lib/newzi-backup/copies`. Instale com `cp deploy/systemd/newzi-backup.* /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now newzi-backup.timer`; rode na hora com `systemctl start newzi-backup` e veja o resultado em `journalctl -u newzi-backup`.
- Cópia fora do servidor: com `NEWZI_BACKUP_REMOTE=destino:pasta` em `/etc/newzi/newzi.env` e o `rclone` configurado em `/var/lib/newzi-backup/rclone.conf` (`sudo -u newzi env RCLONE_CONFIG=/var/lib/newzi-backup/rclone.conf rclone config`), cada cópia também é enviada para lá e as de mais de 30 dias são apagadas no destino.
- Restauração: pare `newzi-api` e `newzi-worker`, guarde o banco atual com outro nome, descompacte a cópia (`gunzip -c copia.sqlite3.gz > /var/lib/newzi/product_backend.sqlite3`), remova os arquivos `-wal` e `-shm` antigos, ajuste o dono para `newzi:newzi` e suba os serviços.
- Monitore `systemctl`, `/health`, `/ready`, `/health/worker`, espaço em disco e logs. Teste a restauração do backup.
- `/health/worker` responde 200 quando cada papel do worker concluiu um ciclo nos últimos `WORKER_STALE_SECONDS` (padrão 300) e 503 quando algum está parado. A resposta traz `missing_roles`, a idade do último ciclo de cada processo, o tamanho e a idade das filas (geração, áudio, push, atualização manual) e há quanto tempo foi a última coleta de notícias. Não expõe IDs, hosts nem mensagens de erro; as falhas ficam no log do worker.
- Saúde das fontes: `python engine/main.py --source-health` lista cada feed com status e diagnóstico (`FEED_URL_NOT_FOUND`, `ACCESS_BLOCKED`, `FEED_ABANDONED`...). Feeds `BROKEN` ou abandonados precisam de URL nova em `engine/config/sources.yaml`.
- TTS: a `edge-tts` usa um endpoint não oficial. Com `AZURE_SPEECH_KEY` e `AZURE_SPEECH_REGION`, o Azure AI Speech oficial, que tem as mesmas vozes, assume automaticamente quando a `edge-tts` falha (por `TTS_FALLBACK_COOLDOWN_SECONDS`, padrão 10 min). Também pode ser o provedor principal, com `TTS_PROVIDER=azure-tts`, mas a troca regenera os áudios existentes.
- O worker aplica retenção uma vez por dia: remove variantes de áudio sem uso (7 dias), telemetria e jobs finalizados (30 dias) e matérias fora da janela (90 dias); briefings, entregas e itens salvos são preservados. Ajuste com `RETENTION_*` ou rode manualmente com `python -m newzi_backend.retention` (a partir de `backend/src`).
- O SQLite atende um único host. Para PostgreSQL, defina `DATABASE_URL=postgresql://usuario:senha@host:5432/newzi` (dependência `psycopg`, já em `requirements.txt`); API e worker criam e atualizam o esquema sozinhos. O armazenamento local de áudio continua exigindo um único host ou um volume compartilhado.

## Painel (Analytics Newzi)

O painel privado de métricas (`docs/ANALYTICS_NEWZI.md`) é um site estático em `admin/`, servido pelo Nginx em
`painel.newzi.app`, que conversa só com as rotas `/api/v1/admin/*` da API já existente. Não há serviço nem banco novos.

1. DNS: registro `A` `painel` apontando para o IP da VPS.
2. Senha: `/opt/newzi/.venv/bin/python /opt/newzi/backend/admin_password.py` pede a senha (mínimo 12 caracteres, sem
   mostrá-la) e imprime a linha `ADMIN_PASSWORD_HASH=...`. Em `/etc/newzi/newzi.env`, acrescente essa linha e
   `ADMIN_EMAIL=...` e `ADMIN_HOST=painel.newzi.app` (as rotas do painel respondem 404 em qualquer outro host, como
   `api.newzi.app`). Sem `ADMIN_EMAIL` e `ADMIN_PASSWORD_HASH` o painel fica desligado.
3. Nginx: copie `deploy/nginx/newzi-painel.conf.example` para `/etc/nginx/sites-available/newzi-painel`, crie o link em
   `sites-enabled`, rode `nginx -t`, recarregue e emita o certificado com `certbot --nginx -d painel.newzi.app`.
4. Reinicie `newzi-api` (a migração `0013_admin_panel` cria as tabelas do painel).

Trocar a senha: gere um hash novo com o mesmo script, substitua a linha e reinicie a API; as sessões abertas caem.
Cinco senhas erradas seguidas bloqueiam o login por 15 minutos; os acessos aparecem na tela Sistema do painel.

## Atualizações

Atualize o checkout sem remover `/var/lib/newzi` ou os arquivos privados em `/etc/newzi`. Instale dependências, reinicie os serviços e verifique health, logs e backups. As migrações de banco são versionadas (`backend/src/newzi_backend/migrations.py`, tabela `schema_versions`) e aplicadas automaticamente na inicialização da API e do worker, uma única vez e sob trava; faça backup antes de atualizar.
