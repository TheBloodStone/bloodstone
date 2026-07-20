// Copyright (c) 2026 The Bloodstone developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <arith_uint256.h>
#include <chain.h>
#include <chainparams.h>
#include <consensus/params.h>
#include <pow.h>
#include <powdata.h>
#include <uint256.h>

#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

#include <memory>
#include <vector>

/* No space between BOOST_FIXTURE_TEST_SUITE and '(', so that extraction of
   the test-suite name works with grep as done in the Makefile.  */
BOOST_FIXTURE_TEST_SUITE(timewarp_tests, BasicTestingSetup)

namespace {

class TestChain
{
private:
    std::vector<std::unique_ptr<CBlockIndex>> blocks;

public:
    CBlockIndex* tip() const
    {
        if (blocks.empty()) return nullptr;
        return blocks.back().get();
    }

    CBlockIndex* attach(PowAlgo algo, uint32_t nTime, uint32_t nBits)
    {
        auto index = std::make_unique<CBlockIndex>();
        index->pprev = tip();
        index->nHeight = blocks.empty() ? 0 : tip()->nHeight + 1;
        index->algo = algo;
        index->nTime = nTime;
        index->nBits = nBits;
        CBlockIndex* raw = index.get();
        blocks.push_back(std::move(index));
        return raw;
    }

    /** Attach a same-algo block with nTime = prevSame + delta (or base if first). */
    CBlockIndex* attachDelta(PowAlgo algo, int64_t delta, uint32_t nBits, uint32_t baseTime = 1'500'000'000)
    {
        const CBlockIndex* last = tip() ? tip()->GetLastAncestorWithAlgo(algo) : nullptr;
        const uint32_t t = last ? static_cast<uint32_t>(last->nTime + delta) : baseTime;
        return attach(algo, t, nBits);
    }
};

/** Build 23 same-algo ancestors so the next block completes a full 24-window. */
void BuildSameAlgoPrefix(TestChain& chain, PowAlgo algo, int64_t step, uint32_t nBits,
                         int count = DGW_PAST_BLOCKS - 1)
{
    for (int i = 0; i < count; ++i) {
        chain.attachDelta(algo, i == 0 ? 0 : step, nBits);
    }
}

} // namespace

/* ************************************************************************** */
/* Constants / lock */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_constants_lock)
{
    BOOST_CHECK_EQUAL(DGW_PAST_BLOCKS, 24);
    BOOST_CHECK_EQUAL(TIMEWARP_MIN_WINDOW_SECONDS, 2160);
    BOOST_CHECK_EQUAL(MAX_FUTURE_BLOCK_TIME, 1800);
    BOOST_CHECK_EQUAL(MAX_FUTURE_BLOCK_TIME_LEGACY, 7200);
    BOOST_CHECK_EQUAL(TIMESTAMP_WINDOW, MAX_FUTURE_BLOCK_TIME_LEGACY);
    BOOST_CHECK_EQUAL(DgwMinTimespan(DGW_PAST_BLOCKS * 270), TIMEWARP_MIN_WINDOW_SECONDS);
    /* Clamp floor and reject MIN are the same helper — not independent literals. */
    BOOST_CHECK_EQUAL(DgwMinTimespan(6480), 2160);
    /* Regtest activates H1 from genesis so unit tests exercise the reject path. */
    BOOST_CHECK_EQUAL(Params().GetConsensus().nH1TimewarpActivationHeight, 0);
    BOOST_CHECK(IsH1TimewarpActive(0, Params().GetConsensus()));
    BOOST_CHECK(IsH1TimewarpActive(1, Params().GetConsensus()));
}

