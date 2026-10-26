# Putting Loamz Chat on one machine

Everything here was run end to end against a fresh Ubuntu 24.04 machine (in a container) and then the real web app
signed in through it under the production security policy. Run it a second time and it changes almost nothing.

What you get on the machine: PostgreSQL, Keycloak (sign-in: Google for people, work email for organizations), the chat server (a hardened systemd service), Caddy (automatic HTTPS, the web
app, a strict content-security policy), a firewall that allows only SSH and the web, fail2ban, automatic security updates,
and a nightly database dump (copied off the machine if you give it a place).

Secrets (the device-authority key, the sign-in key, the code-hashing key, the database password) are **made on the machine
the first time** and never pass through git, this folder or a chat. Back up the authority key once (below).

## First time

1. **A machine** with Ubuntu 24.04 and your SSH key (Oracle's free ARM machine, or any small VPS), and a **name** that points
   at its IP address (a domain, or a free one from duckdns.org).
2. **Tools on your computer:** `ansible` (`uv tool install ansible-core`), then
   `ansible-galaxy collection install -r requirements.yml`; plus `cargo-zigbuild`, `zig`, `wasm-pack` and `pnpm` for the build.
3. **Say where it is:**
   ```
   cp inventory.example.ini inventory.ini        # put the machine's IP in it
   mkdir -p group_vars/all && cp group_vars.example.yml group_vars/all/main.yml            # your names and settings
   cp group_vars.secrets.example.yml group_vars/all/secrets.yml   # Google keys etc. (git ignores it)
   # DNS: an A record for `domain` and another for `auth_domain`, both pointing at the machine, "DNS only" (grey cloud)
   ```
4. **Build** (ARM by default, which suits Oracle's machine; pass another target for an x86 VPS):
   `AUTH_URL=https://auth.example.com ./build.sh` (or add `x86_64-unknown-linux-gnu.2.35` for an x86 machine)
5. **Install:** `ansible-playbook site.yml`
6. **Keep the authority key safe:** `ansible-playbook backup-secrets.yml`. It copies the secrets to `secrets-backup/` here
   (git ignores it). Move that somewhere private. Losing the authority key means every person sets their devices up again.

## Later updates

`./build.sh && ansible-playbook site.yml` installs a new version and restarts the server. The database upgrades itself on start.

## Not done here, on purpose

- **Real SMS.** Phone sign-in stays off until a provider is wired (in India that needs a registered sender). The development
  mode that prints codes to the log is deliberately not switchable from these playbooks.
- **Keycloak's administrator console** is refused on the public address. Reach it through a tunnel:
  `ssh -L 8081:127.0.0.1:8081 ubuntu@machine`, then http://localhost:8081 (user `admin`, password in `/etc/keycloak/admin-password`).
  That is where you create an organization and its people.
- **Email** (confirming a work email, "you are approved") is off until `smtp_host` is set.
- **Monitoring and alerts.** Use any uptime checker on `https://your-domain/healthz` for now.
