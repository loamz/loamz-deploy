"""The registry's rules, each shown to fire. Run: python3 -m pytest products/test_validate.py"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

import validate

REAL = Path(validate.__file__).resolve().parent


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    shutil.copytree(REAL, tmp_path / "products", ignore=shutil.ignore_patterns("__pycache__", "test_*", "validate.py"))
    return tmp_path / "products"


def problems(directory: Path) -> list[str]:
    products, edges, host, found = validate.load(directory)
    return found + validate.check(products, edges, host)


def edit(directory: Path, name: str, change) -> None:  # type: ignore[no-untyped-def]
    path = directory / name
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_the_registry_as_written_is_sound(registry: Path) -> None:
    assert problems(registry) == []


def test_data_may_not_call_agents_even_if_its_file_says_so(registry: Path) -> None:
    edit(registry, "data.yml", lambda d: d["identity"].update(calls=["loamz-agents"]))
    found = problems(registry)
    assert any("data may not call agents" in p for p in found), found


def test_an_edge_that_is_not_in_edges_yml_is_refused(registry: Path) -> None:
    edit(registry, "chat.yml", lambda d: d["identity"].update(calls=["loamz-agents", "loamz-data"]))
    assert any("chat may not call data" in p for p in problems(registry))


def test_a_call_to_an_audience_nobody_has_is_refused(registry: Path) -> None:
    edit(registry, "agents.yml", lambda d: d["identity"].update(calls=["loamz-data", "loamz-notes"]))
    assert any("no product has" in p for p in problems(registry))


def test_both_ends_of_a_token_exchange_must_agree(registry: Path) -> None:
    edit(registry, "agents.yml", lambda d: d["identity"].update(calls=[]))
    assert any("does not call loamz-data" in p for p in problems(registry))
    edit(registry, "data.yml", lambda d: d["identity"].update(accepts_exchange_from=["loamz-nobody"]))
    assert any("no product's client" in p for p in problems(registry))


def test_two_products_may_not_share_a_port_a_client_or_an_audience(registry: Path) -> None:
    edit(registry, "data.yml", lambda d: d["deploy"].update(port=8000) or d["urls"].update(internal="http://127.0.0.1:8000"))
    assert any("port 8000 is already" in p for p in problems(registry))
    edit(registry, "data.yml", lambda d: d["identity"]["clients"][0].update(id="loamz-chat"))
    assert any("client loamz-chat is already" in p for p in problems(registry))


def test_a_product_whose_audience_is_not_named_after_it_is_refused(registry: Path) -> None:
    edit(registry, "data.yml", lambda d: d["identity"].update(audience="loamz-warehouse"))
    assert any("by convention it is loamz-data" in p for p in problems(registry))


def test_the_products_must_fit_in_the_machines_memory(registry: Path) -> None:
    edit(registry, "data.yml", lambda d: d["deploy"].update(memory_mb=6000))
    found = problems(registry)
    assert any("at least 1792 MB is required" in p for p in found), found


def test_a_file_must_be_named_after_its_product_and_match_the_schema(registry: Path) -> None:
    shutil.copy(registry / "data.yml", registry / "warehouse.yml")
    assert any("the file must be data.yml" in p for p in problems(registry))
    (registry / "warehouse.yml").unlink()
    edit(registry, "chat.yml", lambda d: d.pop("agents"))
    assert any("'agents' is a required property" in p for p in problems(registry))


def test_a_public_client_must_redirect_only_to_its_own_host(registry: Path) -> None:
    edit(registry, "chat.yml", lambda d: d["identity"]["clients"][0].update(redirects=["https://evil.example/auth/callback"]))
    assert any("not the app's host" in p for p in problems(registry))


def test_only_mcp_products_are_exported_for_agents():
    import copy
    products = copy.deepcopy(validate.load(REAL)[0])
    assert validate.export_for_agents(products) == []  # today every product is builtin or none
    echo = copy.deepcopy(next(p for p in products if p["id"] == "data"))
    echo.update(id="echo", name="Echo", state="beta")
    echo["agents"] = {"mode": "mcp", "mcp_path": "/mcp", "tools_manifest": "/.well-known/loamz/tools", "safe_tools": ["say"]}
    echo["identity"]["audience"] = "loamz-echo"
    echo["urls"]["internal"] = "http://127.0.0.1:8031"
    [row] = validate.export_for_agents([*products, echo])
    assert row == {"id": "echo", "name": "Echo", "audience": "loamz-echo", "state": "beta", "mcp_url": "http://127.0.0.1:8031/mcp",
                   "manifest_url": "http://127.0.0.1:8031/.well-known/loamz/tools", "safe_tools": ["say"]}