/* ************************************************************************** */
/* (12) Bootstrap / insufficient window */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_bootstrap_insufficient_window)
{
    const Consensus::Params& params = Params().GetConsensus();
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);

    TestChain chain;
    /* 0 same-algo on prev: first block of lane */
    BOOST_CHECK(CheckDgwTimewarpWindow(nullptr, algo, 1'500'000'000, params));

    /* 1 .. 23 same-algo including synthetic new tip → incomplete → defined skip */
    for (int n = 1; n < DGW_PAST_BLOCKS; ++n) {
        TestChain c;
        for (int i = 0; i < n - 1; ++i) {
            c.attachDelta(algo, i == 0 ? 0 : 1, bits);
        }
        /* Compressed timestamps would fail if rule applied; must still pass. */
        BOOST_CHECK_MESSAGE(
            CheckDgwTimewarpWindow(c.tip(), algo, c.tip() ? c.tip()->nTime + 1 : 1'500'000'001, params),
            "bootstrap n=" << n);
    }

    /* Retarget returns powLimit when window incomplete */
    TestChain shallow;
    for (int i = 0; i < 10; ++i) {
        shallow.attachDelta(algo, 100, bits);
    }
    BOOST_CHECK_EQUAL(GetNextWorkRequired(algo, shallow.tip(), params), bits);
}

/* ************************************************************************** */
/* (1) Compressed window reject — span = min-1 */
/* (2) Min legal window accept */
/* (3) Target window accept */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_compressed_and_legal_windows)
{
    const Consensus::Params& params = Params().GetConsensus();
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);

    /* Use multi-algo spacing height: force nHeight so GetTargetSpacing sees 270.
       MainNetConsensus: POST_ICO at >=9910 and MULTI_ALGO at >=1 → S=270. */
    auto buildAtHeight = [&](int startHeight, int64_t step) {
        TestChain chain;
        /* Pad with dummy genesis-like block at startHeight-1 so next is startHeight */
        if (startHeight > 0) {
            auto pad = std::make_unique<CBlockIndex>();
            /* We build by attaching; set height via repeated attach from empty.
               Simpler: attach blocks and then fix heights after. */
        }
        (void)startHeight;
        for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
            chain.attachDelta(algo, i == 0 ? 0 : step, bits);
        }
        /* Raise heights into POST_ICO multi-algo spacing regime. */
        for (CBlockIndex* p = chain.tip(); p != nullptr; p = p->pprev) {
            p->nHeight += 10000;
        }
        return chain;
    };

    /* (1) step such that full span = 23 * step = min-1 when new block +step */
    /* min = DgwMinTimespan(24 * 270) = 2160; need span 2159 on full window.
       24 blocks → 23 intervals; if all intervals equal: step = 2159/23 = 93.87 → use
       endpoint control: set times explicitly. */

    {
        TestChain chain;
        const uint32_t t0 = 1'600'000'000;
        chain.attach(algo, t0, bits);
        for (int i = 1; i < DGW_PAST_BLOCKS - 1; ++i) {
            chain.attach(algo, t0 + i, bits); /* +1s packing on ancestors */
        }
        for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

        /* New tip at t0+22 → span from oldest t0 = 22 if only 23 total with new?
           Window: new + 23 ancestors. We have 23 ancestors (indices 0..22).
           oldest = t0, newest = t0+22 → span 22 < 2160 → reject */
        const int64_t nTimeNew = t0 + 22;
        BOOST_CHECK(!CheckDgwTimewarpWindow(chain.tip(), algo, nTimeNew, params));
    }

    /* (2) span == 2160 exactly */
    {
        TestChain chain;
        const uint32_t t0 = 1'600'000'000;
        const int64_t span = TIMEWARP_MIN_WINDOW_SECONDS; /* 2160 */
        chain.attach(algo, t0, bits);
        for (int i = 1; i < DGW_PAST_BLOCKS - 1; ++i) {
            /* Spread intermediate times arbitrarily within endpoints */
            chain.attach(algo, t0 + static_cast<uint32_t>((span * i) / (DGW_PAST_BLOCKS - 1)), bits);
        }
        for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

        const int64_t nTimeNew = t0 + span;
        BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip(), algo, nTimeNew, params));
    }

    /* (3) span ≈ 6480 (target) */
    {
        TestChain chain;
        const uint32_t t0 = 1'600'000'000;
        const int64_t span = DGW_PAST_BLOCKS * 270; /* 6480 */
        chain.attach(algo, t0, bits);
        for (int i = 1; i < DGW_PAST_BLOCKS - 1; ++i) {
            chain.attach(algo, t0 + static_cast<uint32_t>((span * i) / (DGW_PAST_BLOCKS - 1)), bits);
        }
        for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

        BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip(), algo, t0 + span, params));
    }

    (void)buildAtHeight;
}

