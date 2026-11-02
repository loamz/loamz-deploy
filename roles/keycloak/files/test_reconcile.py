"""reconcile.py against an in-memory Keycloak: it creates what is missing, corrects what differs, adopts without duplicating
mappers, is idempotent, and deletes only with --prune and only what it made."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reconcile  # noqa: E402
import validate  # noqa: E402

REGISTRY = Path(__file__).resolve().parents[3] / "products"


class Fake:
    def __init__(self, clients: list[dict[str, Any]] | None = None) -> None:
        self.clients = {c["id"]: c for c in clients or []}
        self.log: list[tuple[str, str]] = []

    def get(self, path: str) -> Any:
        self.log.append(("GET", path))
        if path.startswith("/clients?clientId="):
            wanted = path.split("=", 1)[1]
            return [c for c in self.clients.values() if c["clientId"] == wanted]
        if path.startswith("/clients?max"):
            return copy.deepcopy(list(self.clients.values()))
        raise AssertionError(path)

    def post(self, path: str, body: Any = None) -> Any:
        self.log.append(("POST", path))
        if path == "/clients":
            self.clients[f"id-{body['clientId']}"] = {"id": f"id-{body['clientId']}", "protocolMappers": [], **body}
        else:
            cid = path.split("/")[2]
            self.clients[cid].setdefault("protocolMappers", []).append(body)

    def put(self, path: str, body: Any = None) -> Any:
        self.log.append(("PUT", path))
        self.clients[path.split("/")[2]] = body

    def delete(self, path: str) -> Any:
        self.log.append(("DELETE", path))
        del self.clients[path.split("/")[2]]


def products() -> list[dict[str, Any]]:
    found, _, _, problems = validate.load(REGISTRY)
    assert not problems
    return found


def test_an_empty_realm_gets_every_client_and_audience_then_nothing_more() -> None:
    kc = Fake()
    first = reconcile.converge(kc, products(), apply=True)
    assert any(line == "create client loamz-chat" for line in first)
    assert "client loamz-chat: token carries loamz-agents" in first
    assert "client loamz-agents: token carries loamz-data" in first
    assert reconcile.converge(kc, products(), apply=True) == []
    agents = next(c for c in kc.clients.values() if c["clientId"] == "loamz-agents")
    assert agents["attributes"]["standard.token.exchange.enabled"] == "true" and agents["serviceAccountsEnabled"]


def test_plan_changes_nothing() -> None:
    kc = Fake()
    assert reconcile.converge(kc, products(), apply=False)
    assert kc.clients == {} and not [m for m, _ in kc.log if m != "GET"]


def test_an_audience_mapper_with_another_name_counts_and_is_not_duplicated() -> None:
    kc = Fake()
    reconcile.converge(kc, products(), apply=True)
    chat = next(c for c in kc.clients.values() if c["clientId"] == "loamz-chat")
    chat["protocolMappers"] = [{"name": "agents audience", "protocolMapper": "oidc-audience-mapper", "config": {"included.custom.audience": "loamz-agents"}}]
    assert reconcile.converge(kc, products(), apply=True) == ["client loamz-chat: token carries loamz-chat"]


def test_a_wrong_redirect_is_corrected_unless_urls_are_skipped() -> None:
    kc = Fake()
    reconcile.converge(kc, products(), apply=True)
    chat = next(c for c in kc.clients.values() if c["clientId"] == "loamz-chat")
    chat["redirectUris"] = ["http://localhost:5173/*"]
    assert reconcile.converge(kc, products(), apply=False, urls=False) == []
    assert reconcile.converge(kc, products(), apply=True) == ["update client loamz-chat: redirectUris"]
    assert reconcile.converge(kc, products(), apply=False) == []


def test_prune_deletes_only_what_the_registry_made() -> None:
    kc = Fake()
    reconcile.converge(kc, products(), apply=True)
    kc.clients["a"] = {"id": "a", "clientId": "loamz-gone", "attributes": {"loamz.managed": "registry"}}
    kc.clients["b"] = {"id": "b", "clientId": "somebody-elses", "attributes": {}}
    kept = reconcile.converge(kc, products(), apply=True)
    assert kept == ["client loamz-gone is no longer in the registry (kept; --prune deletes it)"] and "a" in kc.clients
    assert reconcile.converge(kc, products(), apply=True, prune=True) == ["delete client loamz-gone (no longer in the registry)"]
    assert "a" not in kc.clients and "b" in kc.clients
