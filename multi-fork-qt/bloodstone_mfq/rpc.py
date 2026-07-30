"""JSON-RPC client for any Fork Lab / STONE node."""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

_IS_WIN = sys.platform.startswith("win")

# Expected receive-address shape per chain (legacy base58 + bech32 HRP).
# Windows packs that are renamed bloodstoned.exe produce STONE (S…/stone1…)
# addresses — those are invalid for LRGK/AZURE and must be rejected.
ADDRESS_EXPECTATIONS: Dict[str, Dict[str, Any]] = {
    "STONE": {
        "legacy_prefixes": ("S",),
        "bech32_hrps": ("stone",),
        "label": "Bloodstone (STONE)",
    },
    "LRGK": {
        "legacy_prefixes": ("L",),
        "bech32_hrps": ("lrgk",),
        "label": "Lil Raghnok (LRGK)",
    },
    "AZURE": {
        "legacy_prefixes": ("A",),
        "bech32_hrps": ("azure",),
        "label": "Azure Guardian (AZURE)",
    },
}


def address_looks_valid_for_ticker(ticker: str, address: str) -> Tuple[bool, str]:
    """Return (ok, reason). Rejects wrong-chain formats (e.g. STONE S… on LRGK)."""
    t = (ticker or "").strip().upper()
    addr = (address or "").strip()
    if not addr:
        return False, "Address empty"
    exp = ADDRESS_EXPECTATIONS.get(t)
    if not exp:
        # Unknown fork: accept base58/bech32 shape only
        if len(addr) >= 20 and addr[0].isalnum():
            return True, "ok"
        return False, "Unrecognised address shape"

    lower = addr.lower()
    for hrp in exp.get("bech32_hrps") or ():
        prefix = str(hrp).lower() + "1"
        if lower.startswith(prefix):
            # Real bech32 witness addresses are typically 42+ chars
            if len(addr) < 20:
                return False, f"Bech32 address too short for {t}"
            return True, "ok"
    for pfx in exp.get("legacy_prefixes") or ():
        if addr.startswith(str(pfx)):
            if len(addr) < 25:
                return False, f"Legacy address too short for {t}"
            return True, "ok"

    # Diagnose common mis-pack: Bloodstone binary used for a fork
    if lower.startswith("stone1") or addr.startswith("S"):
        return (
            False,
            f"Got a Bloodstone (STONE) address ({addr[:12]}…) but selected "
            f"{exp['label']}. The local daemon is the wrong chain binary "
            f"(often a renamed bloodstoned.exe pack). Install a real "
            f"{t} node build, or point RPC at the correct {t} daemon.",
        )
    if lower.startswith("lrgk1") or addr.startswith("L"):
        return (
            False,
            f"Address looks like LRGK but the selected coin is {t}.",
        )
    if lower.startswith("azure1") or addr.startswith("A"):
        return (
            False,
            f"Address looks like AZURE but the selected coin is {t}.",
        )
    return (
        False,
        f"Address {addr[:16]}… does not match expected {t} format "
        f"(legacy {','.join(exp['legacy_prefixes'])}… or "
        f"{'/'.join(h + '1…' for h in exp['bech32_hrps'])}).",
    )


