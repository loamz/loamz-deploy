# Runbook: Restore Database and Monthly Recovery Drill

*Source:* `deploy/ansible/roles/backup/templates/backup.sh.j2`, `deploy/compose.dev.yml`, `scripts/dev.sh`, `crates/chat-store-pg/migrations/`.

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

Execute this checklist on the first Monday of every month. Record results in `docs/runbooks/restore-database.md` (the monthly drill checklist) (`UNCONFIRMED: check with Claude`).

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
