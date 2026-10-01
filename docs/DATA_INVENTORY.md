# Technical data inventory

| Data | Stored in | Purpose | User-scoped | Retention decision |
|---|---|---|---|---|
| Email, display name, status | `users` | identity and account | yes | define account lifecycle |
| Language, topics, country, time, timezone, audio preference | `user_preferences` | personalization and scheduling | yes | retain while account exists |
| Briefing editions and items | `briefing_editions`, `briefing_edition_items` | shared editorial output | shared by profile | define history window |
| User deliveries | `user_briefing_deliveries` | history and delivery target | yes | define history window |
| Push token metadata | `push_devices` | notification delivery | yes | disable/revoke on logout; cleanup policy pending |
| Notification settings/jobs/events | notification tables | delivery operation and audit | yes | define operational retention |
| Session token digests | `auth_sessions` | bearer session validation | yes | expire/revoke and later cleanup |
| Audio metadata and files | `audio_*`, `data/audio/` | playback | linked to shared edition | retain with artifact policy |

Passwords are stored only as PBKDF2 digests. Bearer tokens and full push tokens are not returned by API serialization. Shared `BriefingEdition` and `AudioArtifact` must not be deleted solely because one user is removed; future account deletion should remove user-owned rows and retain shared artifacts while referenced.