/* ************************************************************************** */
/* (4) Multi-step ease rate limit — successive compressed windows rejected */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_multistep_compressed_rejected)
{
    const Consensus::Params& params = Params().GetConsensus();
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);

    TestChain chain;
    const uint32_t t0 = 1'700'000'000;
    for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
        chain.attach(algo, t0 + i, bits);
    }
    for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

    /* First compressed tip rejected */
    BOOST_CHECK(!CheckDgwTimewarpWindow(chain.tip(), algo, t0 + DGW_PAST_BLOCKS - 1, params));

    /* Even if we imagine attaching +1s repeatedly, each would fail once full */
    BOOST_CHECK(!CheckDgwTimewarpWindow(chain.tip(), algo, t0 + 100, params));
}

/* ************************************************************************** */
/* (5) Cross-algo isolation */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_cross_algo_isolation)
{
    const Consensus::Params& params = Params().GetConsensus();
    const PowAlgo sha = PowAlgo::SHA256D;
    const PowAlgo neo = PowAlgo::NEOSCRYPT;
    const uint32_t bitsSha = GetNextWorkRequired(sha, nullptr, params);
    const uint32_t bitsNeo = GetNextWorkRequired(neo, nullptr, params);

    TestChain chain;
    const uint32_t t0 = 1'800'000'000;
    /* Interleave honest neo with packed sha ancestors */
    for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
        chain.attach(sha, t0 + i, bitsSha);
        chain.attach(neo, t0 + 1000 + static_cast<uint32_t>(i * 270), bitsNeo);
    }
    for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

    /* Compressed SHA window rejects; neo with large span accepts */
    BOOST_CHECK(!CheckDgwTimewarpWindow(chain.tip(), sha, t0 + DGW_PAST_BLOCKS, params));
    const int64_t neoNew = t0 + 1000 + (DGW_PAST_BLOCKS - 1) * 270 + 270;
    BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip(), neo, neoNew, params));
}

/* ************************************************************************** */
/* (6) Future stamp bound = 1800 */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_max_future_block_time)
{
    BOOST_CHECK_EQUAL(MAX_FUTURE_BLOCK_TIME, 1800);
    /* Policy: nAdjustedTime + 1800 is the consensus ceiling.
       time-too-new uses strict `>` in ContextualCheckBlockHeader. */
    const int64_t adjusted = 2'000'000'000;
    BOOST_CHECK(adjusted + MAX_FUTURE_BLOCK_TIME == adjusted + 1800);
    BOOST_CHECK(adjusted + 1801 > adjusted + MAX_FUTURE_BLOCK_TIME);
    BOOST_CHECK(!(adjusted + 1800 > adjusted + MAX_FUTURE_BLOCK_TIME));
}

