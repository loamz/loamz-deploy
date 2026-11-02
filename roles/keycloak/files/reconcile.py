#!/usr/bin/env python3
"""Makes Keycloak's `loamz` realm match the product registry (products/*.yml): every product's clients, their redirects and origins,
the audience each token carries, and which clients may exchange tokens.

    reconcile.py --url http://127.0.0.1:8081 --password-file /etc/keycloak/admin-password --plan
    reconcile.py --url http://127.0.0.1:8081 --password-file /etc/keycloak/admin-password --apply

  --plan    changes nothing; lists what would change; exit 0 when the realm already matches, 2 when it would change
  --apply   makes the changes, additive ones first
  --skip-urls  leave redirects and origins alone (local Keycloak)
  --prune   with --apply, also deletes clients this script made (attribute loamz.managed=registry) that are no longer in the registry

It only adds and corrects. A client it did not make is adopted (it gets the attribute) and its redirects, origins and exchange flag are
set to the registry's. An audience is "carried" if any audience mapper on the client names it, whatever that mapper is called, so the
mappers the realm template and settle.py made are left alone and nothing is duplicated. Secrets are never rotated and never printed;
with --secret-dir a confidential client's secret is written to <id>.secret (mode 600).
Needs PyYAML and jsonschema (the registry is read with products/validate.py) and Python's standard library otherwise."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "products"))
import validate  # noqa: E402

MANAGED = {"loamz.managed": "registry"}
EXCHANGE = "standard.token.exchange.enabled"
PKCE = "pkce.code.challenge.method"

Json = dict[str, Any]


class Admin(Protocol):
    def get(self, path: str) -> Any: ...
    def post(self, path: str, body: Any = None) -> Any: ...
    def put(self, path: str, body: Any = None) -> Any: ...
    def delete(self, path: str) -> Any: ...


class Keycloak:
    def __init__(self, url: str, user: str, password: str, realm: str) -> None:
        self.url, self.base = url.rstrip("/"), f"/admin/realms/{realm}"
        form = urllib.parse.urlencode({"grant_type": "password", "client_id": "admin-cli", "username": user, "password": password})
        token = self._send("POST", "/realms/master/protocol/openid-connect/token", form.encode(), "application/x-www-form-urlencoded")
        self.token = token["access_token"]

    def _send(self, method: str, path: str, body: bytes | None, content_type: str | None = None, token: str | None = None) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(self.url + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read()
                return json.loads(text) if text else None
        except urllib.error.HTTPError as error:
            raise SystemExit(f"{method} {path} -> {error.code} {error.read().decode()[:200]}") from None

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        return self._send(method, self.base + path, data, "application/json" if data else None, self.token)

    def get(self, path: str) -> Any:
        return self._call("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self._call("POST", path, body)

    def put(self, path: str, body: Any = None) -> Any:
        return self._call("PUT", path, body)

    def delete(self, path: str) -> Any:
        return self._call("DELETE", path)


def audience_mapper(audience: str) -> Json:
    return {
        "name": f"{audience} audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper", "consentRequired": False,
        "config": {"included.client.audience": audience, "id.token.claim": "false", "access.token.claim": "true", "introspection.token.claim": "true"},
    }


def carried(client: Json) -> set[str]:
    """The audiences this client's access token names, by any audience mapper."""
    found: set[str] = set()
    for mapper in client.get("protocolMappers") or []:
        if mapper.get("protocolMapper") == "oidc-audience-mapper":
            config = mapper.get("config") or {}
            found |= {config[k] for k in ("included.client.audience", "included.custom.audience") if config.get(k)}
    return found


def desired(products: list[Json]) -> dict[str, Json]:
    """client id -> {representation fields, 'audiences': set}, from the registry."""
    wanted: dict[str, Json] = {}
    for product in products:
        ident = product["identity"]
        for client in ident["clients"]:
            public = client["type"] == "public"
            audiences = {ident["audience"], *ident["web_extra_audiences"]} if public else set()
            if client.get("exchange"):
                audiences |= set(ident["calls"])
            wanted[client["id"]] = {
                "name": product["name"] if public else f"{product['name']}: {client['id']}",
                "publicClient": public,
                "standardFlowEnabled": public,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": bool(client.get("service_account")),
                "redirectUris": sorted(client.get("redirects", [])),
                "webOrigins": sorted(client.get("origins", [])),
                "attributes": {**MANAGED, **({PKCE: "S256"} if public else {}), **({EXCHANGE: "true"} if client.get("exchange") else {})},
                "audiences": audiences,
            }
    return wanted


