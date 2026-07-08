#!/usr/bin/env python3
"""Gera hashes compatíveis com app.admin_password_hash.

Uso:
  python scripts/hash_secret.py --context ADMIN --secret 'senha-forte' --pepper 'mesmo-pepper-dos-secrets'
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import secrets


def make_hash(secret: str, context: str, pepper: str) -> str:
    salt = secrets.token_hex(16)
    payload = f"{context}:{salt}:{secret}".encode("utf-8")
    digest = hmac.new(pepper.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"v2${salt}${digest}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", default="ADMIN", help="Use ADMIN para senha administrativa.")
    parser.add_argument("--secret", required=True, help="Senha ou segredo a ser protegido.")
    parser.add_argument("--pepper", required=True, help="Mesmo app.credential_pepper configurado no Streamlit.")
    args = parser.parse_args()
    print(make_hash(args.secret, args.context, args.pepper))


if __name__ == "__main__":
    main()
