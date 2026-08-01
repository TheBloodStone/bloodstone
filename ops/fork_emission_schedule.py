#!/usr/bin/env python3
"""STONE / LRGK / AZURE emission, halving, and tail schedules (live consensus).

Source of truth: GetBlockSubsidy + MainNetConsensus in each coin's core tree,
cross-checked against live RPC (height, subsidy, gettxoutsetinfo).

Live path (family shares the SpaceXpanse/Bloodstone subsidy skeleton):
  • Heights < POST_ICO (9910): fixed **1 coin / block**
  • Heights ≥ 9910: classic eras 0–4 = initialSubsidy >> halvings,
    then inflation tail (scaled) for halvings > 4
  • Halving interval: 1_054_080 (STONE, LRGK) / 9_000 (AZURE)

STONE mainnet: initialSubsidy=100, nSubsidyHalvingInterval=1_054_080, POST_ICO=9910
AZURE: initialSubsidy=100, nSubsidyHalvingInterval=9000, premine=5_000_000
LRGK: initialSubsidy=500, nSubsidyHalvingInterval=1_054_080, premine≈200M live

nBlocksPerYear / qseBaseSubsidy exist in chainparams for a STONE-style stepped
QSE tail, but GetBlockSubsidy still uses classic halving + inflation on these
binaries today.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstone.rocks"
).rstrip("/")

# Display order: parent first, then live forks
DASHBOARD_TICKERS = ("STONE", "LRGK", "AZURE")

# Consensus constants (mainnet) — from chainparams.cpp + consensus/params.h
COINS: Dict[str, Dict[str, Any]] = {
    "STONE": {
        "name": "Bloodstone",
        "ticker": "STONE",
        "is_parent": True,
        "post_ico_height": 9910,
        "initial_subsidy": 100.0,
        "halving_interval": 1_054_080,
        "premine_design": 0.0,  # relaunch — no large design premine in registry
        "legacy_initial_for_scale": 800.0,
        "block_time_pre_post_ico_sec": 60,
        "block_time_post_ico_sec": 90,  # design target; tip often slower
        "pow_algorithms": ["neoscrypt", "yespower", "sha256d"],
        "p2p_port": 17333,
        "cli": os.environ.get("STONE_CLI", "bloodstone-cli"),
        "cli_args": [],
        "address_rules": {"legacy": "S…", "bech32": "stone1…"},
        "icon_url": f"{PUBLIC_ROOT}/branding/installer-icon.png",
        "wallet_url": f"{PUBLIC_ROOT}/wallet/",
        "n_blocks_per_year_param": 394470,
        "qse_base_param": 200.0,
        "note_schedule": (
            "Until height 9910 (POST_ICO), every block pays 1 STONE. "
            "From 9910, era-0 reward is 100 STONE, then halves each 1,054,080 blocks "
            "for eras 0–4; inflation tail after era 4 (scaled from legacy 800 curve)."
        ),
    },
    "LRGK": {
        "name": "Lil Raghnok Coin",
        "ticker": "LRGK",
        "is_parent": False,
        "post_ico_height": 9910,
        "initial_subsidy": 500.0,
        "halving_interval": 1_054_080,
        "premine_design": 10_000_000.0,  # fork-lab registry (design intent)
        "legacy_initial_for_scale": 800.0,  # inflation-era scale base
        "block_time_pre_post_ico_sec": 60,  # GetTargetSpacing pre-POST_ICO
        "block_time_post_ico_sec": 90,  # ~270s/algo × 3 algos average
        "pow_algorithms": ["neoscrypt", "yespower", "sha256d"],
        "p2p_port": 33685,
        "cli": os.environ.get("LRGK_CLI", "/root/lrgk-chain/bin/lrgk-cli"),
        "cli_args": [
            f"-datadir={os.environ.get('LRGK_DATADIR', '/root/lrgk-chain/bootstrap-source')}",
            f"-conf={os.environ.get('LRGK_CONF', '/root/lrgk-chain/bootstrap-source/lrgk.conf')}",
        ],
        "address_rules": {"legacy": "L…", "bech32": "lrgk1…"},
        "icon_url": f"{PUBLIC_ROOT}/downloads/fork-lab/icons/e9d304f3379e96859acd131f.png",
        "wallet_url": f"{PUBLIC_ROOT}/fork-lab/wallets/c/lrgk/",
        "n_blocks_per_year_param": 394470,
        "qse_base_param": 200.0,
        "note_schedule": (
            "Until height 9910 (POST_ICO), every block pays 1 LRGK. "
            "From 9910, era-0 reward is 500 LRGK, then halves each 1,054,080 blocks "
            "for eras 0–4; after that an inflation tail applies (scaled from the "
            "legacy 800-coin curve)."
        ),
    },
    "AZURE": {
        "name": "Azure Guardian Coin",
        "ticker": "AZURE",
        "is_parent": False,
        "post_ico_height": 9910,
        "initial_subsidy": 100.0,
        "halving_interval": 9000,  # chainparams mainnet
        "premine_design": 5_000_000.0,
        "legacy_initial_for_scale": 800.0,
        "block_time_pre_post_ico_sec": 60,
        "block_time_post_ico_sec": 90,
        "pow_algorithms": ["neoscrypt", "yespower", "sha256d"],
        "p2p_port": 29825,
        "cli": os.environ.get("AZURE_CLI", "/root/azure-chain/bin/azure-cli"),
        "cli_args": [
            f"-datadir={os.environ.get('AZURE_DATADIR', '/root/azure-chain/bootstrap-source')}",
            f"-conf={os.environ.get('AZURE_CONF', '/root/azure-chain/bootstrap-source/azure.conf')}",
        ],
        "address_rules": {"legacy": "A…", "bech32": "azure1…"},
        "icon_url": f"{PUBLIC_ROOT}/downloads/fork-lab/icons/7e177be306a616364771bf4c.png",
        "wallet_url": f"{PUBLIC_ROOT}/fork-lab/wallets/c/azure/",
        "n_blocks_per_year_param": 394470,
        "qse_base_param": 200.0,
        "note_schedule": (
            "Until height 9910 (POST_ICO), every block pays 1 AZURE. "
            "From 9910, era-0 reward is 100 AZURE, then halves each 9,000 blocks "
            "for eras 0–4 (fast clock vs LRGK/STONE); inflation tail after era 4."
        ),
    },
}


def _cli_json(cfg: Dict[str, Any], args: List[str]) -> Any:
    cmd = [cfg["cli"], *cfg["cli_args"], *args]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=20, text=True)
        out = out.strip()
        if not out:
            return None
        if out[0] in "{[":
            return json.loads(out)
        try:
            return int(out)
        except ValueError:
            try:
                return float(out)
            except ValueError:
                return out
    except Exception:
        return None


def subsidy_at_height(ticker: str, height: int) -> float:
    """Replica of GetBlockSubsidy for mainnet LRGK/AZURE."""
    cfg = COINS[ticker.upper()]
    h = max(0, int(height))
    post = int(cfg["post_ico_height"])
    if h < post:
        return 1.0
    interval = max(1, int(cfg["halving_interval"]))
    halvings = h // interval
    if halvings >= 64:
        return 0.0
    base = float(cfg["initial_subsidy"])
    legacy = float(cfg["legacy_initial_for_scale"])
    if halvings > 4:
        # C++: round(1833823998 * (1.02956^(h-3) - 1.02956^(h-4)))
        import math

        inflate = round(
            1833823998
            * (math.pow(1.02956, halvings - 3) - math.pow(1.02956, halvings - 4))
        )
        # ((int)round((inflateCoins / 1054080.0) * 100)) * (COIN/100) → coin units
        n = round((inflate / 1054080.0) * 100) / 100.0
        if base > 0 and base != legacy:
            n = n * base / legacy
        return float(n)
    # eras 0–4: right-shift
    return float(base / (2**halvings))


def era_table(ticker: str) -> List[Dict[str, Any]]:
    """Human eras: pre-POST_ICO + halving eras 0–8 (enough for dashboard)."""
    cfg = COINS[ticker.upper()]
    post = int(cfg["post_ico_height"])
    interval = int(cfg["halving_interval"])
    rows: List[Dict[str, Any]] = []
    # Phase A
    rows.append(
        {
            "phase": "pre_post_ico",
            "label": f"Bootstrap (height 0–{post - 1})",
            "height_start": 0,
            "height_end": post - 1,
            "blocks": post,
            "reward": 1.0,
            "halvings": None,
            "kind": "fixed_one",
            "approx_block_time_sec": cfg["block_time_pre_post_ico_sec"],
            "emission_in_phase": float(post) * 1.0,
        }
    )
    # Halving eras 0..12
    for halvings in range(0, 13):
        h0 = post + halvings * interval
        h1 = post + (halvings + 1) * interval - 1
        reward = subsidy_at_height(ticker, h0)
        blocks = interval
        kind = "halving" if halvings <= 4 else "inflation_tail"
        label = (
            f"Era {halvings} (½^{halvings})"
            if halvings <= 4
            else f"Inflation tail era {halvings}"
        )
        if halvings == 0:
            label = f"Era 0 — full reward ({reward:g})"
        rows.append(
            {
                "phase": kind,
                "label": label,
                "height_start": h0,
                "height_end": h1,
                "blocks": blocks,
                "reward": reward,
                "halvings": halvings,
                "kind": kind,
                "approx_block_time_sec": cfg["block_time_post_ico_sec"],
                "emission_in_phase": float(blocks) * float(reward),
            }
        )
    return rows


def cumulative_emission(
    ticker: str, through_height: int, *, premine: float
) -> float:
    """Sum subsidies from height 1..through_height plus premine (height 0 special)."""
    h = max(0, int(through_height))
    total = float(premine)
    # height 0 is premine; mining subsidies from 1..h
    # For speed: closed form where possible
    cfg = COINS[ticker.upper()]
    post = int(cfg["post_ico_height"])
    interval = int(cfg["halving_interval"])
    if h <= 0:
        return total
    # pre-post: heights 1..min(h, post-1) pay 1 each
    pre_end = min(h, post - 1)
    if pre_end >= 1:
        total += float(pre_end)  # heights 1..pre_end
    if h < post:
        return total
    # post-ico heights post..h
    # group by era
    start = post
    while start <= h:
        halvings = start // interval  # careful: halvings uses absolute height!
        # Actually in C++: halvings = nHeight / interval using absolute height
        # At height 9910, halvings = 9910/1054080 = 0 for LRGK
        # At height 9000 for AZURE, halvings = 1 already before POST_ICO for those heights
        # Wait - for height 9910 with AZURE interval 9000: 9910//9000 = 1
        # So AZURE starts POST_ICO already in era 1 (250? no 100>>1 = 50)
        reward = subsidy_at_height(ticker, start)
        # find end of this halvings bucket: next height where height//interval changes
        next_boundary = (halvings + 1) * interval
        end = min(h, next_boundary - 1)
        # but also need continuous run of same reward
        # reward only changes at boundaries of interval OR when crossing post_ico
        n = end - start + 1
        total += n * reward
        start = end + 1
    return total


def live_snapshot(ticker: str) -> Dict[str, Any]:
    cfg = COINS[ticker.upper()]
    height = _cli_json(cfg, ["getblockcount"])
    try:
        height = int(height or 0)
    except Exception:
        height = 0
    tip_sub = None
    if height > 0:
        stats = _cli_json(cfg, ["getblockstats", str(height), '["subsidy"]'])
        if isinstance(stats, dict) and stats.get("subsidy") is not None:
            tip_sub = float(stats["subsidy"]) / 1e8
    utxo = _cli_json(cfg, ["gettxoutsetinfo"])
    supply = None
    if isinstance(utxo, dict):
        amt = utxo.get("amount") or {}
        if isinstance(amt, dict):
            supply = float(amt.get("total") or amt.get("coins") or 0)
        elif isinstance(amt, (int, float)):
            supply = float(amt)
    # Infer premine from supply − (height * 1) if still in 1-coin era
    premine_live = None
    if supply is not None and height > 0 and tip_sub == 1.0:
        premine_live = supply - float(height)  # heights 1..height paid 1; genesis premine
        # actually genesis is height 0 included in supply; mining blocks = height
        # supply ≈ premine + height * 1 (if all 1-coin and no fees burned)
        premine_live = supply - float(height)
    premine = premine_live if premine_live and premine_live > 0 else float(
        cfg["premine_design"]
    )
    # If live supply implies ~200M for LRGK, use it
    if ticker.upper() == "LRGK" and premine_live and premine_live > 1e6:
        premine = premine_live

    reward_now = subsidy_at_height(ticker, height)
    reward_next = subsidy_at_height(ticker, height + 1)
    post = int(cfg["post_ico_height"])
    blocks_to_post = max(0, post - height)
    sec = (
        cfg["block_time_pre_post_ico_sec"]
        if height < post
        else cfg["block_time_post_ico_sec"]
    )
    eta_post = None
    if blocks_to_post > 0:
        eta_post = (
            datetime.now(timezone.utc) + timedelta(seconds=blocks_to_post * sec)
        ).strftime("%Y-%m-%d %H:%M UTC")

    eras = era_table(ticker)
    # Next reward change height
    next_change = None
    next_reward = None
    if height < post:
        next_change = post
        next_reward = subsidy_at_height(ticker, post)
    else:
        interval = int(cfg["halving_interval"])
        halvings = height // interval
        next_change = (halvings + 1) * interval
        next_reward = subsidy_at_height(ticker, next_change)

    # Projection milestones
    milestones = []
    for h in sorted(
        set(
            [
                height,
                post,
                post + cfg["halving_interval"],
                post + 2 * cfg["halving_interval"],
                post + 4 * cfg["halving_interval"],
                post + 5 * cfg["halving_interval"],
            ]
        )
    ):
        if h < 0:
            continue
        milestones.append(
            {
                "height": int(h),
                "reward": subsidy_at_height(ticker, int(h)),
                "approx_cum_mined_plus_premine": cumulative_emission(
                    ticker, int(h), premine=premine
                ),
                "is_tip": int(h) == height,
            }
        )

    return {
        "ticker": ticker.upper(),
        "name": cfg["name"],
        "ok": height > 0,
        "live": {
            "height": height,
            "tip_subsidy_coins": tip_sub if tip_sub is not None else reward_now,
            "computed_subsidy_coins": reward_now,
            "circulating_approx": supply,
            "premine_inferred": premine,
            "premine_design_registry": cfg["premine_design"],
            "in_pre_post_ico": height < post,
            "blocks_to_post_ico": blocks_to_post,
            "eta_post_ico_utc": eta_post,
            "next_reward_change_height": next_change,
            "next_reward_coins": next_reward,
            "approx_block_time_sec": sec,
            "daily_emission_approx": reward_now * (86400.0 / max(1, sec)),
            "yearly_emission_approx": reward_now
            * (365.25 * 86400.0 / max(1, sec)),
        },
        "consensus": {
            "post_ico_height": post,
            "initial_subsidy": cfg["initial_subsidy"],
            "halving_interval_blocks": cfg["halving_interval"],
            "pre_post_ico_reward": 1.0,
            "block_time_pre_sec": cfg["block_time_pre_post_ico_sec"],
            "block_time_post_sec": cfg["block_time_post_ico_sec"],
            "pow_algorithms": cfg["pow_algorithms"],
            "p2p_port": cfg["p2p_port"],
            "address_rules": cfg["address_rules"],
            "n_blocks_per_year_param": cfg["n_blocks_per_year_param"],
            "qse_base_param": cfg["qse_base_param"],
            "qse_active_in_binary": False,
            "qse_note": (
                "chainparams define nBlocksPerYear + qseBaseSubsidy=200 for a "
                "STONE-style stepped QSE tail, but GetBlockSubsidy still uses the "
                "classic halving + inflation path. Dashboard reflects the live binary."
            ),
        },
        "eras": eras,
        "milestones": milestones,
        "tail": {
            "kind": "inflation_after_era_4",
            "description": (
                "After 5 full halving steps (halvings > 4), subsidy follows a "
                "~2.956%/era inflation curve scaled by initialSubsidy/800, "
                "not zero and not the STONE QSE 200-coin flat tail (unless binary is upgraded)."
            ),
            "example_era_5_reward": subsidy_at_height(
                ticker, post + 5 * int(cfg["halving_interval"])
            ),
            "example_era_10_reward": subsidy_at_height(
                ticker, post + 10 * int(cfg["halving_interval"])
            ),
        },
        "split": {
            "miners_bps": 9000,
            "mesh_providers_bps": 1000,
            "lab_reserve_bps": 0,
            "note": (
                "Fork Lab economy formula: 90% miners / 10% mesh providers in the "
                "fork ticker (policy). On-chain coinbase today is still full subsidy "
                "to the miner/pool unless dual-submit/merge wiring applies elsewhere."
            ),
        },
        "links": {
            "wallet": cfg["wallet_url"],
            "icon": cfg["icon_url"],
            "seed_registry": f"{PUBLIC_ROOT}/api/ecosystem/seed-registry",
            "exchange_listing": f"{PUBLIC_ROOT}/api/fork-lab/exchange/{ticker.upper()}",
        },
        "note": cfg["note_schedule"],
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _sec_per_year(block_time_sec: float) -> float:
    return 365.25 * 86400.0 / max(1.0, float(block_time_sec))


def comparison_matrix(coins: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Side-by-side halving / yearly mint for coin owners, vs STONE parent."""
    stone = coins.get("STONE") or {}
    stone_live = stone.get("live") or {}
    stone_cons = stone.get("consensus") or {}
    stone_yearly = float(stone_live.get("yearly_emission_approx") or 0)
    stone_daily = float(stone_live.get("daily_emission_approx") or 0)
    stone_reward = float(
        stone_live.get("tip_subsidy_coins")
        or stone_live.get("computed_subsidy_coins")
        or 0
    )
    stone_interval = int(stone_cons.get("halving_interval_blocks") or 1_054_080)
    stone_initial = float(stone_cons.get("initial_subsidy") or 100)
    stone_bt = float(stone_live.get("approx_block_time_sec") or 90)

    rows: List[Dict[str, Any]] = []
    for t in DASHBOARD_TICKERS:
        c = coins.get(t) or {}
        if not c:
            continue
        live = c.get("live") or {}
        cons = c.get("consensus") or {}
        yearly = float(live.get("yearly_emission_approx") or 0)
        daily = float(live.get("daily_emission_approx") or 0)
        reward = float(
            live.get("tip_subsidy_coins") or live.get("computed_subsidy_coins") or 0
        )
        interval = int(cons.get("halving_interval_blocks") or 0)
        initial = float(cons.get("initial_subsidy") or 0)
        bt = float(live.get("approx_block_time_sec") or cons.get("block_time_post_sec") or 90)
        # Years per halving era (design block time)
        years_per_halving = (
            (interval * bt) / (365.25 * 86400.0) if interval > 0 else None
        )
        # Era-0 yearly mint (if already post-ICO at full initial)
        era0_yearly = initial * _sec_per_year(
            float(cons.get("block_time_post_sec") or 90)
        )
        vs = {}
        if t != "STONE" and stone_yearly > 0:
            vs = {
                "yearly_emission_vs_stone": round(yearly / stone_yearly, 4)
                if yearly
                else None,
                "daily_emission_vs_stone": round(daily / stone_daily, 4)
                if daily and stone_daily
                else None,
                "tip_reward_vs_stone": round(reward / stone_reward, 4)
                if reward and stone_reward
                else None,
                "initial_subsidy_vs_stone": round(initial / stone_initial, 4)
                if stone_initial
                else None,
                "halving_interval_vs_stone": round(interval / stone_interval, 4)
                if stone_interval
                else None,
                "era0_yearly_vs_stone_era0": round(
                    era0_yearly
                    / (stone_initial * _sec_per_year(stone_bt)),
                    4,
                )
                if stone_initial
                else None,
            }
        elif t == "STONE":
            vs = {
                "yearly_emission_vs_stone": 1.0,
                "daily_emission_vs_stone": 1.0,
                "tip_reward_vs_stone": 1.0,
                "initial_subsidy_vs_stone": 1.0,
                "halving_interval_vs_stone": 1.0,
                "era0_yearly_vs_stone_era0": 1.0,
            }

        # Compact halving schedule preview (eras 0–4 + first tail)
        schedule = []
        for e in (c.get("eras") or [])[:8]:
            r = float(e.get("reward") or 0)
            bts = float(e.get("approx_block_time_sec") or bt)
            y = r * _sec_per_year(bts)
            schedule.append(
                {
                    "label": e.get("label"),
                    "kind": e.get("kind"),
                    "height_start": e.get("height_start"),
                    "height_end": e.get("height_end"),
                    "reward_per_block": r,
                    "blocks_in_phase": e.get("blocks"),
                    "emission_in_phase": e.get("emission_in_phase"),
                    "coins_per_year_at_reward": round(y, 2),
                    "years_span_approx": round(
                        (int(e.get("blocks") or 0) * bts) / (365.25 * 86400.0), 3
                    )
                    if e.get("blocks")
                    else None,
                }
            )

        rows.append(
            {
                "ticker": t,
                "name": c.get("name") or t,
                "is_parent": bool((COINS.get(t) or {}).get("is_parent")),
                "ok": bool(c.get("ok")),
                "height": live.get("height"),
                "phase": (
                    "pre_POST_ICO_1_coin"
                    if live.get("in_pre_post_ico")
                    else "post_POST_ICO_schedule"
                ),
                "tip_reward_per_block": reward,
                "initial_subsidy_post_ico": initial,
                "halving_interval_blocks": interval,
                "years_per_halving_approx": round(years_per_halving, 3)
                if years_per_halving is not None
                else None,
                "approx_block_time_sec": bt,
                "blocks_per_year_approx": round(_sec_per_year(bt), 1),
                "daily_emission_approx": round(daily, 2),
                "yearly_emission_approx": round(yearly, 2),
                "era0_yearly_emission_approx": round(era0_yearly, 2),
                "premine_inferred": live.get("premine_inferred"),
                "circulating_approx": live.get("circulating_approx"),
                "next_reward_change_height": live.get("next_reward_change_height"),
                "next_reward_coins": live.get("next_reward_coins"),
                "vs_stone": vs,
                "halving_schedule": schedule,
                "icon": (c.get("links") or {}).get("icon"),
                "wallet": (c.get("links") or {}).get("wallet"),
            }
        )

    # Narrative helpers for owners
    notes = [
        "STONE is the parent chain. Ratios use live tip emission (coins/year at current block reward × design block time).",
        "AZURE halves every 9,000 blocks (~every few days at 90s) so it burns through eras much faster than STONE/LRGK (1,054,080 blocks ≈ design multi-year steps).",
        "LRGK era-0 subsidy is 5× STONE (500 vs 100); same halving interval as STONE, so era-0 yearly mint is ~5× STONE if both are at full post-ICO reward.",
        "Bootstrap (height < 9,910): all three pay 1 coin/block — yearly mint is then driven mainly by block rate, not initial subsidy.",
        "After five halving steps, all three enter an inflation tail (not zero) for long-run security budget.",
    ]

    return {
        "schema": "bloodstone/fork-emission-compare/v1",
        "baseline": "STONE",
        "tickers": list(DASHBOARD_TICKERS),
        "rows": rows,
        "notes": notes,
        "fields": {
            "yearly_emission_approx": "Coins minted per year at current tip reward and approx block time",
            "vs_stone": "Ratio of each metric to the STONE parent (1.0 = same as STONE)",
            "halving_schedule": "Bootstrap + eras 0–4 + first inflation-tail steps",
        },
    }


