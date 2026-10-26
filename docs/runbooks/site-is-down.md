# Runbook: The Site Is Down (First Checks in Order)

*Source:* `deploy/ansible/roles/caddy/templates/Caddyfile.j2`, `deploy/ansible/roles/app/templates/chat-server.service.j2`, `deploy/ansible/roles/keycloak/templates/keycloak.service.j2`, `deploy/ansible/roles/postgres/tasks/main.yml`.

When users report that Loamz Chat is down, or an automated uptime monitor alerts, run these diagnostic checks in this exact order.

---

## Check 1: DNS Resolution (Is the domain pointing to the server?)

From any computer with internet access:
```bash
dig +short <domain>
dig +short <auth_domain>
```
**What you should see:** Both return the public IPv4 address of your server.
**If not:**
- If it returns nothing (`NXDOMAIN` or blank), check your domain registrar and DNS provider (e.g. Cloudflare DNS). Ensure nameservers are active and the A record exists.
- If it returns the wrong IP, update the A record to the server's current public IP.

---

## Check 2: External HTTP / TLS Reachability (Is Caddy answering?)

Test the public health check endpoint over HTTPS:
```bash
curl -i -sS -m 5 https://<domain>/healthz
```
**What you should see:**
```http
HTTP/2 200
content-type: application/json
{"status":"ok"}
```
**If not:**
- `Connection refused` on port 443: Caddy is stopped or the cloud firewall is blocking port 443. Proceed to Check 3.
- `SSL certificate problem`: Caddy could not obtain an ACME certificate (often due to rate limits or DNS pointing to the wrong IP). Check Caddy logs (`sudo journalctl -u caddy --no-pager -n 50`).
- `HTTP 502 Bad Gateway`: Caddy is running, but the backend `chat-server` on `127.0.0.1:8090` is down or unresponsive. Proceed to Check 4.

---

## Check 3: Host Status and Caddy Service (On the Server)

SSH into the server:
```bash
ssh ubuntu@<SERVER_IP>
```
Check Caddy status:
```bash
sudo systemctl status caddy
```
**What you should see:** `Active: active (running)`.
**If not:**
- Restart Caddy:
  ```bash
  sudo systemctl restart caddy
  ```
- Check configuration syntax:
  ```bash
  sudo caddy validate --config /etc/caddy/Caddyfile
  ```

---

## Check 4: Chat Server Service (Is `chat-server` running?)

Check the systemd unit:
```bash
sudo systemctl status chat-server
```
**What you should see:** `Active: active (running)`.
**Test local loopback response:**
```bash
curl -fsS http://127.0.0.1:8090/healthz
```
**What you should see:** `{"status":"ok"}`.
**If not:**
- Read the last 50 lines of logs:
  ```bash
  sudo journalctl -u chat-server --no-pager -n 50
  ```
- *Common root cause 1: Database connection failure (`could not connect to server`).* Proceed to Check 6 (PostgreSQL).
- *Common root cause 2: Permission denied on socket or files.* Verify ownership of `/var/lib/loamz-chat` is `loamz-chat:loamz-chat`.
- Restart the service:
  ```bash
  sudo systemctl restart chat-server
  ```

---

## Check 5: Keycloak Sign-in Service (Is Keycloak answering?)

Test the internal Keycloak OpenID configuration endpoint:
```bash
curl -fsS http://127.0.0.1:8081/realms/loamz/.well-known/openid-configuration | jq .issuer
```
**What you should see:** `"https://<auth_domain>/realms/loamz"`.
**If not:**
- Check the Keycloak Docker container:
  ```bash
  sudo docker ps -a --filter name=keycloak
  ```
- If the container is restarting or exited, inspect the logs:
  ```bash
  sudo docker logs --tail 50 keycloak
  ```
- *Common root cause: Keycloak cannot reach PostgreSQL or the database credentials changed.*
- Restart Keycloak:
  ```bash
  sudo systemctl restart keycloak
  ```
  *(Allow 30–60 seconds for Keycloak to finish starting up).*

---

## Check 6: PostgreSQL Database (Is PostgreSQL accepting connections?)

Test local database connectivity:
```bash
sudo runuser -u postgres -- pg_isready -h 127.0.0.1 -p 5432
```
**What you should see:** `127.0.0.1:5432 - accepting connections`.
**If not:**
- Check systemd status:
  ```bash
  sudo systemctl status postgresql
  ```
- Restart PostgreSQL:
  ```bash
  sudo systemctl restart postgresql
  ```
- Inspect PostgreSQL logs:
  ```bash
  sudo journalctl -u postgresql --no-pager -n 50
  ```

---

## Check 7: Disk Space and Inodes (Is the disk full?)

Check disk capacity and inodes:
```bash
df -h / /var/lib/loamz-chat /var/backups/loamz-chat
df -i /
```
**What you should see:** Use% under 85%.
**If 100% full:**
- Check for accumulating database dumps:
  ```bash
  ls -lh /var/backups/loamz-chat/
  ```
  Delete old dumps older than 7 days if necessary.
- Check journal logs size:
  ```bash
  sudo journalctl --disk-usage
  sudo journalctl --vacuum-size=500M
  ```

---

## Check 8: Memory and System Load (Is the server OOM or CPU-locked?)

Check memory usage and process load:
```bash
free -m
top -b -n 1 | head -n 15
```
**What you should see:** At least 500 MB free or available buffer/cache memory.
**If swap/memory is exhausted:**
- Look for runaway processes in `top`.
- Check if Linux killed a process due to Out of Memory (OOM):
  ```bash
  sudo dmesg -T | grep -i oom
  ```
- If Keycloak or chat-server was killed, check memory limits and restart:
  ```bash
  sudo systemctl restart postgresql keycloak chat-server
  ```