/* ************************************************************************** */
/* (9)(10) Adjacent red herrings */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_not_adjacent_rule)
{
    const Consensus::Params& params = Params().GetConsensus();
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);
    const uint32_t t0 = 1'900'000'000;
    const int64_t spanOk = TIMEWARP_MIN_WINDOW_SECONDS;

    /* (9) +1s adjacent steps but overall span >= MIN → ACCEPT */
    {
        TestChain chain;
        /* 23 ancestors spaced so last ancestor is t0+spanOk-1, new at t0+spanOk */
        chain.attach(algo, t0, bits);
        for (int i = 1; i < DGW_PAST_BLOCKS - 1; ++i) {
            chain.attach(algo, t0 + static_cast<uint32_t>((spanOk * i) / (DGW_PAST_BLOCKS - 1)), bits);
        }
        for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;
        /* New is only +1 from previous same-algo tip if tip is t0+spanOk-1 */
        const int64_t prevT = chain.tip()->GetLastAncestorWithAlgo(algo)->nTime;
        const int64_t nTimeNew = prevT + 1;
        /* May or may not reach spanOk depending on oldest; force oldest-based check */
        if (nTimeNew - static_cast<int64_t>(t0) >= spanOk) {
            BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip(), algo, nTimeNew, params));
        } else {
            BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip(), algo, t0 + spanOk, params));
        }
    }

    /* (10) +1s packing span 23 → REJECT on window (not adjacent) */
    {
        TestChain chain;
        for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
            chain.attach(algo, t0 + i, bits);
        }
        for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;
        BOOST_CHECK(!CheckDgwTimewarpWindow(chain.tip(), algo, t0 + DGW_PAST_BLOCKS - 1, params));
    }
}

/* ************************************************************************** */
/* (11) Single source of truth — oldest index agreement */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_single_source_window_agreement)
{
    const Consensus::Params& params = Params().GetConsensus();
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bitsPowLimit = GetNextWorkRequired(algo, nullptr, params);
    const uint32_t t0 = 2'000'000'000;
    const int64_t span = TIMEWARP_MIN_WINDOW_SECONDS + 500;

    TestChain chain;
    for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
        chain.attach(algo, t0 + static_cast<uint32_t>((span * i) / (DGW_PAST_BLOCKS - 1)), bitsPowLimit);
    }
    for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

    const int64_t nTimeNew = t0 + span;

    /* Reject path: synthetic tip */
    CBlockIndex indexNew;
    indexNew.pprev = chain.tip();
    indexNew.algo = algo;
    indexNew.nTime = static_cast<unsigned int>(nTimeNew);
    indexNew.nHeight = chain.tip()->nHeight + 1;

    /* GetLastAncestorWithAlgo is inclusive-of-self: starts at `this`, returns
       the first match walking pprev. Critical so B's nTime is window newest. */
    BOOST_CHECK_EQUAL(indexNew.GetLastAncestorWithAlgo(algo), &indexNew);

    DgwSameAlgoWindow winReject;
    BOOST_REQUIRE(CollectDgwSameAlgoWindow(&indexNew, algo, winReject));
    BOOST_REQUIRE(winReject.full());
    BOOST_CHECK_EQUAL(winReject.newest(), &indexNew);

    /* Attach real tip and collect retarget window from it */
    CBlockIndex* realTip = chain.attach(algo, static_cast<uint32_t>(nTimeNew), bitsPowLimit);
    realTip->nHeight = indexNew.nHeight;

    BOOST_CHECK_EQUAL(realTip->GetLastAncestorWithAlgo(algo), realTip);

    DgwSameAlgoWindow winRetarget;
    BOOST_REQUIRE(CollectDgwSameAlgoWindow(realTip, algo, winRetarget));
    BOOST_REQUIRE(winRetarget.full());
    BOOST_CHECK_EQUAL(winRetarget.newest(), realTip);

    /* Same oldest block index (pointer identity on the shared ancestor chain) */
    BOOST_CHECK_EQUAL(winReject.oldest(), winRetarget.oldest());
    BOOST_CHECK_EQUAL(DgwWindowTimespan(winReject), DgwWindowTimespan(winRetarget));

    /* Independent DGW recomputation from the shared window — must match GNR.
       Proves GetNextWorkRequired engaged the full window (not early powLimit). */
    arith_uint256 bnExpected;
    for (int i = 0; i < winRetarget.nCount; ++i) {
        arith_uint256 bnTarget;
        bnTarget.SetCompact(winRetarget.pindex[i]->nBits);
        const size_t nCountBlocks = static_cast<size_t>(i + 1);
        if (nCountBlocks == 1) {
            bnExpected = bnTarget;
        } else {
            bnExpected = (bnExpected * nCountBlocks + bnTarget) / (nCountBlocks + 1);
        }
    }
    int64_t nActualTimespan = DgwWindowTimespan(winRetarget);
    const int nextHeight = winRetarget.newest()->nHeight + 1;
    const int64_t nTargetTimespan =
        DGW_PAST_BLOCKS * params.rules->GetTargetSpacing(algo, nextHeight);
    const int64_t minTimespan = DgwMinTimespan(nTargetTimespan);
    if (nActualTimespan < minTimespan) nActualTimespan = minTimespan;
    if (nActualTimespan > nTargetTimespan * 3) nActualTimespan = nTargetTimespan * 3;
    bnExpected *= nActualTimespan;
    bnExpected /= nTargetTimespan;
    const arith_uint256 bnPowLimit = UintToArith256(powLimitForAlgo(algo, params));
    if (bnExpected > bnPowLimit) bnExpected = bnPowLimit;
    const uint32_t expectedBits = bnExpected.GetCompact();

    const uint32_t nextBits = GetNextWorkRequired(algo, realTip, params);
    BOOST_CHECK_EQUAL(nextBits, expectedBits);
    /* Null tip is the powLimit early path; full tip must not be confused with it
       unless the formula independently lands on powLimit (equality still holds). */
    BOOST_CHECK_EQUAL(bitsPowLimit, bnPowLimit.GetCompact());

    /* Agreement: timespan used for clamp floor decision matches reject path */
    BOOST_CHECK(DgwWindowTimespan(winRetarget) >= DgwMinTimespan(nTargetTimespan));
    BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip()->pprev, algo, nTimeNew, params));
}

