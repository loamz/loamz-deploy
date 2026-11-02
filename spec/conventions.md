# Conventions every engine follows

*Version 1, 2 November 2026. The engines (Chat, Agents, Data) are written in two languages and share no server code, so they agree on
these rules in writing and prove it with the vectors in `vectors/`. When a rule changes, change this page and the generator, regenerate,
and copy the vector file into each engine's tests (`python3 spec/generate_vectors.py`; `--check` in CI).*

## Tokens

- Signed with **RS256 only**. The algorithm is never taken from the token: `HS256` and `none` are refused.
- The key is looked up by the header's `kid` in the issuer's key set. No `kid` is invalid; an unknown `kid` is a different error
  (`unknown_key`) so a verifier knows to refresh its keys once.
- Required claims: `exp`, `iss`, `aud`, `sub`. The issuer must equal the configured issuer, and `aud` must contain the product's own audience (`loamz-<product>`).
- `organization` (Keycloak's) is either a list of aliases or an object keyed by alias; either way the caller's organizations are the
  aliases, sorted, without duplicates. A person may have none. `groups` are paths, sorted, without duplicates.
- `loamz_kind` of `agent` or `service` makes the caller a service; anything else is a person.
- `azp` is the client the token was issued to. An `act` claim (`{"sub": ...}`) marks an exchanged token: the caller is the person, the
  actor is `act.sub`. A product may also name clients whose person tokens count as an agent acting (Data: `LOAMZ_DATA_AGENT_CLIENTS`).
- `vectors/token/<audience>.json` holds a key set, signed tokens and the outcome each must give. Times are 2001 and 2100, so no clock is needed.

## The event stream (Agents to its readers)

`POST /api/v1/chat` answers `text/event-stream`: events separated by a blank line, each `event: <type>` (optional) and `data: <json>` whose
`type` is one of `text.delta`, `reasoning.delta`, `tool.call`, `tool.result`, `approval.requested`, `turn.completed`, `run.completed`, `run.failed`,
`run.cancelled`, `ping`. A `ping` carries nothing and is dropped; `data: [DONE]` ends the stream. A stream that ends without a `run.*` event is a
cut connection and a reader reports it as a failure. `vectors/sse/turn.json` holds streams and what a reader must make of them; the reader in
loamz-ui (`@loamz/conversation`) runs them. Agents' emitter is **not** yet tested against them.

## The tenant lifecycle (standard)

A tenant is a Keycloak organization alias. The control plane (Platform) calls a product with its own client's token for the product's audience.
Every call is idempotent: Platform retries from an outbox. A product that speaks this needs no code in Platform, only `tenant.lifecycle: standard`
in its registry file. Agents and Data predate it and have adapters of their own (`tenant.lifecycle: custom`).

| Call | Meaning | Answers |
|---|---|---|
| `PUT /api/v1/tenants/{alias}` | the tenant exists | 200 or 201, also when it already did |
| `PUT /api/v1/tenants/{alias}/entitlements` `{version, values}` | replace the whole set; ignore a `version` older than the one held | 200 |
| `GET /api/v1/tenants/{alias}/usage?period=YYYY-MM` | counters, never content: `{period, meters: {name: number}}` | 200, or 404 for none yet |
| `DELETE /api/v1/tenants/{alias}` | erase everything of the tenant | 202 `{task}`, or 200/204 when already done |
| `GET /api/v1/tenants/{alias}/erasure/{task}` | `{state: pending\|done\|failed}` | 200 |
| `GET /healthz` | alive | 200 |

Entitlement keys are namespaced by product. A refusal (4xx other than 429) is final; 429 and 5xx are retried with growing delay.
Today only the contract and Platform's side exist (`loamz-platform/src/control/`); no product serves it yet.

## Still to write (each needs vectors before it is a rule)

Problem documents (RFC 9457, and Data's "404, never 403"), pagination and
idempotency, vectors for the tenant lifecycle calls, and the webhook signature.
