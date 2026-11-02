#!/usr/bin/env python3
"""Checks the product registry: every products/<id>.yml against schema.json, and the rules between products (docs/ARCHITECTURE.md).

    python3 products/validate.py [--export-agents FILE] [--export-registry FILE]   (the export is what the Agents server reads to offer products' tools)
    exit 0 and one line when it is sound; every problem listed, exit 1, when it is not

Needs PyYAML and jsonschema. The rules that need more than one file live here: who may call whom (edges.yml), that both ends of a
token exchange agree, that clients, audiences, ports and hosts are unique, and that the products fit in the machine's memory (host.yml).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jsonschema
import yaml

HERE = Path(__file__).resolve().parent
RESERVED = {"edges.yml", "host.yml"}

Product = dict[str, Any]


def load(directory: Path) -> tuple[list[Product], dict[str, list[str]], dict[str, Any], list[str]]:
    """The products, the allowed edges, the host budget, and the problems met while reading them."""
    problems: list[str] = []
    schema = json.loads((directory / "schema.json").read_text())
    products: list[Product] = []
    for path in sorted(directory.glob("*.yml")):
        if path.name in RESERVED:
            continue
        product = yaml.safe_load(path.read_text())
        errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(product), key=lambda e: list(e.path))
        problems += [f"{path.name}: {'/'.join(map(str, e.path)) or 'file'}: {e.message}" for e in errors]
        if not errors:
            if product["id"] != path.stem:
                problems.append(f"{path.name}: id is {product['id']!r}, the file must be {product['id']}.yml")
            products.append(product)
    edges = yaml.safe_load((directory / "edges.yml").read_text()) or {}
    host = yaml.safe_load((directory / "host.yml").read_text())
    return products, edges, host, problems


def export_for_agents(products: list[Product]) -> list[dict[str, Any]]:
    """What the Agents server needs to offer a product's tools: only products that serve tools over MCP. Written to the file named by
    LOAMZ_AGENTS_PRODUCTS__FILE; the Agents server reads JSON, so it needs no YAML."""
    return [
        {
            "id": p["id"], "name": p["name"], "audience": p["identity"]["audience"], "state": p["state"],
            "mcp_url": p["urls"]["internal"] + p["agents"]["mcp_path"],
            "manifest_url": p["urls"]["internal"] + p["agents"]["tools_manifest"],
            "safe_tools": sorted(p["agents"].get("safe_tools", [])),
        }
        for p in products
        if p["agents"]["mode"] == "mcp" and p["state"] != "planned"
    ]


def export_for_platform(products: list[Product]) -> list[dict[str, Any]]:
    """What the control plane needs: every product, its audience, where to call it and which tenant lifecycle it speaks."""
    return [
        {"id": p["id"], "name": p["name"], "state": p["state"], "audience": p["identity"]["audience"],
         "internal": p["urls"]["internal"], "lifecycle": p["tenant"]["lifecycle"]}
        for p in products
    ]


def check(products: list[Product], edges: dict[str, list[str]], host: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    ids = [p["id"] for p in products]
    for name in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"product id {name} is used twice")

    by_audience: dict[str, Product] = {}
    clients: dict[str, tuple[Product, dict[str, Any]]] = {}
    for p in products:
        pid, ident = p["id"], p["identity"]
        if ident["audience"] != f"loamz-{pid}":
            problems.append(f"{pid}: audience is {ident['audience']}, by convention it is loamz-{pid}")
        if ident["audience"] in by_audience:
            problems.append(f"{pid}: audience {ident['audience']} is already {by_audience[ident['audience']]['id']}'s")
        by_audience[ident["audience"]] = p
        for c in ident["clients"]:
            if c["id"] in clients:
                problems.append(f"{pid}: client {c['id']} is already {clients[c['id']][0]['id']}'s")
            clients[c["id"]] = (p, c)
            if c["type"] == "public" and not c.get("redirects"):
                problems.append(f"{pid}: public client {c['id']} has no redirect addresses")
            app_host = urlsplit(p["urls"].get("app", "")).hostname
            for uri in c.get("redirects", []):
                if urlsplit(uri).hostname != app_host:
                    problems.append(f"{pid}: client {c['id']} redirects to {uri}, which is not the app's host {app_host}")

    # Rule R2: edges. Every edges key and value is a product, and every audience a product calls belongs to an allowed callee.
    for caller, callees in edges.items():
        for name in [caller, *callees]:
            if name not in ids:
                problems.append(f"edges.yml names {name}, which is not a product")
    for p in products:
        wanted = list(p["identity"]["calls"]) + list(p["identity"]["web_extra_audiences"])
        for audience in wanted:
            callee = by_audience.get(audience)
            if callee is None:
                problems.append(f"{p['id']}: calls audience {audience}, which no product has")
            elif callee["id"] not in edges.get(p["id"], []):
                problems.append(f"{p['id']} may not call {callee['id']}: add it to edges.yml if that edge is intended")
        for extra in p["identity"]["web_extra_audiences"]:
            if extra not in p["identity"]["calls"]:
                problems.append(f"{p['id']}: web_extra_audiences has {extra}, which is not in calls")

    # Rule R3: both ends of a token exchange agree.
    for p in products:
        for cid in p["identity"]["accepts_exchange_from"]:
            owner = clients.get(cid)
            if owner is None:
                problems.append(f"{p['id']}: accepts exchange from {cid}, which is no product's client")
                continue
            caller, client = owner
            if not client.get("exchange"):
                problems.append(f"{p['id']}: accepts exchange from {cid}, whose token exchange is not enabled")
            if p["identity"]["audience"] not in caller["identity"]["calls"]:
                problems.append(f"{p['id']}: accepts exchange from {cid}, but {caller['id']} does not call {p['identity']['audience']}")

    # Ports and hosts are one machine's: no two products may share one.
    seen_ports: dict[int, str] = {}
    seen_hosts: dict[str, str] = {}
    for p in products:
        deploy = p["deploy"]
        if deploy["kind"] in ("binary", "python"):
            missing = [k for k in ("unit", "port", "health", "memory_mb") if k not in deploy]
            if missing:
                problems.append(f"{p['id']}: a {deploy['kind']} product needs {', '.join(missing)} in deploy")
        if "port" in deploy:
            if deploy["port"] in seen_ports:
                problems.append(f"{p['id']}: port {deploy['port']} is already {seen_ports[deploy['port']]}'s")
            seen_ports[deploy["port"]] = p["id"]
            if urlsplit(p["urls"]["internal"]).port != deploy["port"]:
                problems.append(f"{p['id']}: urls.internal and deploy.port name different ports")
        app = urlsplit(p["urls"].get("app", "")).hostname
        if app:
            if app in seen_hosts:
                problems.append(f"{p['id']}: host {app} is already {seen_hosts[app]}'s")
            seen_hosts[app] = p["id"]

    # The machine's memory.
    used = sum(p["deploy"].get("memory_mb", 0) for p in products)
    reserved = sum(host["reserved_mb"].values())
    free = host["memory_mb"] - reserved - used
    if free < host["min_headroom_mb"]:
        problems.append(
            f"products need {used} MB and the infrastructure {reserved} MB of {host['memory_mb']} MB: "
            f"{free} MB would be left, at least {host['min_headroom_mb']} MB is required"
        )
    return problems


def main(argv: list[str]) -> int:
    platform = None
    if "--export-registry" in argv:
        at = argv.index("--export-registry")
        platform = Path(argv[at + 1])
        argv = argv[:at] + argv[at + 2:]
    export = None
    if "--export-agents" in argv:
        at = argv.index("--export-agents")
        export = Path(argv[at + 1])
        argv = argv[:at] + argv[at + 2:]
    directory = Path(argv[1]) if len(argv) > 1 else HERE
    products, edges, host, problems = load(directory)
    problems += check(products, edges, host)
    if problems:
        print("\n".join(f"  {p}" for p in problems), file=sys.stderr)
        print(f"registry: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    if platform:
        platform.write_text(json.dumps(export_for_platform(products), indent=2) + "\n")
    if export:
        export.write_text(json.dumps(export_for_agents(products), indent=2) + "\n")
    used = sum(p["deploy"].get("memory_mb", 0) for p in products)
    reserved = sum(host["reserved_mb"].values())
    print(f"registry ok: {len(products)} products ({', '.join(p['id'] for p in products)}); "
          f"{used} MB of products + {reserved} MB infrastructure, {host['memory_mb'] - used - reserved} MB free of {host['memory_mb']} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
