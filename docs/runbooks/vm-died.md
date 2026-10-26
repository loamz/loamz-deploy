# Runbook: The Virtual Machine Died and Must Be Rebuilt

*Source:* `deploy/ansible/README.md`, `deploy/ansible/site.yml`, `deploy/ansible/backup-secrets.yml`, `deploy/ansible/roles/backup/templates/backup.sh.j2`.

Use this runbook when the virtual machine running Loamz Chat is destroyed, corrupted, terminated, or permanently unreachable.

---

## Prerequisites & Required Materials

Before starting, ensure you have:
1. **Access to the cloud console** (Oracle Cloud Infrastructure console or your VPS provider) to provision a new instance.
2. **Access to your DNS provider** (e.g. Cloudflare) to update A records.
3. **The offline secrets backup** saved from the last run of `backup-secrets.yml`:
   - `secrets-backup/etc/loamz-chat/secrets.env` (contains the device-authority seed, sign-in secret, and code-hashing key).
   - `secrets-backup/etc/loamz-chat/db-password` (chat database password).
   - `secrets-backup/etc/keycloak/admin-password` (Keycloak admin password).
   - `secrets-backup/etc/keycloak/db-password` (Keycloak database password).
4. **The latest off-site backup archive** (database dump `chat-*.dump` and blob directory).
5. **Local build tools:** `ansible-playbook`, `cargo-zigbuild`, `zig`, `wasm-pack`, `pnpm`.

---

## Step 1: Provision a New Virtual Machine [OWNER ONLY]

1. Log into your cloud provider console.
2. Launch a fresh compute instance:
   - **Operating System:** Ubuntu 24.04 LTS (Minimal or Server).
   - **Shape:** Ampere A1 (ARM64, 4 OCPU, 24 GB RAM) or standard VPS (x86_64).
   - **SSH Key:** Paste your local administrator SSH public key.
3. Note the new public IPv4 address assigned to the instance: `<NEW_IP>`.

---

## Step 2: Update DNS Records [OWNER ONLY]

1. Open your DNS management dashboard (e.g. Cloudflare DNS).
2. Update the A records for both domains to point to `<NEW_IP>`:
   - `<domain>` (e.g. `chat.loamz.com`) -> `<NEW_IP>` ("DNS only", unproxied grey cloud).
   - `<auth_domain>` (e.g. `auth.loamz.com`) -> `<NEW_IP>` ("DNS only", unproxied grey cloud).
3. **Verification command:**
   ```bash
   dig +short <domain>
   ```
   **Expected output:**
   `<NEW_IP>`
   *If you do not see `<NEW_IP>`, wait a few minutes for TTL to expire before running Caddy certificate issuance.*

---

## Step 3: Update Ansible Inventory & Restore Secrets on Host

1. In your local repository clone under `deploy/ansible/`:
   Edit `inventory.ini` to set the new IP:
   ```ini
   [chat]
   <NEW_IP> ansible_user=ubuntu
   ```
2. Verify SSH connection to the new VM:
   ```bash
   ssh -o StrictHostKeyChecking=accept-new ubuntu@<NEW_IP> "uptime"
   ```
   **Expected output:** System uptime string (e.g. `up 2 min, 1 user, load average...`).
