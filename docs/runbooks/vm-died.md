# Runbook: the virtual machine died and must be rebuilt

> **Status: not drilled.** Written on 2 November 2026 from the playbooks and scripts in this repository. One step was checked
> for real (restored tables must be owned by the app's role, which `loamz-chat-restore` now does when given the owner); the rest was
> not run. Do the first drill on a throwaway VM, fix this page where it is wrong, and record it in the drill log of
> [restore-database.md](restore-database.md).

One machine runs everything (an Oracle Always Free Ampere A1: 2 cores, 12 GB): Postgres with three databases (`chat`, `keycloak`,
`loamz_agents`), Keycloak, `chat-server`, the agents server `loamz-agents`, one `chat-bridge@NAME` per agent, and Caddy.

## What you need before it happens

1. The cloud console (to make a machine) and your DNS (Cloudflare) login.
2. **`secrets-backup/`** on your computer, from `ansible-playbook backup-secrets.yml` (run it again whenever a secret changes; it keeps one folder per
   machine, `secrets-backup/<name in inventory.ini>/`, below called `<host>`). Under `<host>/` it must hold:
   - `etc/loamz-chat/{secrets.env,db-password,backup.key}`
   - `etc/keycloak/{admin-password,db-password}`
   - `etc/loamz-agents/{sealing.key,db-password}`, `etc/loamz-agents/bridge-*.key`, `etc/loamz-agents/clients/*.secret`

   `backup.key` opens every backup; `sealing.key` opens everything the agents server stored. Neither can be made again.
3. The off-machine backups in B2 (keys in `group_vars/all/b2.env`): `db/daily/` and `db/monthly/` hold `chat-*.dump.enc`,
   `keycloak-*.dump.enc`, `loamz_agents-*.dump.enc` and `agents-bridge-*.tar.enc`; `blobs/` holds files under 10 MB. A copy of
   `group_vars/` and `inventory.ini` (both git-ignored).
4. On your computer: `ansible-playbook`, `cargo-zigbuild` and `zig`, `wasm-pack`, `pnpm`, `uv`, and the sibling checkouts
   `loamz-chat`, `loamz-agents`, `loamz-data`, `loamz-python` (the builds read them).

## 1. A new machine and DNS [owner only]

1. Ubuntu 24.04 ARM (`loamz-chat/deploy/oracle/grab-vm.sh` helps when Oracle says "out of capacity"). Note its address, `<NEW_IP>`.
2. In Cloudflare point `chat`, `auth`, `data`, `www` and the bare domain at `<NEW_IP>`, **DNS only** (grey cloud). Check: `dig +short chat.loamz.com`.
3. Put `<NEW_IP>` in `inventory.ini`, and check `ssh ubuntu@<NEW_IP> uptime`.

## 2. Put the secrets back before the first playbook run

The playbook makes a key only when it is missing, so restoring the files first keeps the old ones.

```bash
rsync -a --rsync-path="sudo rsync" secrets-backup/<host>/etc/ ubuntu@<NEW_IP>:/etc/
ssh ubuntu@<NEW_IP> 'sudo chmod -R go-rwx /etc/loamz-chat /etc/keycloak'
```

The agents files must belong to the group `loamz-agents`, which exists only after the first run, so that step is below.

## 3. Build and install

```bash
AUTH_URL=https://auth.loamz.com ./build.sh      # server, bridge, web app (saves the previous build first: ./release.sh)
./build-agents.sh                                # the agents wheels, built from the sibling checkouts
ansible-playbook site.yml
```

Keycloak builds its cache on first start: if that task fails, wait a minute and run it again. Then fix the agents files and run the
playbook once more:

```bash
ssh ubuntu@<NEW_IP> 'sudo chgrp -R loamz-agents /etc/loamz-agents && sudo chmod 0750 /etc/loamz-agents && \
  sudo find /etc/loamz-agents -type f -exec chmod 0640 {} +'
ansible-playbook site.yml
```

## 4. Restore the databases

The new databases exist and are empty. Stop everything that uses them, then bring each one back **under its own role** (the
database and its owner have the same name; without the owner the app gets "permission denied").

```bash
ssh ubuntu@<NEW_IP>
sudo systemctl stop chat-server loamz-agents 'chat-bridge@*' keycloak
sudo rclone lsf b2:<BUCKET>/db/daily/ | sort | tail -8                      # newest of each; <BUCKET> is BUCKET_NAME in b2.env
for db in chat keycloak loamz_agents; do
  f=$(sudo rclone lsf b2:<BUCKET>/db/daily/ | grep "^$db-" | sort | tail -1)
  sudo rclone copy "b2:<BUCKET>/db/daily/$f" /root/
  sudo -u postgres dropdb "$db"
  sudo loamz-chat-restore "/root/$f" "$db" "$db"
done
```

## 5. Restore the bridge state and the blobs

```bash
f=$(sudo rclone lsf b2:<BUCKET>/db/daily/ | grep '^agents-bridge-' | sort | tail -1)
sudo rclone copy "b2:<BUCKET>/db/daily/$f" /root/
sudo openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass file:/etc/loamz-chat/backup.key -in "/root/$f" -out /root/bridge.tar
sudo tar -C /var/lib/loamz-agents -xf /root/bridge.tar
sudo chown -R loamz-agents:loamz-agents /var/lib/loamz-agents/bridge
sudo rclone sync b2:<BUCKET>/blobs/ /var/lib/loamz-chat/blobs/
sudo chown -R loamz-chat:loamz-chat /var/lib/loamz-chat/blobs
```

Files over 10 MB are not in the off-machine copy, so those are gone. Plain `.dump` files from the last 14 days may still be on the old disk if it is
reachable.

## 6. Start and check

```bash
sudo systemctl start keycloak chat-server loamz-agents 'chat-bridge@*'
sudo systemctl is-active postgresql keycloak chat-server loamz-agents caddy      # five times: active
curl -fsS https://chat.loamz.com/healthz                                          # {"status":"ok"}
curl -fsS https://chat.loamz.com/api/v1/authority                                 # the public key must equal the one from before
```

Then in a browser: sign in, open an old conversation (it must be readable), send a message to an agent, and check that a bridge
agent still answers in its chat. Finally run `ansible-playbook site.yml` once more, take a backup now
(`sudo systemctl start loamz-chat-backup.service`), and write down what went wrong in the drill log.
