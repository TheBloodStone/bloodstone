"""Read logged-in web wallet session and resolve primary receive address."""

from __future__ import annotations

import os
import re
import sys

WALLET_WEB_DIR = os.environ.get("WALLET_WEB_DIR", "/root/bloodstone-wallet-web")
if WALLET_WEB_DIR not in sys.path:
    sys.path.insert(0, WALLET_WEB_DIR)

import users_db  # noqa: E402
import wallet_rpc  # noqa: E402

LEGACY_ADDR = re.compile(r"^S[1-9A-HJ-NP-Za-km-z]{25,34}$")
BECH32_ADDR = re.compile(r"^stone1[0-9a-z]{20,}$", re.I)


def load_wallet_session_secret() -> str:
    path = os.environ.get("WALLET_WEB_SECRETS", f"{WALLET_WEB_DIR}/secrets.conf")
    if not os.path.isfile(path):
        raise RuntimeError(f"Wallet secrets not found: {path}")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("secret_key="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"secret_key missing in {path}")


WALLET_SESSION_COOKIE = os.environ.get("WALLET_SESSION_COOKIE", "bs_wallet_session")


def _wallet_session_payload():
    import hashlib

    from flask import request
    from flask.json.tag import TaggedJSONSerializer
    from itsdangerous import BadSignature, URLSafeTimedSerializer

    val = request.cookies.get(WALLET_SESSION_COOKIE)
    if not val:
        return None
    serializer = URLSafeTimedSerializer(
        load_wallet_session_secret(),
        salt="cookie-session",
        serializer=TaggedJSONSerializer(),
        signer_kwargs={"key_derivation": "hmac", "digest_method": hashlib.sha1},
    )
    try:
        return serializer.loads(val, max_age=31 * 24 * 60 * 60)
    except BadSignature:
        return None


def current_wallet_user():
    from flask import session

    uid = session.get("user_id")
    if not uid:
        payload = _wallet_session_payload()
        uid = payload.get("user_id") if payload else None
        if uid:
            session["user_id"] = uid
    if not uid:
        return None
    users_db.init_db()
    return users_db.get_user_by_id(uid)


def _wallets_for_user(user) -> set[str]:
    names = {user["wallet_name"]}
    for entry in users_db.get_linked_wallets(user["id"]):
        names.add(entry["wallet_name"])
    return names


def _address_owned_by_user(user, wallet_name: str, address: str) -> bool:
    if wallet_name not in _wallets_for_user(user):
        return False
    if not (LEGACY_ADDR.match(address) or BECH32_ADDR.match(address)):
        return False
    wallet_rpc.ensure_wallet_loaded(wallet_name)
    try:
        info = wallet_rpc.rpc("getaddressinfo", [address], wallet=wallet_name)
        return bool(info.get("ismine"))
    except RuntimeError:
        return False


def _default_primary_address(user) -> str:
    wallet_name = user["wallet_name"]
    wallet_rpc.ensure_wallet_loaded(wallet_name)
    received = wallet_rpc.rpc(
        "listreceivedbyaddress", [0, True, True], wallet=wallet_name
    )
    if received:
        return received[0]["address"]
    return wallet_rpc.rpc("getnewaddress", ["primary"], wallet=wallet_name)


def primary_address_for_user(user) -> str:
    if not user or not user.get("wallet_name"):
        raise RuntimeError("No wallet configured for this account")

    stored_wallet = user.get("primary_receive_wallet")
    stored_address = user.get("primary_receive_address")
    if stored_wallet and stored_address:
        if _address_owned_by_user(user, stored_wallet, stored_address):
            return stored_address

    return _default_primary_address(user)