3. Pre-populate the backed-up secrets on the fresh machine before running Ansible so the original device-authority key and passwords are kept:
   ```bash
   # Create directories with strict permissions
   ssh ubuntu@<NEW_IP> "sudo mkdir -p /etc/loamz-chat /etc/keycloak && sudo chmod 0700 /etc/loamz-chat /etc/keycloak"

   # Copy backed-up secrets back to the new server
   scp secrets-backup/etc/loamz-chat/secrets.env ubuntu@<NEW_IP>:/tmp/secrets.env
   scp secrets-backup/etc/loamz-chat/db-password ubuntu@<NEW_IP>:/tmp/chat-db-password
   scp secrets-backup/etc/keycloak/admin-password ubuntu@<NEW_IP>:/tmp/kc-admin-password
   scp secrets-backup/etc/keycloak/db-password ubuntu@<NEW_IP>:/tmp/kc-db-password

   # Move secrets into place with root-only permissions
   ssh ubuntu@<NEW_IP> "sudo mv /tmp/secrets.env /etc/loamz-chat/secrets.env && \
     sudo mv /tmp/chat-db-password /etc/loamz-chat/db-password && \
     sudo mv /tmp/kc-admin-password /etc/keycloak/admin-password && \
     sudo mv /tmp/kc-db-password /etc/keycloak/db-password && \
     sudo chmod 0600 /etc/loamz-chat/* /etc/keycloak/* && \
     sudo chown -R root:root /etc/loamz-chat /etc/keycloak"
   ```
   *Source:* `deploy/ansible/backup-secrets.yml`.

---

## Step 4: Build and Deploy the Base Stack

1. From `deploy/ansible/`, build the server and web bundles:
   ```bash
   AUTH_URL=https://<auth_domain> ./build.sh
   ```
   *Note: For an x86 machine, run `./build.sh x86_64-unknown-linux-gnu.2.35`.*
   **Expected output:** `Built chat-server` and `Built web application` without errors.
2. Run the Ansible playbook to configure the machine, PostgreSQL, Keycloak, Caddy, and chat-server:
   ```bash
   ansible-playbook site.yml
   ```
   **Expected output:** All tasks complete with `failed=0`.
   *If a task fails on Keycloak startup, wait 60 seconds (Keycloak builds container caches on first start) and rerun.*

---

## Step 5: Restore the Database and Blobs

1. Locate your latest off-site backup archive (`chat-<date>.dump`) and blobs directory from your backup remote.
2. Copy the backup files to the server:
   ```bash
   scp chat-<date>.dump ubuntu@<NEW_IP>:/tmp/chat-restore.dump
   rsync -avz --progress <local_backup_blobs_dir>/ ubuntu@<NEW_IP>:/tmp/blobs-restore/
   ```
3. Stop the chat server while restoring database state:
   ```bash
   ssh ubuntu@<NEW_IP> "sudo systemctl stop chat-server"
   ```
4. Restore the PostgreSQL database:
   ```bash
   ssh ubuntu@<NEW_IP> "sudo runuser -u postgres -- pg_restore --clean --if-exists --dbname=chat /tmp/chat-restore.dump && rm -f /tmp/chat-restore.dump"
   ```
   *Source:* `deploy/ansible/roles/backup/templates/backup.sh.j2`.
5. Restore the encrypted file blobs:
   ```bash
   ssh ubuntu@<NEW_IP> "sudo mkdir -p /var/lib/loamz-chat/blobs && \
     sudo cp -r /tmp/blobs-restore/* /var/lib/loamz-chat/blobs/ && \
     sudo chown -R loamz-chat:loamz-chat /var/lib/loamz-chat && \
     sudo rm -rf /tmp/blobs-restore"
   ```
6. Start the chat server:
   ```bash
   ssh ubuntu@<NEW_IP> "sudo systemctl start chat-server"
   ```

---

## Step 6: Verify Recovery

1. Check service statuses:
   ```bash
   ssh ubuntu@<NEW_IP> "sudo systemctl is-active chat-server keycloak caddy postgresql"
   ```
   **Expected output:**
   ```
   active
   active
   active
   active
   ```
2. Test the public health check endpoint:
   ```bash
   curl -fsS https://<domain>/healthz
   ```
   **Expected output:** `{"status":"ok"}`.
3. Verify public authority key matches pre-disaster key:
   ```bash
   curl -fsS https://<domain>/api/v1/authority
   ```
   Compare the base64 `public_key` with your backed-up public key.
4. **End-to-End Verification:** Open `https://<domain>` in your browser. Sign in using your existing Google or work account. Verify your existing conversations appear and messages are readable.
