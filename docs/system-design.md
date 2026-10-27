# Loamz system design: products, data, and where everything lives

Status: proposal for the owner (2026-10-27). Free tiers first; money only where it clearly buys time or safety.

## 1. What we run (products and their weight)

| Product | Processes | State it keeps | Size now | Grows with |
|---|---|---|---|---|
| Loamz Chat | chat-server, chat-bridge (Rust) | Postgres `chat` (ciphertext log, directory), blobs (photos, voice, files) | 2 MB dump, tiny blobs | people × messages; media dominates |
| Sign-in | Keycloak | Postgres `keycloak` | small | people |
| Loamz Agents | agents server (monolith profile) | Postgres `loamz_agents`, agent workspaces | small | runs, memory |
| Loamz Data | catalog, controller, worker, SeaweedFS (S3), workspace UI | Iceberg tables on S3 (Parquet), Postgres catalog | **empty today** | **stock-market data: the big one** |
| Edge | Caddy | none | | |
| Backups | systemd timer + rclone | encrypted dumps | 2 MB/day | slowly |

Rule: Chat, Sign-in and Agents are small and fit anywhere. **Data decides the disk, the memory and the money.**

## 2. What is free (confirm in each console)

| Resource | Allowance | Notes |
|---|---|---|
| Oracle compute (Arm) | 4 cores, 24 GB total | one VM at 2 cores / 12 GB today; the other half is unused |
| Oracle block storage | **200 GB total, boot disks included** | VM1 boot is 100 GB, so **about 100 GB is left** for a data volume or a second VM |
| Oracle Object Storage | 20 GB (Standard, Infrequent, Archive combined; sources vary) | Archive: 90-day minimum, slow retrieval |
| Oracle outbound data | 10 TB/month | fine |
| Cloudflare R2 | 10 GB, then $0.015/GB-month, **no download fees** | best place for what people download |
| Backblaze B2 | 10 GB, then $0.006/GB-month | cheapest for cold data |
| GitHub Actions, Resend, Cloudflare Tunnel | free tiers | not storage |

## 3. Sizing the stock-market data (the number we must pin down)

Parquet with compression is about 8 to 15x smaller than CSV. Rough sizes for 5,000 instruments over 20 years:

| Granularity | Rows | Compressed |
|---|---|---|
| Daily bars (OHLCV) | about 25 M | under 1 GB |
| 5-minute bars | about 2 B | about 25 to 40 GB |
| 1-minute bars | about 10 B | about 100 to 150 GB |
| Ticks / order book | tens of billions | far beyond free storage; keep only recent history hot |

So **100 to 200 GB is plausible only if you keep 1-minute bars (or ticks for a short window)**. Daily and 5-minute data fit in the free 100 GB comfortably.

## 4. Storage tiers (the placement rule)

```
 HOT   /data volume on the VM (Oracle block, up to ~100 GB)
       Postgres, SeaweedFS (Iceberg Parquet), last 12-24 months at fine granularity, agent workspaces
       read by DuckDB/Polars at local-disk speed
 WARM  Cloudflare R2   photos/voice/files (E2EE ciphertext), older stock data people query sometimes
       zero download fees, edge delivery
 COLD  Backblaze B2    daily database dumps (second provider), old stock partitions, raw vendor files
       Oracle Archive  monthly database dumps (12 months), final raw archives
```

Data moves down the tiers by age (Iceberg partitions by month; compaction job already exists). Hot never holds more than it needs.

## 5. Compute placement

- One VM (2 cores / 12 GB) holds Chat, Keycloak, Agents and Postgres: about 3 GB in use today.
- Data platform adds about 5 GB (SeaweedFS, controller, one worker, UI). That fits in 12 GB but leaves little spare, so **heavy ingest and backfills must not run on the VM**: do them on your own machine, write Parquet, then upload. The VM only serves queries.
- If CPU or memory pressure shows up, create the **second free VM (2 cores / 12 GB) for Data** and move SeaweedFS and workers there. Its boot disk comes out of the same 200 GB, so then the data volume is 50 GB and warm/cold tiers carry more.

## 6. Decisions to make (in order)

1. How fine is the stock data (daily, 5-minute, 1-minute, ticks), how many instruments, how many years? This sets the tier sizes above.
2. Accept about $2 to $3 a month once data passes the free tiers (200 GB on B2 is about $1.20, on R2 about $3)? The alternative is dropping fine-grained history.
3. One VM now, second VM only when measurements say so (recommended).

## 7. Plan after the decisions

1. Attach a 100 GB block volume as `/data`; move Postgres and SeaweedFS onto it; weekly volume backups.
2. Backups: daily to B2, monthly to Oracle Archive, local 14 days; remove backup files from R2.
3. Media to R2 with short-lived links for chat members only.
4. Data platform on the VM against your real stock partitions; measure query times; tune partitioning (symbol group, month).
5. Monitor disk, memory and request counts; alarm before any free limit is hit.
