# Runbook: Keycloak Realm Operations (Export, Import, Live Changes, Admin Tunnel)

*Source:* `deploy/ansible/roles/keycloak/`, `deploy/ansible/roles/caddy/templates/Caddyfile.j2`, `deploy/ansible/README.md`, `web/e2e/lib.cjs`.

---

## 1. Accessing Keycloak Admin Console via SSH Tunnel [OWNER ONLY]

By design, Caddy blocks public access to `/admin` on `auth.<domain>` (returning HTTP 403 Forbidden). The administration console is accessible only via local loopback.

1. Open an SSH local port-forwarding tunnel to the server:
   ```bash
   ssh -L 8081:127.0.0.1:8081 ubuntu@<SERVER_IP>
   ```
2. Read the admin password on the host:
   ```bash
   sudo cat /etc/keycloak/admin-password
   ```
   *(Keep this terminal open to maintain the tunnel).*
3. Open your browser to:
   ```
   http://localhost:8081
   ```
4. Sign in with:
   - **Username:** `admin`
   - **Password:** `<content of /etc/keycloak/admin-password>`
5. Switch from the `master` realm to the `loamz` realm using the dropdown at top-left.

---

## 2. Exporting the Realm Configuration

Use this to capture the live state of users, clients, identity providers, and mappers.

### Method A: Automated CLI Export via Docker Container Exec
1. Connect via SSH to the server:
   ```bash
   ssh ubuntu@<SERVER_IP>
   ```
2. Run an export command inside a temporary container attached to the Keycloak database:
   ```bash
   sudo docker exec -t keycloak /opt/keycloak/bin/kc.sh export \
     --dir /opt/keycloak/data/import/export-$(date +%Y%m%d) \
     --realm loamz \
     --users realm_file
   ```
3. Copy the exported JSON file:
   ```bash
   sudo cp /etc/keycloak/import/export-*/loamz-realm.json /var/backups/loamz-realm-$(date +%Y%m%d).json
   ```

### Method B: Via Admin Web Console
1. Open the SSH tunnel as in Section 1.
2. In the `loamz` realm, navigate to **Realm settings** -> **Action** -> **Partial export**.
3. Toggle "Include clients" and "Include groups and roles" -> Click **Export**. Save the JSON file locally.

---

## 3. Importing or Restoring the Realm

On initial server setup, Keycloak automatically imports `/etc/keycloak/import/realm-loamz.json` because `keycloak.service` starts with `--import-realm`:
```ini
ExecStart=/usr/bin/docker run ... -v /etc/keycloak/import:/opt/keycloak/data/import:ro ... start --import-realm
```
*Source:* `deploy/ansible/roles/keycloak/templates/keycloak.service.j2`.

To re-import or update from a fresh realm file:
1. Place the new realm JSON file in `/etc/keycloak/import/realm-loamz.json`:
   ```bash
   sudo cp <NEW_REALM_JSON> /etc/keycloak/import/realm-loamz.json
   sudo chmod 0644 /etc/keycloak/import/realm-loamz.json
   ```
2. If importing into a clean database, restart the service:
   ```bash
   sudo systemctl restart keycloak
   ```
3. Check startup logs to verify import:
   ```bash
   sudo docker logs --tail 50 -f keycloak
   ```
   **Expected output:** `Imported realm loamz from file /opt/keycloak/data/import/realm-loamz.json`.

---

## 4. Applying Live Schema or Mapper Changes via Admin REST API

When changing mappers (for example, the Google profile picture mapper) without restarting Keycloak or risking database downtime, use the Keycloak Admin REST API.

*Source:* `web/e2e/lib.cjs`.

### Step 1: Obtain an Admin Access Token
From the server (or locally through the SSH tunnel on `http://localhost:8081`):
```bash
ADMIN_PASSWORD=$(sudo cat /etc/keycloak/admin-password)

ADMIN_TOKEN=$(curl -fsS -X POST "http://127.0.0.1:8081/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=${ADMIN_PASSWORD}" | jq -r .access_token)
```
Verify that `ADMIN_TOKEN` is a valid JWT string.

### Step 2: Query Realm Details or Clients
```bash
curl -fsS -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  http://127.0.0.1:8081/admin/realms/loamz | jq .realm
```
**Expected output:** `"loamz"`.

### Step 3: Add or Update a Protocol Mapper (Example: Profile Picture)
To add a user attribute protocol mapper to the `loamz-chat` client:
1. Get the internal UUID of the `loamz-chat` client:
   ```bash
   CLIENT_UUID=$(curl -fsS -H "Authorization: Bearer ${ADMIN_TOKEN}" \
     http://127.0.0.1:8081/admin/realms/loamz/clients?clientId=loamz-chat | jq -r '.[0].id')
   ```
2. Post the mapper definition:
   ```bash
   curl -fsS -X POST "http://127.0.0.1:8081/admin/realms/loamz/clients/${CLIENT_UUID}/protocol-mappers/models" \
     -H "Authorization: Bearer ${ADMIN_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "picture",
       "protocol": "openid-connect",
       "protocolMapper": "oidc-usermodel-attribute-mapper",
       "consentRequired": false,
       "config": {
         "user.attribute": "picture",
         "claim.name": "picture",
         "jsonType.label": "String",
         "id.token.claim": "true",
         "access.token.claim": "true",
         "userinfo.token.claim": "true"
       }
     }'
   ```
   **Expected output:** HTTP 201 Created (or 409 Conflict if already present).
   *Source:* `deploy/ansible/roles/keycloak/templates/realm-loamz.json.j2`.