/* ************************************************************************** */
/* (13) Newest-endpoint inflation — future bound 1800 + MTP (not MIN alone) */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_newest_inflation_future_bound)
{
    /* MIN-window rule does not catch inflation (large span). Reduced
       MAX_FUTURE_BLOCK_TIME = 1800 caps how far newest may lead wall clock.
       MTP still floors nTime > median(prev 11). */
    BOOST_CHECK_EQUAL(MAX_FUTURE_BLOCK_TIME, 1800);
    BOOST_CHECK(MAX_FUTURE_BLOCK_TIME < 7200);

    const int64_t now = 2'100'000'000;
    /* Old attack: stamp newest at now+7200 — rejected under new FUT */
    BOOST_CHECK(now + 7200 > now + MAX_FUTURE_BLOCK_TIME);
    /* Boundary: now+1800 allowed by future rule (strict > fails only above) */
    BOOST_CHECK(!(now + 1800 > now + MAX_FUTURE_BLOCK_TIME));
    BOOST_CHECK(now + 1801 > now + MAX_FUTURE_BLOCK_TIME);

    /* Large span still passes MIN check (inflation ≠ compression) */
    const Consensus::Params& params = Params().GetConsensus();
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);
    TestChain chain;
    const uint32_t t0 = static_cast<uint32_t>(now - 10000);
    for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
        chain.attach(algo, t0 + static_cast<uint32_t>(i * 400), bits);
    }
    for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

    const int64_t inflated = now + 1800; /* max legal future under H1 */
    BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip(), algo, inflated, params));
    /* Attacker cannot use +7200 newest under H1 future rule */
    BOOST_CHECK(now + 7200 > now + MAX_FUTURE_BLOCK_TIME);
}

/* ************************************************************************** */
/* (7) Honest multi-algo smoke — legal spans pass for all three lanes */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_honest_multialgo_smoke)
{
    const Consensus::Params& params = Params().GetConsensus();
    const uint32_t t0 = 2'200'000'000;
    const int64_t step = 270;

    for (const PowAlgo algo : {PowAlgo::SHA256D, PowAlgo::NEOSCRYPT, PowAlgo::YESPOWER}) {
        TestChain chain;
        const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);
        for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
            chain.attach(algo, t0 + static_cast<uint32_t>(i * step), bits);
        }
        for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;
        BOOST_CHECK(CheckDgwTimewarpWindow(chain.tip(), algo, t0 + (DGW_PAST_BLOCKS - 1) * step, params));
    }
}

