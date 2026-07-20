// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2018 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <pow.h>

#include <arith_uint256.h>
#include <chain.h>
#include <powdata.h>
#include <uint256.h>

H1HeaderTimeResult
CheckH1HeaderTimeRules(const int nHeight, const int64_t nBlockTime, const int64_t nAdjustedTime,
                       const CBlockIndex* pindexPrev, const PowAlgo algo,
                       const Consensus::Params& params, const int activationHeight)
{
    if (nBlockTime > nAdjustedTime + MaxFutureBlockTimeForHeight(nHeight, activationHeight)) {
        return H1HeaderTimeResult::TIME_TOO_NEW;
    }
    if (IsH1TimewarpActive(nHeight, activationHeight) &&
        !CheckDgwTimewarpWindow(pindexPrev, algo, nBlockTime, params)) {
        return H1HeaderTimeResult::TIMEWARP_WINDOW;
    }
    return H1HeaderTimeResult::OK;
}

int64_t
DgwWindowTimespan(const DgwSameAlgoWindow& window)
{
    if (window.nCount < 1) {
        return 0;
    }
    return window.newest()->GetBlockTime() - window.oldest()->GetBlockTime();
}

bool
CollectDgwSameAlgoWindow(const CBlockIndex* pindexStart, const PowAlgo algo,
                         DgwSameAlgoWindow& out)
{
    out.nCount = 0;
    if (pindexStart == nullptr) {
        return false;
    }

    const CBlockIndex* pindex = pindexStart->GetLastAncestorWithAlgo(algo);
    if (pindex == nullptr) {
        return false;
    }

    while (pindex != nullptr && out.nCount < DGW_PAST_BLOCKS) {
        out.pindex[out.nCount++] = pindex;
        pindex = pindex->pprev;
        if (pindex != nullptr) {
            pindex = pindex->GetLastAncestorWithAlgo(algo);
        }
    }
    return true;
}

bool
CheckDgwTimewarpWindow(const CBlockIndex* pindexPrev, const PowAlgo algo,
                       const int64_t nTimeNew, const Consensus::Params& params)
{
    /* Synthetic tip representing the new header so reject and retarget share
       CollectDgwSameAlgoWindow exactly (same walk, same newest/oldest). */
    CBlockIndex indexNew;
    indexNew.pprev = const_cast<CBlockIndex*>(pindexPrev);
    indexNew.algo = algo;
    indexNew.nTime = static_cast<unsigned int>(nTimeNew);
    if (pindexPrev != nullptr) {
        indexNew.nHeight = pindexPrev->nHeight + 1;
    }

    DgwSameAlgoWindow window;
    if (!CollectDgwSameAlgoWindow(&indexNew, algo, window)) {
        /* No same-algo ancestor path (should not happen once indexNew.algo is set). */
        return true;
    }

    /* Bootstrap / shallow window: rule does not apply until 24 same-algo blocks
       exist including the new tip. GetNextWorkRequired returns powLimit in the
       same incomplete-window case. */
    if (!window.full()) {
        return true;
    }

    const int nextHeight = (pindexPrev != nullptr) ? pindexPrev->nHeight + 1 : 0;
    const int64_t nTargetTimespan
        = DGW_PAST_BLOCKS * params.rules->GetTargetSpacing(algo, nextHeight);
    const int64_t minTimespan = DgwMinTimespan(nTargetTimespan);

    return DgwWindowTimespan(window) >= minTimespan;
}

unsigned int
GetNextWorkRequired(const PowAlgo algo, const CBlockIndex* pindexLast,
                    const Consensus::Params& params)
{
    const arith_uint256 bnPowLimit
        = UintToArith256(powLimitForAlgo(algo, params));

    if (pindexLast == nullptr || params.fPowNoRetargeting) {
        return bnPowLimit.GetCompact();
    }

    /* DGW taken from Dash, same-algo only — window via CollectDgwSameAlgoWindow. */

    DgwSameAlgoWindow window;
    if (!CollectDgwSameAlgoWindow(pindexLast, algo, window) || !window.full()) {
        return bnPowLimit.GetCompact();
    }

    arith_uint256 bnResult;
    for (int i = 0; i < window.nCount; ++i) {
        const CBlockIndex* pindex = window.pindex[i];
        arith_uint256 bnTarget;
        bnTarget.SetCompact(pindex->nBits);

        /* Match historical DGW average indexing: nCountBlocks = i+1. */
        const size_t nCountBlocks = static_cast<size_t>(i + 1);
        if (nCountBlocks == 1) {
            bnResult = bnTarget;
        } else {
            bnResult = (bnResult * nCountBlocks + bnTarget) / (nCountBlocks + 1);
        }
    }

    int64_t nActualTimespan = DgwWindowTimespan(window);
    const int nextHeight = window.newest()->nHeight + 1;
    const int64_t nTargetTimespan
        = DGW_PAST_BLOCKS * params.rules->GetTargetSpacing(algo, nextHeight);

    /* Clamp floor: same DgwMinTimespan as CheckDgwTimewarpWindow reject MIN.
       Upper clamp remains 3*T (MAX window reject not shipped in H1). */
    const int64_t minTimespan = DgwMinTimespan(nTargetTimespan);
    if (nActualTimespan < minTimespan) {
        nActualTimespan = minTimespan;
    }
    if (nActualTimespan > nTargetTimespan * 3) {
        nActualTimespan = nTargetTimespan * 3;
    }

    bnResult *= nActualTimespan;
    bnResult /= nTargetTimespan;

    if (bnResult > bnPowLimit) {
        bnResult = bnPowLimit;
    }

    return bnResult.GetCompact();
}
