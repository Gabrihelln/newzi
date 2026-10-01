# Secrets and environments

## Environment model

`APP_ENV` is required conceptually at process startup and accepts only `development`, `staging` or `production`. Invalid values fail fast. Production cannot expose DEV routes or use the development push provider while notifications are enabled.

| Variable | Consumer | Development | Staging | Production | Secret | Mobile-safe |
|---|---|---|---|---|---|---|
| `APP_ENV` | backend/mobile build | `development` | `staging` | `production` | no | yes |
| `DATABASE_URL` | backend | local SQLite | private SQLite/VPS | private SQLite/VPS | no | no |
| `ENABLE_DEV_ENDPOINTS` | backend | `true` | `false` | `false` | no | no |
| `AUDIO_ENABLED` | backend | `true` | explicit | explicit | no | no |
| `NOTIFICATIONS_ENABLED` | backend | `true` | explicit | explicit | no | no |
| `PUSH_PROVIDER` | backend | `development` | `fcm` | `fcm` | no | no |
| `FCM_PROJECT_ID` | FCM server | optional | secret-managed config | secret-managed config | yes | no |
| `FCM_ACCESS_TOKEN` | FCM server | absent | secret manager/ADC | secret manager/ADC | yes | no |
| `CORS_ALLOW_ORIGINS` | future web boundary | empty | allowlist | allowlist | no | no |
| `__NEWS_ENGINE_API_URL__` | mobile build config | emulator/local | staging URL | production URL | no | yes |
| `google-services.json` | Android Firebase client | environment file | environment file | environment file | public client config, never server credentials | packaged client only |
| `GoogleService-Info.plist` | iOS Firebase client | environment file | environment file | environment file | public client config, never server credentials | packaged client only |

Never commit passwords, service-account JSON, APNs private keys, FCM server credentials, keystores or real `.env` files. Rotate FCM credentials in the provider/secret manager, deploy the replacement, verify delivery, then revoke the old credential. Mobile client config is environment-specific and must not contain server credentials.

The Android release build refuses to reuse the debug signing key; provide a real keystore only through protected build variables. iOS signing, provisioning and Firebase files are prepared on a Mac in the bring-up checklist.