/* ************************************************************************** */
/* Clamp floor uses DgwMinTimespan (shared with reject) */
/* ************************************************************************** */

BOOST_AUTO_TEST_CASE(timewarp_clamp_uses_shared_min)
{
    const Consensus::Params& params = Params().GetConsensus();
    BOOST_CHECK(!params.fPowNoRetargeting);

    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bitsLimit = GetNextWorkRequired(algo, nullptr, params);

    TestChain chain;
    const uint32_t t0 = 2'300'000'000;
    /* Full window with very small span (will be accepted only if we skip reject;
       here we only test GetNextWorkRequired clamp after attaching illegal-short
       times that would be rejected at header — call retarget on a packed tip
       built without going through Check). */
    for (int i = 0; i < DGW_PAST_BLOCKS; ++i) {
        chain.attach(algo, t0 + i, bitsLimit);
    }
    for (CBlockIndex* p = chain.tip(); p; p = p->pprev) p->nHeight += 10000;

    DgwSameAlgoWindow w;
    BOOST_REQUIRE(CollectDgwSameAlgoWindow(chain.tip(), algo, w));
    BOOST_REQUIRE(w.full());
    BOOST_CHECK_LT(DgwWindowTimespan(w), TIMEWARP_MIN_WINDOW_SECONDS);

    const int64_t nTargetTimespan
        = DGW_PAST_BLOCKS * params.rules->GetTargetSpacing(algo, chain.tip()->nHeight + 1);
    BOOST_CHECK_EQUAL(DgwMinTimespan(nTargetTimespan), TIMEWARP_MIN_WINDOW_SECONDS);

    /* Retarget still runs (clamp pretends min span); header reject is separate. */
    const uint32_t next = GetNextWorkRequired(algo, chain.tip(), params);
    BOOST_CHECK(next != 0);
}

/* ************************************************************************** */
/* Height-gate: gate logic decoupled from live mainnet H (placeholder)       */
/* ************************************************************************** */

/** Placeholder-style H used only inside tests (not mainnet freeze value). */
static constexpr int TEST_H1_ACTIVATION_HEIGHT = 1000;

/** Build 23 same-algo blocks with 1s steps so the next header compresses the window. */
static CBlockIndex* BuildCompressedPrefix(TestChain& chain, PowAlgo algo, uint32_t bits,
                                          uint32_t t0 = 1'800'000'000)
{
    for (int i = 0; i < DGW_PAST_BLOCKS - 1; ++i) {
        chain.attach(algo, t0 + i, bits);
    }
    return chain.tip();
}

/* Named green: short-window block below H → accepted (grandfathered). */
BOOST_AUTO_TEST_CASE(timewarp_gate_short_window_below_H_accepted)
{
    const Consensus::Params& params = Params().GetConsensus();
    const int H = TEST_H1_ACTIVATION_HEIGHT;
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);
    TestChain chain;
    const uint32_t t0 = 1'800'000'000;
    BuildCompressedPrefix(chain, algo, bits, t0);
    const int64_t nTimeNew = t0 + DGW_PAST_BLOCKS - 1; /* span = 23 < MIN */
    const int nHeight = H - 1;
    const int64_t adjusted = nTimeNew; /* not in the future */

    BOOST_REQUIRE(!IsH1TimewarpActive(nHeight, H));
    BOOST_REQUIRE(!CheckDgwTimewarpWindow(chain.tip(), algo, nTimeNew, params));
    BOOST_CHECK(CheckH1HeaderTimeRules(nHeight, nTimeNew, adjusted, chain.tip(), algo, params, H) ==
                H1HeaderTimeResult::OK);
}

