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

    print("changed: " + ("; ".join(changed) if changed else "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
