# Runbook: Restore Database and Monthly Recovery Drill

*Source:* `roles/backup/templates/{backup,restore}.sh.j2` in this repository, and `loamz-chat` (`deploy/compose.dev.yml`, `scripts/dev.sh`, `crates/chat-store-pg/migrations/`).

Use this runbook to:
1. Verify the integrity of database dumps in a local scratch environment without touching the live server.
2. Complete the required monthly Disaster Recovery Drill.

---

## Part A: Restore into a Local Scratch Docker Container

Follow these steps to restore a backup dump into an isolated local container and verify data consistency.

### Step 1: Obtain the Database Backup File
Locate the latest backup file from the server or your off-site rclone storage (`chat-<stamp>.dump`).
```bash
# If copying directly from the production server:
scp ubuntu@<SERVER_IP>:/var/backups/loamz-chat/chat-<stamp>.dump /tmp/chat-drill.dump
```
*Source:* `deploy/ansible/roles/backup/templates/backup.sh.j2`.

### Step 2: Launch a Fresh Scratch PostgreSQL Container
Start an empty PostgreSQL 16 container on a scratch port (e.g. `5439`):
```bash
docker run --rm -d \
  --name chat-restore-scratch \
  -e POSTGRES_USER=chat \
  -e POSTGRES_PASSWORD=scratch-drill-password \
  -e POSTGRES_DB=chat \
  -p 127.0.0.1:5439:5432 \
  postgres:16
```
Wait 5 seconds for PostgreSQL to initialize. Verify it is accepting connections:
```bash
pg_isready -h 127.0.0.1 -p 5439 -U chat
```
**Expected output:** `127.0.0.1:5439 - accepting connections`.

### Step 3: Restore the Dump File
Copy the dump file into the container and execute `pg_restore`:
```bash
docker cp /tmp/chat-drill.dump chat-restore-scratch:/tmp/chat.dump

docker exec -t chat-restore-scratch pg_restore \
  --username=chat \
  --dbname=chat \
  --clean \
  --if-exists \
  --no-owner \
  /tmp/chat.dump
```
**Expected output:** Return code 0 (some warnings about roles not existing may occur with `--no-owner`, which is normal).

### Step 4: Verify Table Counts and Schema Integrity
Run a query against the scratch database to confirm tables exist and contain records:
```bash
PGPASSWORD=scratch-drill-password psql -h 127.0.0.1 -p 5439 -U chat -d chat -c "
  SELECT 'conversations' AS table_name, count(*) FROM conversations
  UNION ALL
  SELECT 'conversation_entries', count(*) FROM conversation_entries
  UNION ALL
  SELECT 'people', count(*) FROM people
  UNION ALL
  SELECT 'devices', count(*) FROM devices;
"
```
**Expected output:** A table showing positive counts matching production volume:
```
       table_name       | count 
------------------------+-------
 conversations          |     5
 conversation_entries   |   142
 people                 |     8
 devices                |    11
(4 rows)
```

### Step 5: Verify That Ciphertext Cannot Be Decrypted Without User Keys
Confirm that message contents in `conversation_entries` are purely encrypted bytes (`\\x...` bytea) and contain no plaintext:
```bash
PGPASSWORD=scratch-drill-password psql -h 127.0.0.1 -p 5439 -U chat -d chat -c "
  SELECT seq, encode(body, 'hex') AS hex_body FROM conversation_entries LIMIT 3;
"
```
**Expected output:** Hex-encoded MLS ciphertext frames. Plain English text should never appear in the `body` column.

### Step 6: Clean Up the Scratch Container
When testing is complete, destroy the scratch container:
```bash
docker stop chat-restore-scratch
rm -f /tmp/chat-drill.dump
```

---

## Part B: Monthly Recovery Drill Checklist

Execute this checklist on the first Monday of every month and record it in the **Drill log** at the bottom of this page. Once, do the full rebuild drill ([vm-died.md](vm-died.md)) on a throwaway machine.

- [ ] **1. Backup Freshness:** Confirm a new backup file was written to `/var/backups/loamz-chat/` within the past 24 hours.
  ```bash
  ssh ubuntu@<SERVER_IP> "ls -lth /var/backups/loamz-chat/ | head -n 5"
  ```
- [ ] **2. Off-site Sync:** Confirm the backup exists on the secondary remote storage (`backup_remote` via rclone).
- [ ] **3. Scratch Restore:** Execute Part A above with the latest dump file into a clean local container.
- [ ] **4. Blob Backup Check:** Verify the blob directory size on remote storage matches `/var/lib/loamz-chat/blobs`.
  ```bash
  ssh ubuntu@<SERVER_IP> "du -sh /var/lib/loamz-chat/blobs"
  ```
- [ ] **5. Authority Key Backup:** Verify that `secrets-backup/` containing the device-authority key remains accessible in the owner's password manager or encrypted offline storage.
- [ ] **6. Record Sign-off:** Log the drill date, backup timestamp, table row counts, and tester name.

## Encrypted backups (from 2026-10-27)
Nightly dumps of the three databases (`chat`, `keycloak`, `loamz_agents`) and the agents' chat-bridge state (`agents-bridge-*.tar.enc`) are
encrypted with `/etc/loamz-chat/backup.key` (made once on the server). **Copy that key, and `/etc/loamz-agents/sealing.key`, to your password
manager:** `ansible-playbook backup-secrets.yml` fetches them into `secrets-backup/` in this repository. Without the backup key an off-machine copy
cannot be opened; without the sealing key the agents server's stored conversations cannot be.

To look at a dump on any machine that has the key at that path: `sudo loamz-chat-restore chat-YYYYMMDD-HHMM.dump.enc [database]`
(default database `chat_restored`; it refuses to touch a live one). To bring a database back for real (stop the app, drop the empty
database first) name its owner too: `sudo loamz-chat-restore chat-YYYYMMDD-HHMM.dump.enc chat chat`. Without the owner the tables belong to
`postgres` and the app gets "permission denied" (checked in a scratch Postgres on 2 November 2026).
Off-machine copies (when `backup_remote` is set) keep 7 daily dumps and 12 monthly ones.

## Drill log
Add a row each time. A drill is only counted when the restored data was opened and read.

| Date | By | What was restored, and from where | Result | What had to be fixed |
|---|---|---|---|---|
| 2026-11-02 | Claude (mechanism only, not a drill) | `pg_restore --no-owner` into a scratch Postgres 17 | Tables came back owned by `postgres`; the app role got "permission denied" | `loamz-chat-restore` takes the owner role as a third argument (`--role`); with it the app role reads the data |
