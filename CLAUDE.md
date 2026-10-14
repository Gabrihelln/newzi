# Newzi

Monorepo: `backend/` (FastAPI product API), `engine/` (news collection, briefings, audio, push worker) and
`mobile/` (React Native CLI app for Android and iOS; see `mobile/CLAUDE.md`).

- **iOS work:** read and follow `docs/IOS_SETUP.md` first. It lists, in order, everything still needed to
  build and test the app on an iPhone, and which steps need the project owner's Apple/Firebase accounts.
- Never commit `.env`, keys or service-account files. Commit or push only when asked.
