# Runbook: put a product on the machine from its registry file

`roles/product` installs every id in `deployed_products` (`group_vars/all/main.yml`, empty today) from `products/<id>.yml`: a system user,
`/opt/loamz-<id>`, `/etc/loamz-<id>`, `/var/lib/loamz-<id>`, the program, an optional web app, an optional PostgreSQL role and database
(`loamz_<id>`), the settings file, a systemd unit whose memory limit is the registry's `memory_mb`, and a Caddy host from `urls.app`.
Nothing in the role names a product. `tests/product-render-test.yml` renders it for Data in CI.

## What you supply per product (never in git)

- `artifacts/<id>/<unit>`: the program (`cargo zigbuild --release --target aarch64-unknown-linux-gnu.2.35 -p loamz-data-server`, copied as `loamz-data`), and `artifacts/<id>-web/` if the registry says `web: true`.
- `group_vars/secrets.yml` (git-ignored):
  `product_env: { data: { LOAMZ_DATA_OIDC_ISSUER: https://auth.loamz.com/realms/loamz, LOAMZ_DATA_BUCKET: loamz-data, LOAMZ_DATA_BUCKET_ENDPOINT: …, LOAMZ_DATA_BUCKET_KEY_ID_FILE: /etc/loamz-data/r2-key-id, … } }` and
  `product_files: { data: { r2-key-id: …, r2-secret: …, r2-issuer-token: … } }` (written under `/etc/loamz-data/`, mode 0640, group `loamz-data`).
- DNS: the product's host (`data.loamz.com`) at the machine, DNS only.

## Order

1. `python3 products/validate.py` (the memory total must still fit with headroom).
2. `roles/keycloak/files/reconcile.py --plan` then `--apply` ([keycloak-reconcile.md](keycloak-reconcile.md)) so the clients and audiences exist.
3. Add the id to `deployed_products`, then `ansible-playbook site.yml --tags` is not used: run the whole playbook.
4. Check `systemctl is-active loamz-<id>`, `curl https://<host>/<health>`, and the family smoke test.

## Not solved here, and not hidden

- **Workspace sites.** Data serves one site per workspace at `w-<id>.data.loamz.com`. That needs a wildcard certificate (a DNS challenge, so a Caddy
  build with a DNS plugin) or flattening the host to one label under a wildcard Cloudflare already holds. The vhost this role writes is the account site only.
- **Data's own units:** the compute agent (`loamz-runner`) and the sandbox are not installed by this role.
- It has been rendered and syntax-checked, **not run on a machine**.