def full_dashboard() -> Dict[str, Any]:
    coins = {t: live_snapshot(t) for t in DASHBOARD_TICKERS}
    compare = comparison_matrix(coins)
    return {
        "schema": "bloodstone/fork-emission-dashboard/v2",
        "public_root": PUBLIC_ROOT,
        "page": f"{PUBLIC_ROOT}/fork-lab/emissions/",
        "owners_page": f"{PUBLIC_ROOT}/fork-lab/owners/",
        "api": f"{PUBLIC_ROOT}/api/fork-lab/emissions",
        "compare_api": f"{PUBLIC_ROOT}/api/fork-lab/emissions/compare",
        "coins": coins,
        "compare": {
            "post_ico_height": 9910,
            "baseline": "STONE",
            "current_phase": {
                t: (
                    "pre_POST_ICO_1_coin"
                    if coins[t]["live"]["in_pre_post_ico"]
                    else "post_POST_ICO_schedule"
                )
                for t in coins
            },
            "matrix": compare,
        },
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.ticker:
        data = live_snapshot(args.ticker)
    else:
        data = full_dashboard()
    print(json.dumps(data, indent=2))
    if args.publish:
        out = os.environ.get(
            "BLOODSTONE_DOWNLOADS_DIR", "/var/www/bloodstone/downloads"
        )
        path = os.path.join(out, "fork-lab-emissions.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data if not args.ticker else full_dashboard(), fh, indent=2)
            fh.write("\n")
        print("published", path, file=__import__("sys").stderr)