def differs(have: Json, want: Json, *, urls: bool = True) -> list[str]:
    """Which of the registry's fields the live client does not have."""
    out = [k for k in ("publicClient", "standardFlowEnabled", "serviceAccountsEnabled") if bool(have.get(k)) != want[k]]
    out += [k for k in ("redirectUris", "webOrigins") if urls and sorted(have.get(k) or []) != want[k]]
    attributes = have.get("attributes") or {}
    out += [f"attribute {k}" for k, v in want["attributes"].items() if attributes.get(k) != v]
    return out


def converge(kc: Admin, products: list[Json], *, apply: bool, prune: bool = False, secret_dir: str = "", urls: bool = True) -> list[str]:
    """The changes needed (and made, when `apply`), one line each. Additive changes come first."""
    changes: list[str] = []
    wanted = desired(products)
    live = {c["clientId"]: c for c in kc.get("/clients?max=1000")}
    for client_id in sorted(wanted):
        want, have = wanted[client_id], live.get(client_id)
        fields = {k: v for k, v in want.items() if k != "audiences"}
        if have is None:
            changes.append(f"create client {client_id}")
            if apply:
                kc.post("/clients", {"clientId": client_id, "enabled": True, **fields})
                have = next(c for c in kc.get(f"/clients?clientId={urllib.parse.quote(client_id)}"))
        else:
            wrong = differs(have, want, urls=urls)
            if wrong:
                changes.append(f"update client {client_id}: {', '.join(wrong)}")
                if apply:
                    kc.put(f"/clients/{have['id']}", {**have, **{k: v for k, v in fields.items() if k != "attributes" and (urls or k not in ("redirectUris", "webOrigins"))},
                                                       "attributes": {**(have.get("attributes") or {}), **want["attributes"]}})
        have_audiences = carried(have) if have else set()
        for audience in sorted(want["audiences"] - have_audiences):
            changes.append(f"client {client_id}: token carries {audience}")
            if apply and have:
                kc.post(f"/clients/{have['id']}/protocol-mappers/models", audience_mapper(audience))
        if apply and have and secret_dir and not want["publicClient"]:
            write_secret(kc, have["id"], Path(secret_dir) / f"{client_id}.secret")
    stale = sorted(c for c, v in live.items() if (v.get("attributes") or {}).get("loamz.managed") == "registry" and c not in wanted)
    for client_id in stale:
        changes.append(f"delete client {client_id} (no longer in the registry)" if prune else f"client {client_id} is no longer in the registry (kept; --prune deletes it)")
        if apply and prune:
            kc.delete(f"/clients/{live[client_id]['id']}")
    return changes


def write_secret(kc: Admin, internal_id: str, path: Path) -> None:
    value = (kc.get(f"/clients/{internal_id}/client-secret") or {}).get("value", "")
    if not value or (path.exists() and path.read_text().strip() == value):
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password")
    ap.add_argument("--password-file")
    ap.add_argument("--realm", default="loamz")
    ap.add_argument("--registry", default=str(Path(__file__).resolve().parents[3] / "products"))
    ap.add_argument("--secret-dir", default="")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--skip-urls", action="store_true", help="leave redirects and origins alone (a local Keycloak serves other addresses than the registry's)")
    a = ap.parse_args()
    products, _, _, problems = validate.load(Path(a.registry))
    if problems:
        sys.exit("the registry has problems (run products/validate.py):\n  " + "\n  ".join(problems))
    password = a.password or Path(a.password_file).read_text().strip()
    changes = converge(Keycloak(a.url, a.user, password, a.realm), products, apply=a.apply, prune=a.prune, secret_dir=a.secret_dir, urls=not a.skip_urls)
    for line in changes:
        print(("done: " if a.apply else "would: ") + line)
    print(f"{'applied' if a.apply else 'plan'}: " + (f"{len(changes)} change(s)" if changes else "the realm matches the registry"))
    return 2 if changes and a.plan else 0


if __name__ == "__main__":
    sys.exit(main())
