# Runbook: Add or Remove a Founder

*Source:* `deploy/ansible/group_vars.example.yml`, `deploy/ansible/roles/app/templates/settings.env.j2`, `crates/chat-server/src/api.rs`, `crates/chat-store-pg/migrations/0009_access_requests.sql`.

---

## 1. What a Founder Is and What They Can Do

In Loamz Chat, the server operates an access gate (`CHAT_ACCESS=approval`). When a stranger signs in, they must submit a reason to join.
- **Founders** are designated administrators who:
  1. Are approved automatically upon sign-in without waiting for approval.
  2. Receive automated notification emails whenever a new person asks to join.
  3. Can view waiting requests in the "Me" settings page under "Requests to join" (via `GET /api/v1/admin/requests`).
  4. Can approve or decline requests (via `POST /api/v1/admin/requests/{account}/{decision}`).
- **How founders are configured:** A comma-separated list of email addresses or domain patterns (e.g. `founder@example.com` or `@mycompany.com`) passed into `chat-server` as the `CHAT_FOUNDERS` environment variable.

---

## 2. Procedure: Add or Remove a Founder via Ansible (Recommended)

1. Connect to your local deployment repository clone:
   ```bash
   cd deploy/ansible
   ```
2. Open `group_vars/all/main.yml`:
   Locate the `founders:` setting.
   - **To add an individual founder:** Add their email to the list:
     ```yaml
     founders: "founder1@loamz.com,newfounder@loamz.com"
     ```
   - **To allow an entire team domain to act as founders:** Use the `@domain` wildcard:
     ```yaml
     founders: "@loamz.com"
     ```
   - **To remove a founder:** Remove their email address from the string.
3. Apply the configuration change to the server:
   ```bash
   ansible-playbook site.yml --tags app
   ```
   *Ansible updates `/etc/loamz-chat/settings.env` and restarts `chat-server`.*
4. **Verification:**
   Check that `chat-server` restarted cleanly:
   ```bash
   ssh ubuntu@<SERVER_IP> "sudo systemctl status chat-server"
   ```
   **Expected output:** `Active: active (running)`.

---

## 3. Emergency Procedure: Update Directly on the Live Server

If you need to grant immediate approval permissions and cannot run Ansible right away:

1. SSH into the server:
   ```bash
   ssh ubuntu@<SERVER_IP>
   ```
2. Open `/etc/loamz-chat/settings.env` with root privileges:
   ```bash
   sudo nano /etc/loamz-chat/settings.env
   ```
3. Update the `CHAT_FOUNDERS` line:
   ```ini
   CHAT_FOUNDERS=founder1@loamz.com,emergencyadmin@loamz.com
   ```
4. Save the file and restart the chat server:
   ```bash
   sudo systemctl restart chat-server
   ```
5. Verify the setting loaded:
   ```bash
   sudo systemctl status chat-server
   curl -fsS http://127.0.0.1:8090/healthz
   ```
   **Expected output:** `{"status":"ok"}`.
6. **Important:** Commit the change back to `deploy/ansible/group_vars/all/main.yml` in git so the next Ansible run does not overwrite it.
