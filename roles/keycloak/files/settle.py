#!/usr/bin/env python3
"""Brings a running Keycloak's `loamz` realm in line with what the chat app needs. Safe to run again and again: it
changes only what is missing and says what it changed. Needs only Python's standard library.

  settle.py --url http://127.0.0.1:8081 --password-file /etc/keycloak/admin-password      (on the server, by Ansible)
  settle.py --url http://localhost:8081 --password admin-dev-only                        (the throwaway dev Keycloak)

Why this exists: importing the realm file only happens on the very first start, so settings added later (a profile picture,
"delete my account") must reach a realm that already has people in it, without wiping it.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password")
    ap.add_argument("--password-file")
    ap.add_argument("--realm", default="loamz")
    ap.add_argument("--client", default="loamz-chat")
    # An AI agent's own Keycloak client (a service account): NAME:EMAIL:DISPLAY_NAME:ORGANIZATION[:CHAT_TENANT]. Repeat per agent.
    # ORGANIZATION is the organization its token names (the agents server needs every token to name one; it is created if
    # missing). CHAT_TENANT is "personal" for an agent that serves personal accounts in chat, else empty (it serves ORGANIZATION).
    ap.add_argument("--agent", action="append", default=[])
    # Where each agent client's secret is written (one file per agent, mode 600). Secrets are never printed.
    ap.add_argument("--secret-dir", default="")
    # The audience of the agents API; chat tokens must carry it too so the web app can call the agents server.
    ap.add_argument("--agents-audience", default="loamz-agents")
    a = ap.parse_args()
    password = a.password or open(a.password_file).read().strip()
    changed: list[str] = []

    def call(method, path, data=None, form=None, token=None, ok=(200, 201, 204, 409)):
        headers = {}
        body = None
        if token:
            headers["Authorization"] = "Bearer " + token
        if form is not None:
            body = urllib.parse.urlencode(form).encode()
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(a.url + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read()
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            if e.code in ok:
                return e.code, None
            raise SystemExit(f"{method} {path} -> {e.code} {e.read().decode()[:200]}")

    _, t = call("POST", "/realms/master/protocol/openid-connect/token",
                form={"grant_type": "password", "client_id": "admin-cli", "username": a.user, "password": password})
    tok = t["access_token"]
    r = f"/admin/realms/{a.realm}"

    # 1. Extra attributes on a person (the Google profile picture) are allowed.
    _, prof = call("GET", f"{r}/users/profile", token=tok)
    if prof.get("unmanagedAttributePolicy") != "ENABLED":
        prof["unmanagedAttributePolicy"] = "ENABLED"
        call("PUT", f"{r}/users/profile", data=prof, token=tok)
        changed.append("extra profile attributes allowed")

    # 2. The chat app's token carries the picture.
    _, clients = call("GET", f"{r}/clients?clientId={a.client}", token=tok)
    if clients:
        c = clients[0]
        if not any(m["name"] == "picture" for m in c.get("protocolMappers", [])):
            call("POST", f"{r}/clients/{c['id']}/protocol-mappers/models", token=tok, data={
                "name": "picture", "protocol": "openid-connect", "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {"user.attribute": "picture", "claim.name": "picture", "jsonType.label": "String",
                           "id.token.claim": "true", "access.token.claim": "true", "userinfo.token.claim": "true"}})
            changed.append("picture in the token")

    # 3. Google's picture is copied to the person on every sign-in.
    _, idps = call("GET", f"{r}/identity-provider/instances", token=tok)
    if any(i["alias"] == "google" for i in idps or []):
        _, ms = call("GET", f"{r}/identity-provider/instances/google/mappers", token=tok)
        if not any(m["name"] == "google picture" for m in ms or []):
            call("POST", f"{r}/identity-provider/instances/google/mappers", token=tok, data={
                "name": "google picture", "identityProviderAlias": "google",
                "identityProviderMapper": "oidc-user-attribute-idp-mapper",
                "config": {"syncMode": "FORCE", "claim": "picture", "user.attribute": "picture"}})
            changed.append("Google picture copied on sign-in")

    # 4. "Delete my account" is switched on, and everyone may use it.
    _, action = call("GET", f"{r}/authentication/required-actions/delete_account", token=tok)
    if action and not action.get("enabled"):
        action["enabled"] = True
        call("PUT", f"{r}/authentication/required-actions/delete_account", data=action, token=tok)
        changed.append("delete-account action enabled")
    _, acct = call("GET", f"{r}/clients?clientId=account", token=tok)
    if acct:
        _, role = call("GET", f"{r}/clients/{acct[0]['id']}/roles/delete-account", token=tok)
        _, realm = call("GET", r, token=tok)
        default_id = (realm.get("defaultRole") or {}).get("id")
        if role and default_id:
            _, have = call("GET", f"{r}/roles-by-id/{default_id}/composites", token=tok)
            if not any(x["id"] == role["id"] for x in have or []):
                call("POST", f"{r}/roles-by-id/{default_id}/composites", data=[role], token=tok)
                changed.append("everyone may delete their own account")

    # 5. The chat app's token also carries the agents API audience, so people can call the agents server with it.
    if clients:
        c = clients[0]
        if not any(m["name"] == "agents audience" for m in c.get("protocolMappers", [])):
            call("POST", f"{r}/clients/{c['id']}/protocol-mappers/models", token=tok, data={
                "name": "agents audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
                "consentRequired": False,
                "config": {"included.custom.audience": a.agents_audience, "id.token.claim": "false",
                           "access.token.claim": "true"}})
            changed.append("agents audience in the chat token")

    # 6. Each AI agent has its own service-account client. Its token says `loamz_kind: agent` (only this client's mapper can set
    #    that, so no person can pretend to be an agent), is meant for chat and for the agents API, and names its organization.
    for spec in a.agent:
        parts = spec.split(":")
        if len(parts) < 3:
            raise SystemExit(f"--agent wants NAME:EMAIL:DISPLAY_NAME[:ORGANIZATION], got {spec!r}")
        name, email, display = parts[0], parts[1], parts[2]
        org = parts[3] if len(parts) > 3 else ""
        chat_tenant = parts[4] if len(parts) > 4 else ""
        client_id = f"agent-{name}"
        _, found = call("GET", f"{r}/clients?clientId={client_id}", token=tok)
        if not found:
            call("POST", f"{r}/clients", token=tok, data={
                "clientId": client_id, "name": display, "enabled": True, "protocol": "openid-connect",
                "publicClient": False, "serviceAccountsEnabled": True, "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False, "implicitFlowEnabled": False, "clientAuthenticatorType": "client-secret"})
            changed.append(f"agent client {client_id}")
            _, found = call("GET", f"{r}/clients?clientId={client_id}", token=tok)
        cid = found[0]["id"]
        have = {m["name"] for m in found[0].get("protocolMappers", [])}

        def mapper(mname, kind, config):
            if mname not in have:
                call("POST", f"{r}/clients/{cid}/protocol-mappers/models", token=tok, data={
                    "name": mname, "protocol": "openid-connect", "protocolMapper": kind, "consentRequired": False,
                    "config": config})
                changed.append(f"{client_id}: {mname}")
        mapper("agent kind", "oidc-hardcoded-claim-mapper", {"claim.name": "loamz_kind", "claim.value": "agent",
               "jsonType.label": "String", "access.token.claim": "true", "id.token.claim": "false",
               "userinfo.token.claim": "false"})
        if chat_tenant:
            mapper("chat tenant", "oidc-hardcoded-claim-mapper", {"claim.name": "loamz_chat_tenant", "claim.value": chat_tenant,
                   "jsonType.label": "String", "access.token.claim": "true", "id.token.claim": "false",
                   "userinfo.token.claim": "false"})
        mapper("chat audience", "oidc-audience-mapper", {"included.custom.audience": a.client, "access.token.claim": "true",
               "id.token.claim": "false"})
        mapper("agents audience", "oidc-audience-mapper", {"included.custom.audience": a.agents_audience,
               "access.token.claim": "true", "id.token.claim": "false"})
        # The token carries the organization claim only if the client has the organization scope.
        _, have_scopes = call("GET", f"{r}/clients/{cid}/default-client-scopes", token=tok)
        if not any(x["name"] == "organization" for x in have_scopes or []):
            _, all_scopes = call("GET", f"{r}/client-scopes", token=tok)
            wanted = [x for x in all_scopes or [] if x["name"] == "organization"]
            if wanted:
                call("PUT", f"{r}/clients/{cid}/default-client-scopes/{wanted[0]['id']}", token=tok)
                changed.append(f"{client_id}: organization scope")
        # The service account is a user: give it the address people will add it by, and a name.
        _, su = call("GET", f"{r}/clients/{cid}/service-account-user", token=tok)
        want = {"email": email, "emailVerified": True, "firstName": display, "lastName": ""}
        if any((su.get(k) or ("" if isinstance(v, str) else None)) != v for k, v in want.items()):
            su.update(want)
            call("PUT", f"{r}/users/{su['id']}", data=su, token=tok)
            changed.append(f"{client_id}: address and name")
        # Exactly one organization (the tenant), or none for personal accounts.
        if org:
            _, orgs = call("GET", f"{r}/organizations?search={urllib.parse.quote(org)}&exact=true", token=tok)
            match = [o for o in orgs or [] if o.get("alias") == org]
            if not match:
                call("POST", f"{r}/organizations", token=tok, data={"name": org, "alias": org, "enabled": True,
                     "domains": [{"name": f"{org}.agents.invalid", "verified": False}]})
                changed.append(f"organization {org}")
                _, orgs = call("GET", f"{r}/organizations?search={urllib.parse.quote(org)}&exact=true", token=tok)
                match = [o for o in orgs or [] if o.get("alias") == org]
                if not match:
                    raise SystemExit(f"organization {org!r} could not be created (needed by agent {name})")
            _, members = call("GET", f"{r}/organizations/{match[0]['id']}/members?max=1000", token=tok)
            if not any(m["id"] == su["id"] for m in members or []):
                call("POST", f"{r}/organizations/{match[0]['id']}/members", data=su["id"], token=tok)
                changed.append(f"{client_id}: member of {org}")
        # The secret goes to a file for the services that need it; it is never printed.
        if a.secret_dir:
            import os
            os.makedirs(a.secret_dir, mode=0o750, exist_ok=True)
            os.chmod(a.secret_dir, 0o750)
            _, sec = call("GET", f"{r}/clients/{cid}/client-secret", token=tok)
            path = os.path.join(a.secret_dir, f"{client_id}.secret")
            value = (sec or {}).get("value", "")
            if value and (not os.path.exists(path) or open(path).read().strip() != value):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(value + "\n")
                changed.append(f"{client_id}: secret written")

    print("changed: " + ("; ".join(changed) if changed else "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
