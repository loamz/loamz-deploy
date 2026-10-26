# Loamz Chat Operations Runbooks

These runbooks guide the operator through recovery, maintenance, emergency response, and administrative tasks for Loamz Chat.

All procedures are verified against the deployment automation in `deploy/ansible/` and the server architecture.

---

## Runbook Directory

| Runbook | Purpose | When to use |
|---|---|---|
| [1. VM Died (Disaster Recovery)](vm-died.md) | Full server rebuild and data restoration from backup | The host instance is terminated, corrupted, or unreachable |
| [2. Restore Database Drill](restore-database.md) | Restoring database and blob dumps into scratch container | Routine monthly recovery drill or disaster recovery |
| [3. Rotate Authority Key](rotate-authority-key.md) | Device-authority key rotation procedure and analysis | Key compromise, routine key retirement, or audit prep |
| [4. Keycloak Realm Operations](keycloak-realm.md) | Realm export, import, live schema updates, and admin tunnel | User management, SSO configuration, identity updates |
| [5. Add or Remove a Founder](add-a-founder.md) | Update access gate founder permissions | Granting/revoking access approval privileges |
| [6. Site is Down (Triage)](site-is-down.md) | Step-by-step diagnostic triage sequence | The site, sign-in, or messaging stops answering |

---

## Escalation and Emergency Contacts

> [!IMPORTANT]
> Keep this contact list updated. Any emergency requiring cloud account access, DNS changes, or master secret decryption requires the Owner.

| Role | Name | Channel / Contact | Responsibilities |
|---|---|---|---|
| **Primary Owner** | `OWNER TO FILL` | `OWNER TO FILL` | Cloud consoles (Oracle/DNS), master secrets, domain registrar |
| **Secondary Owner** | `OWNER TO FILL` | `OWNER TO FILL` | Emergency backup keys, failover contact |
| **System Lead** | Claude | Repository PRs | Code, cryptography review, deployment lead |
| **Operations Support** | Antigravity | Issue tracker | Runbooks, QA, verification, dependency auditing |

---

## System Overview & Component Port Reference

- **Host OS:** Ubuntu 24.04 LTS (Oracle Cloud Ampere aarch64 or x86_64 VPS)
- **Reverse Proxy:** Caddy (`:80`, `:443`) terminating TLS for `chat.<domain>` and `auth.<domain>`
- **Chat Server:** Rust binary (`chat-server`) listening locally on `127.0.0.1:8090`
- **Identity Server:** Keycloak container listening locally on `127.0.0.1:8081`
- **Database:** PostgreSQL 16 on `127.0.0.1:5432` (databases: `chat`, `keycloak`)
- **Blob Storage:** Encrypted ciphertext blobs in `/var/lib/loamz-chat/blobs/`
- **Backups:** Nightly dumps in `/var/backups/loamz-chat/` and remote rclone copy
