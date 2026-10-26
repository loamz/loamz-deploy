# Runbook: Rotate the Device-Authority Key

*Source:* `crates/chat-identity/src/lib.rs`, `crates/chat-server/src/api.rs`, `deploy/ansible/roles/app/tasks/main.yml`, `docs/security/internal-review-1.md`.

---

## What the Device-Authority Key Is

The **device-authority key** is an Ed25519 signing key held exclusively by the authentication service (`chat-server`).
- **Its job:** When a user registers a new phone or computer, the server issues a cryptographic certificate binding the device's public signing key to the person's identity (`Identity { account, device, kind: human|agent, tenant, name }`).
- **How other devices use it:** Every chat client uses the authority's public key (via `Trust`) to verify that members and bots in a room are genuine. It proves that an agent has a bot badge, and prevents a malicious server or attacker from impersonating a person.
- **Where it lives:** On the production server in `/etc/loamz-chat/secrets.env` as `CHAT_AUTHORITY_SEED=<64-hex-chars>`. The owner holds an offline backup in `secrets-backup/etc/loamz-chat/secrets.env`.

---

## What Happens if the Key Leaks or Is Lost?

- **If the key is lost (destroyed with no backup):**
  The server can no longer issue certificates for new devices. Existing devices will reject certificates from any freshly generated authority key. **Result:** Every user must reset their local storage and re-register their devices.
- **If the key leaks (compromised by an adversary):**
  An attacker holding the seed can forge signed device credentials and introduce "ghost devices" claiming to be an existing person. (The attacker still cannot read past end-to-end encrypted messages because MLS group keys are negotiated between real devices; but they could attempt to join new rooms if not stopped).
  **Result:** The authority key must be rotated immediately, and the compromised key revoked.

---

## The Rotation Architecture: What Works Today vs What Requires a Code Change

### What Works Today in Code
1. **Multi-key Trust in `chat-identity`:**
   In `crates/chat-identity/src/lib.rs`, `Trust` is explicitly designed for rotation:
   ```rust
   /// The authority keys a client believes. More than one allows a key to be rotated.
   #[derive(Clone, Debug)]
   pub struct Trust(Vec<VerifyingKey>);
   ```
   `Trust::verify()` iterates through all trusted authority keys. If a certificate matches *any* key in the list, it is accepted.

### What Requires a Code Change Before Live Rotation Can Happen
> [!WARNING]
> **Code change required:** The following two parts currently support only a single authority key and must be updated before performing a zero-downtime key rotation:
> 1. **Server Endpoint (`/api/v1/authority`):** In `crates/chat-server/src/api.rs`, the endpoint returns a single key: `{"public_key": "..."}`. It needs to return a list: `{"public_keys": ["<new_key>", "<old_key>"], "current": "<new_key>"}`.
> 2. **Client Key Pinning (`web/src/engine.ts`):** The web client fetches the authority key on first sign-in and pins it. The client needs to accept an array of valid keys from the authority endpoint so both old and new certificates remain trusted during the transition.
>
> *Status: Marked as Open in `docs/security/internal-review-1.md` (item 1).*

---

## Zero-Downtime Rotation Procedure (Once Code Changes Land)

When the multi-key endpoint is implemented, follow this four-phase rotation process:

### Phase 1: Generate the New Authority Seed [OWNER ONLY]
1. On a secure, offline terminal, generate a fresh 32-byte (64-hex) seed:
   ```bash
   NEW_SEED=$(openssl rand -hex 32)
   ```
2. Derive the corresponding public key using a local tool or scratch test:
   `NEW_PUBLIC_KEY=<base64-encoded-verifying-key>`

### Phase 2: Stage Both Keys in Trust List (Dual-Trust Phase)
1. Update `chat-server` configuration to serve both public keys over `/api/v1/authority`.
2. Deploy the update. Existing clients fetch and trust both `<OLD_PUBLIC_KEY>` and `<NEW_PUBLIC_KEY>`.
3. Wait for clients to refresh their trusted authority list (proposal: 7–14 days for active users to update).

### Phase 3: Switch the Signing Authority to the New Key
1. Connect to the production server:
   ```bash
   ssh ubuntu@<SERVER_IP>
   ```
2. Update `/etc/loamz-chat/secrets.env` to set the new signing seed:
   ```bash
   sudo sed -i 's/^CHAT_AUTHORITY_SEED=.*/CHAT_AUTHORITY_SEED=<NEW_SEED>/' /etc/loamz-chat/secrets.env
   ```
3. Restart the server:
   ```bash
   sudo systemctl restart chat-server
   ```
4. Verify the server is running and signing with the new key:
   ```bash
   sudo systemctl status chat-server
   curl -fsS http://127.0.0.1:8090/healthz
   ```
   Newly registered devices receive certificates signed by the new key. Existing devices accept them because they trust both keys.

### Phase 4: Retire the Old Key (After Transition Window)
1. After all active devices have re-keyed or after a defined deprecation window, remove `<OLD_PUBLIC_KEY>` from the server's public key endpoint.
2. Back up the new secret to offline storage:
   ```bash
   ansible-playbook deploy/ansible/backup-secrets.yml
   ```
3. Securely erase the old backup copy.

---

## Emergency Key Revocation (Hard Reset if Key is Actively Leaked Today)

If the key is actively leaked *before* the multi-key rotation code is deployed:
1. Generate a new seed on the server:
   ```bash
   ssh ubuntu@<SERVER_IP> "sudo sed -i 's/^CHAT_AUTHORITY_SEED=.*/CHAT_AUTHORITY_SEED=$(openssl rand -hex 32)/' /etc/loamz-chat/secrets.env && sudo systemctl restart chat-server"
   ```
2. **Impact on Users:** All existing client sessions will fail certificate verification for devices created after this moment. Users must be notified to clear browser application storage (`IndexedDB`) and sign in again to register fresh devices.
