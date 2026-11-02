#!/usr/bin/env python3
"""Writes spec/vectors/token/<audience>.json: signed example tokens and the outcome every engine's verifier must give.

    python3 spec/generate_vectors.py            rewrite the files (the test key is committed, so the output is stable except for signatures' inputs)
    python3 spec/generate_vectors.py --check    fail if the committed files differ from what would be written

The signing key is a throwaway made for these vectors and is committed on purpose: it protects nothing. Times are far in the
future or the past, so no engine needs a fixed clock. Needs PyJWT and cryptography."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

HERE = Path(__file__).resolve().parent
OUT = HERE / "vectors" / "token"
KEY_FILE = HERE / "vectors" / "test-key.pem"
ISSUER = "https://auth.example.test/realms/loamz"
FUTURE, PAST = 4102444800, 978307200  # 2100-01-01 and 2001-01-01
AUDIENCES = ["loamz-data"]


def key(path: Path) -> rsa.RSAPrivateKey:
    if not path.exists():
        path.write_bytes(
            rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
    return serialization.load_pem_private_key(path.read_bytes(), None)  # type: ignore[return-value]


def jwks(k: rsa.RSAPrivateKey, kid: str) -> dict[str, object]:
    jwk = json.loads(RSAAlgorithm.to_jwk(k.public_key()))
    return {"keys": [{**jwk, "kid": kid, "use": "sig", "alg": "RS256"}]}


def cases(k: rsa.RSAPrivateKey, audience: str) -> list[dict[str, object]]:
    base = {"iss": ISSUER, "aud": audience, "sub": "ana-1", "exp": FUTURE, "azp": "loamz-web"}

    def sign(claims: dict[str, object], kid: str | None = "k1", alg: str = "RS256", secret: object = None) -> str:
        headers = {"kid": kid} if kid else {}
        return jwt.encode(claims, secret if secret is not None else k, algorithm=alg, headers=headers)

    def ok(name: str, token: str, **who: object) -> dict[str, object]:
        return {"name": name, "token": token, "expect": {"ok": True, **who}}

    def bad(name: str, token: str, error: str) -> dict[str, object]:
        return {"name": name, "token": token, "expect": {"ok": False, "error": error}}

    return [
        ok("a person with an organization and groups", sign({**base, "name": "Ana", "email": "ana@acme.test", "organization": ["acme"], "groups": ["/finance/analysts", "/finance/analysts"]}),
           subject="ana-1", kind="person", client="loamz-web", orgs=["acme"], groups=["/finance/analysts"], actor=None),
        ok("a person with no organization", sign(base), subject="ana-1", kind="person", client="loamz-web", orgs=[], groups=[], actor=None),
        ok("organizations given as an object are read by alias", sign({**base, "organization": {"acme": {"id": "x"}, "beta": {}}}),
           subject="ana-1", kind="person", client="loamz-web", orgs=["acme", "beta"], groups=[], actor=None),
        ok("a service account of kind agent", sign({**base, "sub": "svc-1", "azp": "agent-helper", "loamz_kind": "agent"}),
           subject="svc-1", kind="service", client="agent-helper", orgs=[], groups=[], actor=None),
        ok("a token exchanged for an agent acting for a person (act claim)", sign({**base, "azp": "loamz-agents", "act": {"sub": "agent-helper"}}),
           subject="ana-1", kind="person", client="loamz-agents", orgs=[], groups=[], actor="agent-helper"),
        bad("expired", sign({**base, "exp": PAST}), "invalid"),
        bad("wrong issuer", sign({**base, "iss": "https://evil.example.test/realms/loamz"}), "invalid"),
        bad("wrong audience", sign({**base, "aud": "loamz-other"}), "invalid"),
        bad("no subject", sign({k_: v for k_, v in base.items() if k_ != "sub"}), "invalid"),
        bad("a key id the verifier has never seen", sign(base, kid="k-unknown"), "unknown_key"),
        bad("no key id", sign(base, kid=None), "invalid"),
        bad("signed with HS256 using the public key as the secret (algorithm confusion)", sign(base, alg="HS256", secret="x" * 64), "invalid"),
        bad("not a token", "not.a.token", "invalid"),
    ]


def build() -> dict[Path, str]:
    k = key(KEY_FILE)
    files: dict[Path, str] = {}
    for audience in AUDIENCES:
        doc = {
            "about": "Every engine's verifier, configured with this issuer, audience and key set, must give each expected outcome. See spec/conventions.md.",
            "issuer": ISSUER,
            "audience": audience,
            "jwks": jwks(k, "k1"),
            "cases": cases(k, audience),
        }
        files[OUT / f"{audience}.json"] = json.dumps(doc, indent=2) + "\n"
    return files


if __name__ == "__main__":
    wanted = build()
    if "--check" in sys.argv:
        # RS256 signatures are deterministic (PKCS#1 v1.5), so regenerating gives the same bytes.
        stale = [p.name for p, text in wanted.items() if not p.exists() or p.read_text() != text]
        if stale:
            sys.exit(f"vectors are out of date: {', '.join(stale)}; run spec/generate_vectors.py")
        print("vectors up to date")
    else:
        for path, text in wanted.items():
            path.write_text(text)
            print(f"wrote {path.relative_to(HERE.parent)}")
