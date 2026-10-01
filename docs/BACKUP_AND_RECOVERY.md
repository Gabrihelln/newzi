# Backup and recovery

MVP procedure for a stopped single-node deployment:

1. Stop scheduler/worker writes.
2. Copy `DATABASE_URL` SQLite file to a versioned backup location, or use SQLite online backup tooling while the service is live.
3. Copy `data/audio/` together with the database; audio metadata references content-addressed files.
4. Record application version and migration version beside the backup.
5. Restore the database and audio directory to an isolated path.
6. Start the service with the same environment and call `GET /health` and `GET /ready`.
7. Verify a known user briefing, audio metadata and notification job counts before resuming workers.

Backups must be encrypted and access-controlled. Retention and off-host replication are operational decisions, not implemented automatically. Before production, test a restore regularly and migrate audio to durable object storage/CDN when required.
