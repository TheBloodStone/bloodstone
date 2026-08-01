// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2018 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_POW_H
#define BITCOIN_POW_H

#include <consensus/params.h>

#include <stdint.h>

class CBlockHeader;
class CBlockIndex;
class uint256;

enum class PowAlgo : uint8_t;

/**
 * Number of same-algo blocks in the Dark Gravity Wave retarget window.
 * Single source for window length (reject + GetNextWorkRequired).
 */
static constexpr int64_t DGW_PAST_BLOCKS = 24;

/**
 * Locked multi-algo (per-algo spacing S = 270) minimum window endpoint span:
 *   TIMEWARP_MIN_WINDOW_SECONDS = 24 * 270 / 3 = 2160
 *
 * Both the header-reject rule and the DGW nActualTimespan clamp floor MUST use
 * DgwMinTimespan(nTargetTimespan) — never a second independent literal — so the
 * two cannot desync. For multi-algo mainnet, DgwMinTimespan(24*270) equals this
 * constant (enforced by static_assert and unit tests).
 *
 * TODO(H1-followup): evaluate MAX window ceiling (e.g. 3*T = 19440) separately
 * post-testnet. Not shipped in first H1 — honest hashrate drops can produce long
 * spans (flash-crash recovery); that is a distinct problem from timewarp.
 */
static constexpr int64_t TIMEWARP_MIN_WINDOW_SECONDS = 2160;

static_assert(DGW_PAST_BLOCKS * 270 / 3 == TIMEWARP_MIN_WINDOW_SECONDS,
              "TIMEWARP_MIN_WINDOW_SECONDS must equal multi-algo DGW T/3");

/**
 * Shared DGW min timespan / timewarp reject floor for a given target timespan.
 * Used by GetNextWorkRequired (clamp) and CheckDgwTimewarpWindow (reject).
 */
inline int64_t DgwMinTimespan(int64_t nTargetTimespan)
{
    return nTargetTimespan / 3;
}

/** Result of CollectDgwSameAlgoWindow (newest → oldest, up to DGW_PAST_BLOCKS). */
struct DgwSameAlgoWindow {
    /** Window slots newest-first; valid for indices [0, nCount). */
    const CBlockIndex* pindex[DGW_PAST_BLOCKS] = {};
    int nCount = 0;

    bool full() const { return nCount == DGW_PAST_BLOCKS; }
    const CBlockIndex* newest() const { return nCount > 0 ? pindex[0] : nullptr; }
    const CBlockIndex* oldest() const { return nCount > 0 ? pindex[nCount - 1] : nullptr; }
};

/** Endpoint span newest.nTime − oldest.nTime; 0 if empty. Defined in pow.cpp. */
int64_t DgwWindowTimespan(const DgwSameAlgoWindow& window);

/**
 * Single source of truth for the DGW same-algo window walk.
 *
 * Starts at pindexStart, jumps to the last ancestor with `algo` (including
 * pindexStart if it matches), then walks back with GetLastAncestorWithAlgo
 * collecting up to DGW_PAST_BLOCKS headers. Identical walk for retarget and
 * timewarp reject (reject builds a synthetic tip for the new header first).
 *
 * @return false if pindexStart is null or no same-algo ancestor exists
 * @return true  with out.nCount in [1, DGW_PAST_BLOCKS] (may be incomplete)
 */
bool CollectDgwSameAlgoWindow(const CBlockIndex* pindexStart, PowAlgo algo,
                              DgwSameAlgoWindow& out);

/**
 * Header-reject timewarp check (Phase H1).
 *
 * Treats a new block of `algo` with timestamp nTimeNew as the window newest
 * (synthetic tip linked to pindexPrev) and runs CollectDgwSameAlgoWindow.
 *
 * Bootstrap / insufficient window (out.nCount < DGW_PAST_BLOCKS): the MIN
 * rule does not apply — returns true (defined skip, not a crash). DGW already
 * returns powLimit when the ancestor walk is shallow.
 *
 * Full window: require timespan >= DgwMinTimespan(DGW_PAST_BLOCKS * spacing).
 */
bool CheckDgwTimewarpWindow(const CBlockIndex* pindexPrev, PowAlgo algo,
                            int64_t nTimeNew, const Consensus::Params& params);

/**
 * Phase H1 height-gated header time rules (future bound + window-min).
 * Pure helper used by ContextualCheckBlockHeader and unit tests — keeps gate
 * logic decoupled from the frozen mainnet *H* value.
 *
 * - Future bound: always applied; limit is 7200 below H, 1800 at/after H.
 * - Window-min: only when IsH1TimewarpActive(nHeight) (nHeight >= H).
 */
enum class H1HeaderTimeResult {
    OK,
    TIME_TOO_NEW,       //!< time-too-new (beyond height-dependent future bound)
    TIMEWARP_WINDOW,    //!< timewarp-dgw-window (compressed same-algo window)
};

/**
 * @param activationHeight  Phase H1 activation height H (tests pass a placeholder;
 *                          validation passes consensus.nH1TimewarpActivationHeight).
 */
H1HeaderTimeResult CheckH1HeaderTimeRules(int nHeight, int64_t nBlockTime, int64_t nAdjustedTime,
                                          const CBlockIndex* pindexPrev, PowAlgo algo,
                                          const Consensus::Params& params, int activationHeight);

/** Uses params.nH1TimewarpActivationHeight. */
inline H1HeaderTimeResult CheckH1HeaderTimeRules(int nHeight, int64_t nBlockTime, int64_t nAdjustedTime,
                                                 const CBlockIndex* pindexPrev, PowAlgo algo,
                                                 const Consensus::Params& params)
{
    return CheckH1HeaderTimeRules(nHeight, nBlockTime, nAdjustedTime, pindexPrev, algo, params,
                                  params.nH1TimewarpActivationHeight);
}

unsigned int GetNextWorkRequired(PowAlgo algo, const CBlockIndex* pindexLast, const Consensus::Params&);

#endif // BITCOIN_POW_H