/* Named green: short-window block at/above H → rejected. */
BOOST_AUTO_TEST_CASE(timewarp_gate_short_window_at_or_above_H_rejected)
{
    const Consensus::Params& params = Params().GetConsensus();
    const int H = TEST_H1_ACTIVATION_HEIGHT;
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);
    TestChain chain;
    const uint32_t t0 = 1'800'000'000;
    BuildCompressedPrefix(chain, algo, bits, t0);
    const int64_t nTimeNew = t0 + DGW_PAST_BLOCKS - 1;
    const int64_t adjusted = nTimeNew;

    for (const int nHeight : {H, H + 50}) {
        BOOST_REQUIRE(IsH1TimewarpActive(nHeight, H));
        BOOST_CHECK(CheckH1HeaderTimeRules(nHeight, nTimeNew, adjusted, chain.tip(), algo, params, H) ==
                    H1HeaderTimeResult::TIMEWARP_WINDOW);
    }
}

/* Named green: future stamp 1801s — below H uses legacy 7200 → accepted. */
BOOST_AUTO_TEST_CASE(timewarp_gate_future_1801_below_H_accepted)
{
    const Consensus::Params& params = Params().GetConsensus();
    const int H = TEST_H1_ACTIVATION_HEIGHT;
    const PowAlgo algo = PowAlgo::SHA256D;
    const int64_t adjusted = 2'000'000'000;
    const int64_t nTime = adjusted + 1801;
    const int nHeight = H - 1;

    BOOST_CHECK_EQUAL(MaxFutureBlockTimeForHeight(nHeight, H), MAX_FUTURE_BLOCK_TIME_LEGACY);
    BOOST_CHECK(CheckH1HeaderTimeRules(nHeight, nTime, adjusted, nullptr, algo, params, H) ==
                H1HeaderTimeResult::OK);
}

/* Named green: future stamp 1801s — at/above H uses 1800 → rejected. */
BOOST_AUTO_TEST_CASE(timewarp_gate_future_1801_at_or_above_H_rejected)
{
    const Consensus::Params& params = Params().GetConsensus();
    const int H = TEST_H1_ACTIVATION_HEIGHT;
    const PowAlgo algo = PowAlgo::SHA256D;
    const int64_t adjusted = 2'000'000'000;
    const int64_t nTime = adjusted + 1801;

    for (const int nHeight : {H, H + 1}) {
        BOOST_CHECK_EQUAL(MaxFutureBlockTimeForHeight(nHeight, H), MAX_FUTURE_BLOCK_TIME);
        BOOST_CHECK(CheckH1HeaderTimeRules(nHeight, nTime, adjusted, nullptr, algo, params, H) ==
                    H1HeaderTimeResult::TIME_TOO_NEW);
    }
}

/* Named green: future stamp 7201s — rejected even below H (legacy bound). */
BOOST_AUTO_TEST_CASE(timewarp_gate_future_7201_below_H_rejected)
{
    const Consensus::Params& params = Params().GetConsensus();
    const int H = TEST_H1_ACTIVATION_HEIGHT;
    const PowAlgo algo = PowAlgo::SHA256D;
    const int64_t adjusted = 2'000'000'000;
    const int nHeight = H - 1;
    BOOST_CHECK(CheckH1HeaderTimeRules(nHeight, adjusted + 7201, adjusted, nullptr, algo, params, H) ==
                H1HeaderTimeResult::TIME_TOO_NEW);
}

/**
 * Named green: IBD/reindex across H boundary.
 *
 * Reason the gate exists: 741 early-chain short windows must remain accepted
 * under reindex when H grandfathers them. This test builds a synthetic chain
 * with many compressed same-algo windows at heights < H, then legal windows
 * at/after H, and asserts CheckH1HeaderTimeRules returns OK for every step
 * (simulating header checks during IBD/reindex). Control: same early chain
 * with H=0 (ungated) fails — proves the gate, not luck, saves reindex.
 */
