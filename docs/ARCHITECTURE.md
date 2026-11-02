# The Loamz family: how products fit together

*Written 2 November 2026. This page is the one place that says what the products are, who may depend on whom, and what is checked by a
test rather than by memory. The plan that drives it is the owner's: adding product N should cost one new repository and one file
(`products/<id>.yml`, not written yet), and no change to the other products.*

## The pieces

| Role | Repositories | What it is |
|---|---|---|
| **Engines** | `loamz-chat` (Rust), `loamz-agents` (Python), `loamz-data` (Rust) | The servers, each with its own web app. They talk to each other only through public, versioned APIs. |
| **Clients** | `loamz-python`, `loamz-rs` | Thin public SDKs. Solutions are built on them as a library on top of the engines. They are not engines and hold no server code. `loamz-rs` is a placeholder until a Rust solution needs it. |
| **Solutions** | `loamz-solutions` | Apps built on the engines through the SDKs; it offers tools to Agents over MCP. |
| **UI kit** | `loamz-agents-ui` (made, not pushed or tagged) | `@loamz/design`, `@loamz/auth` (the PKCE core) and `@loamz/conversation` (stream reader, turn state, plain thread), with tests. No app depends on it yet: the design is still copied by script from `loamz-chat`, and Data copies the conversation core with `web/scripts/sync-ui.sh`. |
| **Control plane** | `loamz-platform` (being rebuilt) | Provisioning, plans, entitlements, usage, billing. Never in a request path. |
| **Infrastructure** | `loamz-deploy` (this repository) | Ansible, Keycloak, Caddy, backups, runbooks, and (planned) the product registry. |

One Keycloak realm, `loamz`, signs everyone in. A Keycloak **organization is a tenant**. Each product is one Keycloak client with one audience.

## The rules

| # | Rule | Checked by | Today |
|---|---|---|---|
| R1 | Products call each other only through their public, versioned `/api/v1`; the spec is checked in and a drift test keeps it true. | `make spec` plus `git diff --exit-code` in each producer; a pinned copy and hash in each consumer | Data and Agents each have the spec and a drift test (Agents: `make spec`, 141 paths); the Data SDK vendors Data's spec and tests against it; Chat's protocol and the CI runs are not covered |
| R2 | Allowed edges: Platform to the engines (provision, entitle, usage, erase); Agents to Data; Agents to registered tool servers; Chat to Agents; Solutions to the SDKs. **Data depends on nothing.** Nothing depends on Platform or Solutions. | Data: `server/server/tests/layering.rs`. Agents: import-linter. Web apps: dependency-cruiser | **Data: enforced** (`layering.rs`). Agents has import-linter contracts (engine, runtime, layers) but none for edges to other products. Web apps: no dependency-cruiser. Browser-only optional edges are listed in `products/edges.yml` (`_optional_web`) |
| R3 | One realm; one client and one audience per product. A call from one product to another is an RFC 8693 token exchange for the callee's audience. A user's token is never forwarded. | The product registry validator; a family smoke test | Works for Agents to Data (client `loamz-agents`, audience `loamz-data`). The registry validator checks the graph; `roles/keycloak/files/reconcile.py` makes Keycloak match it (rehearsed on the dev realm, not run on the live one) |
| R4 | A tenant is a Keycloak organization alias. Each product offers idempotent provision, entitlements, usage and erase. No product reads another's database. | Contract tests per adapter | Agents has entitlement and erase endpoints; Data has `POST /api/v1/orgs/{org}/account` and no entitlement, usage or whole-organization erase. Platform's adapters for both and the standard lifecycle are in `loamz-platform/src/control/` (tested with fakes, no store behind them yet) |
| R5 | A product that agents may use ships an MCP server and a tools manifest, and is listed in the registry. | Registry validator | Built in Agents: a product with `agents.mode: mcp` is offered from its tools manifest, called with the person's exchanged token, and listed in the marketplace (tested against a real MCP server; no product serves a manifest yet). Data's tools are still built in |
| R6 | Web apps depend on `@loamz/*` packages by exact version. No app imports another app. | CI: no `src/design` copy | Not yet: three copies of the design system until `loamz-agents-ui` is pushed and tagged |
| R7 | One product tells another by a signed, idempotent webhook from an outbox. | A consumer test | Not built |
| R8 | **Clients stay thin.** The SDKs are written from each engine's checked-in API description, carry the API's version, hold no server code and no engines. Server conventions (token claims, problem documents, stream frames) are a written spec plus test vectors that each engine runs, not shared code. | `.importlinter` and a dependency guard in the SDK repos; vectors in each engine's tests | Mostly: token vectors run in Data, Chat and Agents; the SDKs have `.importlinter` and a no-server-library test; the Data SDK is held to a vendored spec. Problem-document vectors, the Agents emitter against the stream vectors, and `oasdiff` are not done |
| R9 | Each repository enforces its own edges in CI. | The above | Data's CI has the layering and conformance tests; the other repos run theirs but several workflows (including this repository's) have never run on GitHub |

## Why shared code is not shared code

The engines are written in two languages, and the SDKs are for people outside. So the three token verifiers (Rust in Chat and Data,
Python in Agents) stay separate and agree through **written conventions and conformance vectors**, a set of signed example tokens and
expected outcomes that every engine's tests must pass. A shared Rust crate for Chat and Data is worth making only when a third Rust
service needs it, or a security fix lands in one copy and the vectors show the other lagging twice. It would live in its own private repository,
never in an SDK.

## Adding a product (the goal, and what is missing)

Before the registry, a new product reached Agents by changing five or six repositories (the Agents catalog and builders, the Keycloak realm template and
`settle.py`, an icon in Chat, a block of settings here, then lock bumps). The goal is: a new repository, plus `products/<id>.yml` here.
The pieces now exist and are tested in isolation (the registry and validator, the Keycloak reconciler, the registry-driven Agents tool list, the
generic `product` deploy role, the control plane's adapters, and a CI test that a new product is one file), but **none has run against the live machine**. The order, and why, is in the plan the owner approved on 2 November 2026
(`~/.claude/plans/i-want-to-build-eager-dusk.md` on the owner's machine).

## What is true of the live system

One Oracle Always Free machine (2 cores, 12 GB) runs Postgres, Keycloak, Chat, Agents, the chat bridges and Caddy. Data is not deployed.
There is no staging, no alerting that anyone has set up, and no restore that has been tried end to end (see `docs/runbooks/`). Every product
added to that machine multiplies those gaps, which is why the first phase of the plan is about them.