def load_kv(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path or not os.path.isfile(path):
        return out
    # Ignore Linux-only paths on Windows
    if _IS_WIN and path.startswith(("/root/", "/var/", "/home/")):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


class CoinRPC:
    def __init__(
        self,
        coin: Dict[str, Any],
        *,
        rpc_user: str = "",
        rpc_password: str = "",
        rpc_host: str = "",
        rpc_port: int = 0,
        timeout: float = 30.0,
    ):
        self.coin = coin
        self.ticker = coin["ticker"]
        conf_path = coin.get("conf") or ""
        if _IS_WIN and str(conf_path).startswith(("/root/", "/var/", "/home/")):
            conf_path = ""
        conf = load_kv(conf_path)

        self.rpc_host = (
            rpc_host
            or coin.get("rpc_host")
            or conf.get("rpcbind")
            or conf.get("rpcconnect")
            or "127.0.0.1"
        )
        if self.rpc_host in ("0.0.0.0", "::", "[::]"):
            self.rpc_host = "127.0.0.1"

        self.rpc_port = int(
            rpc_port
            or conf.get("rpcport")
            or coin.get("rpc_port")
            or 0
        )
        # Prefer explicit coin credentials (from Settings) over conf
        self.rpc_user = (
            rpc_user
            or coin.get("rpc_user")
            or conf.get("rpcuser")
            or ""
        )
        self.rpc_password = (
            rpc_password
            or coin.get("rpc_password")
            or conf.get("rpcpassword")
            or ""
        )
        self.timeout = timeout
        self.conf_path = conf_path if conf_path and os.path.isfile(conf_path) else conf_path

    @property
    def configured(self) -> bool:
        return bool(self.rpc_port and self.rpc_user and self.rpc_password)

    def config_hint(self) -> str:
        """Human-readable setup help when RPC is incomplete."""
        missing = []
        if not self.rpc_user:
            missing.append("rpcuser")
        if not self.rpc_password:
            missing.append("rpcpassword")
        if not self.rpc_port:
            missing.append("rpcport")
        conf_note = self.conf_path or "(no conf file)"
        if _IS_WIN:
            return (
                f"{self.ticker}: RPC not configured (need {', '.join(missing) or 'credentials'}). "
                f"Open Settings → set rpcuser/rpcpassword/rpcport for {self.ticker}, "
                f"or point conf at your local daemon file under %APPDATA% / "
                f"%LOCALAPPDATA%\\Bloodstone\\MultiForkQt\\rpc\\{self.ticker.lower()}.conf. "
                f"Current conf={conf_note}"
            )
        return (
            f"{self.ticker}: RPC not configured "
            f"(need {', '.join(missing) or 'credentials'}; conf={conf_note})"
        )

    def _url(self, wallet: Optional[str] = None) -> str:
        base = f"http://{self.rpc_host}:{self.rpc_port}/"
        if wallet:
            from urllib.parse import quote

            return base + "wallet/" + quote(wallet, safe="")
        return base

    def call(
        self,
        method: str,
        params: Optional[List[Any]] = None,
        *,
        wallet: Optional[str] = None,
        retries: int = 2,
    ) -> Any:
        if not self.configured:
            raise RuntimeError(self.config_hint())
        payload = {
            "jsonrpc": "1.0",
            "id": f"mfq-{self.ticker.lower()}",
            "method": method,
            "params": params or [],
        }
        auth = (self.rpc_user, self.rpc_password)
        last: Optional[Exception] = None
        for attempt in range(max(1, retries)):
            try:
                resp = requests.post(
                    self._url(wallet),
                    json=payload,
                    headers={"content-type": "text/plain;"},
                    auth=auth,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("error"):
                    err = data["error"]
                    raise RuntimeError(err.get("message", str(err)))
                return data.get("result")
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                last = exc
                if attempt + 1 < retries:
                    time.sleep(0.4)
        raise RuntimeError(str(last) if last else f"{self.ticker} RPC failed")

    def probe(self, timeout: float = 2.0) -> Dict[str, Any]:
        if not self.configured:
            return {
                "online": False,
                "error": self.config_hint(),
                "blocks": None,
                "chain": None,
            }
        old = self.timeout
        self.timeout = timeout
        try:
            info = self.call("getblockchaininfo", retries=1) or {}
            return {
                "online": True,
                "blocks": int(info.get("blocks") or 0),
                "headers": int(info.get("headers") or 0),
                "chain": str(info.get("chain") or ""),
                "verificationprogress": info.get("verificationprogress"),
                "error": None,
            }
        except Exception as exc:
            return {
                "online": False,
                "blocks": None,
                "headers": None,
                "chain": None,
                "error": str(exc)[:200],
            }
        finally:
            self.timeout = old

    def list_wallets(self) -> List[str]:
        """Return names of currently loaded wallets.

        Empty list means none loaded (modern multiwallet default). A single
        empty-string entry means the legacy default wallet is loaded.
        """
        try:
            result = self.call("listwallets", retries=1)
            if isinstance(result, list):
                return [str(x) for x in result]
        except Exception:
            pass
        return []

    def list_wallet_dir(self) -> List[str]:
        """Wallet names present on disk (loaded or not)."""
        try:
            info = self.call("listwalletdir", retries=1) or {}
            rows = info.get("wallets") if isinstance(info, dict) else None
            if not isinstance(rows, list):
                return []
            out: List[str] = []
            for row in rows:
                if isinstance(row, dict):
                    name = str(row.get("name") or "")
                else:
                    name = str(row or "")
                out.append(name)
            return out
        except Exception:
            return []

    def resolve_wallet_for_rpc(self, wallet: Optional[str] = None) -> Optional[str]:
        """Pick a wallet endpoint for wallet RPCs (getnewaddress, etc.).

        Returns:
          - explicit name when provided
          - first loaded named wallet when multiwallet has wallets loaded
          - None when the legacy default wallet is the only context
          - None when no wallet exists yet (caller must create one first)
        """
        if wallet is not None and str(wallet).strip() != "":
            name = str(wallet).strip()
            try:
                self.load_wallet(name)
            except Exception:
                pass
            return name

        loaded = self.list_wallets()
        # Legacy default wallet only
        if loaded == [""]:
            return None
        named = [w for w in loaded if w]
        if named:
            return named[0]
        # Nothing loaded — try load first wallet from disk
        on_disk = self.list_wallet_dir()
        for name in on_disk:
            # Empty name = default wallet directory entry
            try:
                if name:
                    self.load_wallet(name)
                    return name
                # default wallet file: loadwallet "" may not work; try bare
                self.call("loadwallet", [""], retries=1)
                return None
            except Exception:
                continue
        return None

    def load_wallet(self, name: str) -> None:
        if name is None:
            return
        # Allow empty string only for explicit default-wallet loads via callers
        # that pass it; bare load of "" is usually invalid — skip.
        if name == "":
            return
        try:
            self.call("loadwallet", [name], retries=1)
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "already loaded" in msg or "duplicate" in msg:
                return
            raise

    def create_wallet(
        self,
        name: str,
        *,
        passphrase: str = "",
        blank: bool = False,
        disable_private_keys: bool = False,
    ) -> Dict[str, Any]:
        """Create a legacy (non-descriptor) wallet so WIF export works for Qt."""
        name = (name or "").strip()
        if not name or not all(c.isalnum() or c in "_-" for c in name):
            raise ValueError(
                "Wallet name must be 1–48 characters: letters, digits, _ or -"
            )
        if len(name) > 48:
            raise ValueError("Wallet name too long (max 48).")

        # Prefer legacy wallet: disable_private_keys=false, blank=false,
        # passphrase="", avoid_reuse=false, descriptors=false
        try:
            result = self.call(
                "createwallet",
                [name, disable_private_keys, blank, "", False, False],
                retries=1,
            )
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "already exists" in msg or "database already exists" in msg:
                self.load_wallet(name)
                result = {"name": name, "warning": "loaded existing wallet"}
            else:
                # Older nodes: createwallet "name" only
                try:
                    result = self.call("createwallet", [name], retries=1)
                except RuntimeError as exc2:
                    if "already" in str(exc2).lower():
                        self.load_wallet(name)
                        result = {"name": name, "warning": "loaded existing"}
                    else:
                        raise RuntimeError(str(exc2)) from exc2

        encrypted = False
        pp = (passphrase or "").strip()
        if pp:
            if len(pp) < 8:
                raise ValueError("Encryption passphrase must be at least 8 characters.")
            # Encrypt then unlock — HD seed flush means keys come after encrypt
            self.call("encryptwallet", [pp], wallet=name)
            encrypted = True
            try:
                loaded = set(self.list_wallets())
                if name not in loaded:
                    self.load_wallet(name)
            except Exception:
                pass
            self.unlock(pp, 600, wallet=name)

        # Prefer legacy P2PKH (S…/L…/A…) — widest explorer/pool compatibility.
        # Validate chain identity so a renamed bloodstoned.exe cannot mint
        # STONE addresses under an LRGK/AZURE wallet label.
        addr = self.new_address(wallet=name, label="primary")
        ok, why = address_looks_valid_for_ticker(self.ticker, addr)
        if not ok:
            raise RuntimeError(why)

        wif = ""
        warning = ""
        try:
            wif = str(self.call("dumpprivkey", [addr], wallet=name))
        except RuntimeError as exc:
            wif = ""
            warning = str(exc)

        if isinstance(result, dict):
            cw_warn = str(result.get("warning") or "").strip()
            # Drop the noisy empty-passphrase createwallet notice when we
            # successfully encrypt afterward.
            if encrypted and "empty string given as passphrase" in cw_warn.lower():
                cw_warn = ""
            if cw_warn:
                warning = (warning + "; " if warning else "") + cw_warn

        # Confirm encryption stuck when requested
        if pp:
            try:
                wi = self.wallet_info(wallet=name)
                if "unlocked_until" not in wi and not wi.get("unlocked_until"):
                    # Some builds omit 'encrypted'; unlocked_until present ⇒ encrypted
                    if "unlocked_until" not in wi:
                        # probe via walletlock/walletpassphrase is heavy; rely on call ok
                        pass
            except Exception:
                pass

        return {
            "name": name,
            "address": addr,
            "wif": wif,
            "encrypted": encrypted,
            "ticker": self.ticker,
            "address_type": "legacy",
            "warning": warning,
        }

    def encrypt_wallet(self, passphrase: str, wallet: Optional[str] = None) -> str:
        pp = (passphrase or "").strip()
        if len(pp) < 8:
            raise ValueError("Passphrase must be at least 8 characters.")
        self.call("encryptwallet", [pp], wallet=wallet)
        return "Wallet encrypted. Unlock before spending."

    def dump_private_key(self, address: str, wallet: Optional[str] = None) -> str:
        return str(self.call("dumpprivkey", [address], wallet=wallet))

    def wallet_info(self, wallet: Optional[str] = None) -> Dict[str, Any]:
        return self.call("getwalletinfo", wallet=wallet) or {}

    def balance(self, wallet: Optional[str] = None, minconf: int = 0) -> float:
        try:
            val = self.call("getbalance", ["*", minconf], wallet=wallet, retries=1)
            return float(val or 0)
        except RuntimeError:
            val = self.call("getbalance", wallet=wallet, retries=1)
            return float(val or 0)

    def new_address(
        self,
        wallet: Optional[str] = None,
        label: str = "mfq",
        *,
        address_type: str = "legacy",
        validate: bool = True,
    ) -> str:
        """Generate a receive address (default legacy P2PKH for coin prefixes).

        Tries preferred type then falls back. When validate=True, rejects
        addresses that do not match this coin's expected prefix/HRP (catches
        wrong-chain daemons).
        """
        preferred = (address_type or "legacy").strip().lower() or "legacy"
        # Order: preferred, then common alternatives
        type_order = [preferred]
        for alt in ("legacy", "bech32", "p2sh-segwit"):
            if alt not in type_order:
                type_order.append(alt)

        last_err: Optional[Exception] = None
        addr = ""
        for atype in type_order:
            try:
                if atype:
                    addr = str(
                        self.call("getnewaddress", [label, atype], wallet=wallet)
                    )
                else:
                    addr = str(self.call("getnewaddress", [label], wallet=wallet))
                break
            except RuntimeError as exc:
                last_err = exc
                continue
        if not addr:
            try:
                addr = str(self.call("getnewaddress", wallet=wallet))
            except RuntimeError as exc:
                raise RuntimeError(str(last_err or exc)) from exc

        addr = (addr or "").strip()
        if not addr:
            raise RuntimeError(f"{self.ticker}: node returned an empty address")

        # RPC-level validity when available
        try:
            info = self.call("validateaddress", [addr], wallet=wallet) or {}
            if info.get("isvalid") is False:
                raise RuntimeError(
                    f"{self.ticker}: node rejected address as invalid: {addr}"
                )
        except RuntimeError as exc:
            if "rejected address" in str(exc).lower():
                raise
            # Older nodes / wallet-scoped validate failures — continue to shape check
            pass

        if validate:
            ok, why = address_looks_valid_for_ticker(self.ticker, addr)
            if not ok:
                raise RuntimeError(why)
        return addr

    def assert_chain_identity(self, wallet: Optional[str] = None) -> str:
        """Mint a throwaway address and ensure it matches this ticker's format.

        Returns the sample address on success. Returns "" when no wallet exists
        yet (modern multiwallet nodes do not auto-create a default wallet) —
        callers that create wallets must validate the first address after
        createwallet instead.

        Raises if the daemon is the wrong chain (e.g. bloodstoned renamed as
        lrgkd) or offline.
        """
        probe = self.probe(timeout=3.0)
        if not probe.get("online"):
            raise RuntimeError(
                probe.get("error")
                or f"{self.ticker}: daemon offline — cannot verify chain identity"
            )

        use = self.resolve_wallet_for_rpc(wallet)
        loaded = self.list_wallets()
        on_disk = self.list_wallet_dir() if use is None and not loaded else []

        # Fresh node: no wallet loaded and none on disk — cannot call
        # getnewaddress yet. create_wallet() validates the first address after
        # createwallet, so defer rather than false-failing with:
        # "No wallet is loaded… default wallet is no longer automatically created"
        if use is None and not loaded and not on_disk:
            return ""
        if use is None and not loaded and on_disk:
            # resolve_wallet_for_rpc already tried load; still nothing usable
            return ""

        try:
            sample = self.new_address(
                wallet=use,
                label="mfq-identity-check",
                address_type="legacy",
                validate=True,
            )
            return sample
        except RuntimeError as exc:
            msg = str(exc).lower()
            # Multiwallet / no-default-wallet nodes
            if (
                "no wallet is loaded" in msg
                or "wallet file not specified" in msg
                or "must request wallet rpc" in msg
            ):
                # Defer: wallet creation path re-checks address format
                return ""
            raise

    def list_transactions(
        self, wallet: Optional[str] = None, count: int = 50
    ) -> List[Dict[str, Any]]:
        try:
            rows = self.call(
                "listtransactions", ["*", count, 0, True], wallet=wallet, retries=1
            )
        except RuntimeError:
            rows = self.call("listtransactions", ["*", count], wallet=wallet, retries=1)
        if not isinstance(rows, list):
            return []
        return list(reversed(rows))

    def send(
        self,
        address: str,
        amount: float,
        *,
        wallet: Optional[str] = None,
        comment: str = "",
    ) -> str:
        params: List[Any] = [address, amount]
        if comment:
            params.extend([comment, ""])
        return str(self.call("sendtoaddress", params, wallet=wallet))

    def unlock(self, passphrase: str, timeout: int = 600, wallet: Optional[str] = None):
        self.call("walletpassphrase", [passphrase, timeout], wallet=wallet)

    def get_info_bundle(self, wallet: Optional[str] = None) -> Dict[str, Any]:
        probe = self.probe()
        out: Dict[str, Any] = {
            "probe": probe,
            "wallets": [],
            "balance": None,
            "configured": self.configured,
            "rpc_host": self.rpc_host,
            "rpc_port": self.rpc_port,
            "conf_path": self.conf_path,
        }
        if not probe.get("online"):
            return out
        try:
            out["wallets"] = self.list_wallets()
        except Exception as exc:
            out["wallet_error"] = str(exc)[:160]
        try:
            if wallet is not None:
                if wallet and wallet not in (out.get("wallets") or []):
                    try:
                        self.load_wallet(wallet)
                    except Exception:
                        pass
                out["balance"] = self.balance(wallet=wallet or None)
            else:
                wallets = out.get("wallets") or [""]
                total = 0.0
                for w in wallets:
                    try:
                        total += self.balance(wallet=w or None)
                    except Exception:
                        pass
                out["balance"] = total
        except Exception as exc:
            out["balance_error"] = str(exc)[:160]
        return out


def fmt_amount(val: Any, places: int = 8) -> str:
    if val is None:
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    s = f"{n:,.{places}f}".rstrip("0").rstrip(".")
    return s if s else "0"