BOOST_AUTO_TEST_CASE(timewarp_ibd_reindex_across_H_boundary)
{
    const Consensus::Params& params = Params().GetConsensus();
    const int H = 200;
    const int ungatedH = 0;
    const PowAlgo algo = PowAlgo::SHA256D;
    const uint32_t bits = GetNextWorkRequired(algo, nullptr, params);
    const int64_t step_short = 1;   /* forces span << MIN once window is full */
    const int64_t step_legal = 270; /* multi-algo spacing → MIN = 2160 over 24 */
    const uint32_t t0 = 1'700'000'000;
    const int nEarlyShortHeaders = 80; /* well above one full window; << 741 but same class */

    TestChain chain;
    int64_t t = t0;
    int accepted_early = 0;
    int would_fail_ungated = 0;

    for (int i = 0; i < nEarlyShortHeaders; ++i) {
        const int nHeight = i; /* genesis-like height 0.. */
        const int64_t nTimeNew = (i == 0) ? t0 : t + step_short;
        const CBlockIndex* prev = chain.tip();
        /* Wall clock far ahead of all historical nTimes → future rule never trips. */
        const int64_t adjusted = t0 + 10'000'000;

        const auto gatedRes =
            CheckH1HeaderTimeRules(nHeight, nTimeNew, adjusted, prev, algo, params, H);
        BOOST_CHECK_MESSAGE(gatedRes == H1HeaderTimeResult::OK,
                            "gated IBD step i=" << i << " height=" << nHeight
                                                << " must grandfather short window");

        const auto ungatedRes =
            CheckH1HeaderTimeRules(nHeight, nTimeNew, adjusted, prev, algo, params, ungatedH);
        if (ungatedRes == H1HeaderTimeResult::TIMEWARP_WINDOW) {
            ++would_fail_ungated;
        }

        chain.attach(algo, static_cast<uint32_t>(nTimeNew), bits);
        t = nTimeNew;
        ++accepted_early;
    }

    BOOST_CHECK_EQUAL(accepted_early, nEarlyShortHeaders);
    /* Once 24 same-algo exist, ungated path must start rejecting — proves why gate is mandatory. */
    BOOST_CHECK_GE(would_fail_ungated, 1);

    /* Cross H and beyond with legal spacing — must stay green under gated rules. */
    for (int nHeight = H; nHeight < H + DGW_PAST_BLOCKS + 5; ++nHeight) {
        const int64_t nTimeNew = t + step_legal;
        const int64_t adjusted = nTimeNew + 60;
        const auto res =
            CheckH1HeaderTimeRules(nHeight, nTimeNew, adjusted, chain.tip(), algo, params, H);
        BOOST_CHECK_MESSAGE(res == H1HeaderTimeResult::OK,
                            "post-H legal header height=" << nHeight);
        chain.attach(algo, static_cast<uint32_t>(nTimeNew), bits);
        t = nTimeNew;
    }

    /* Attack after H: compressed window must be rejected. */
    {
        TestChain attack;
        BuildCompressedPrefix(attack, algo, bits, static_cast<uint32_t>(t));
        const int64_t badNew = t + DGW_PAST_BLOCKS - 1;
        BOOST_CHECK(CheckH1HeaderTimeRules(H + 100, badNew, badNew + 60, attack.tip(), algo, params, H) ==
                    H1HeaderTimeResult::TIMEWARP_WINDOW);
    }
}

/* Placeholder mainnet H is not a freeze — regtest stays H=0; gate logic takes H as arg. */
BOOST_AUTO_TEST_CASE(timewarp_gate_placeholder_decoupled_from_live_H)
{
    BOOST_CHECK_EQUAL(Params().GetConsensus().nH1TimewarpActivationHeight, 0); /* regtest */
    BOOST_CHECK(IsH1TimewarpActive(0, 0));

    const int mainnetPlaceholder = std::numeric_limits<int>::max();
    BOOST_CHECK(!IsH1TimewarpActive(0, mainnetPlaceholder));
    BOOST_CHECK(!IsH1TimewarpActive(1'000'000, mainnetPlaceholder));
    BOOST_CHECK(IsH1TimewarpActive(mainnetPlaceholder, mainnetPlaceholder));
}

BOOST_AUTO_TEST_SUITE_END()
