# Runbook: make Keycloak match the product registry

`roles/keycloak/files/reconcile.py` reads `products/*.yml` and makes the `loamz` realm's clients agree: redirects and origins, the audience
each token carries, token exchange, service accounts. It runs from your computer (it needs PyYAML and jsonschema, like `products/validate.py`),
through an SSH tunnel to the machine's Keycloak. `settle.py` still runs on every deploy for the rest (profile settings, theme, agent clients);
this script is the part that grows with each product.

```bash
ssh -N -L 8081:127.0.0.1:8081 ubuntu@<host> &                       # Keycloak listens on loopback only
PW=$(ssh ubuntu@<host> sudo cat /etc/keycloak/admin-password)       # not printed
python3 roles/keycloak/files/reconcile.py --url http://127.0.0.1:8081 --password "$PW" --plan     # exit 2 means it would change something
python3 roles/keycloak/files/reconcile.py --url http://127.0.0.1:8081 --password "$PW" --apply
```

## First time on the live realm (adoption)

1. Back up first: `ssh ubuntu@<host> sudo systemctl start loamz-chat-backup.service` (the Keycloak database is in it), and note the time.
2. `--plan`. Expected, and harmless: `attribute loamz.managed` on each existing client (adoption), plus any audience a client should
   carry and does not. **Anything else (a redirect or origin change, a flag) must be read before applying**: it means the live realm
   differs from the registry. Fix whichever is wrong, the registry or the realm.
3. `--apply`, then `--plan` again: it must say `the realm matches the registry`.
4. Check by hand: sign in to chat in a browser, open a conversation, send an agent a message.

Rehearsed on the local dev Keycloak (the realm rendered from the template): plan, apply, plan gave the five additive changes, then nothing.
It has **not** been run against the live realm. Local Keycloak serves other addresses than the registry, so use `--skip-urls` there.

## Deleting

A client is only deleted if this script made or adopted it (it carries `loamz.managed=registry`), it is gone from the registry, and you
pass `--prune` with `--apply`. Without `--prune` the plan names it and keeps it.

## Not done by this script

Realm settings, the sign-in theme, identity providers, organizations, users, roles and the agents' own service-account clients stay in the
realm template and `settle.py`. Secrets are never rotated or printed.
