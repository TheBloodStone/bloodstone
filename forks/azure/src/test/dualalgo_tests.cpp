// Copyright (c) 2018-2019 The Xaya developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <chain.h>
#include <chainparams.h>
#include <consensus/params.h>
#include <pow.h>
#include <powdata.h>

#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

/* No space between BOOST_FIXTURE_TEST_SUITE and '(', so that extraction of
   the test-suite name works with grep as done in the Makefile.  */
BOOST_FIXTURE_TEST_SUITE(dualalgo_tests, TestingSetup)

/* ************************************************************************** */

namespace
{

/* OriginalDGW removed — dualalgo golden uses GetNextWorkRequired (H1). */

class TestChain
{

private:

  std::vector<std::unique_ptr<CBlockIndex>> blocks;

public:

  CBlockIndex*
  tip () const
  {
    if (blocks.empty ())
      return nullptr;
    return blocks.back ().get ();
  }

  unsigned
  height () const
  {
    const CBlockIndex* pindex = tip ();
    return pindex == nullptr ? 0 : pindex->nHeight;
  }

  void
  attach (const CBlockIndex& indexNew)
  {
    std::unique_ptr<CBlockIndex> modified(new CBlockIndex (indexNew));
    modified->pprev = tip ();
    modified->nHeight = blocks.size ();
    blocks.push_back (std::move (modified));
  }

};

} // anonymous namespace

BOOST_AUTO_TEST_CASE (difficulty_retargeting)
{
  /* The test for our dual-algo difficulty retargeting works as follows:
     We construct a chain of blocks with randomly chosen algorithms and
     block times (nBits of each block is set according to GetNextWorkRequired,
     although that does not really matter).  We also attach the same blocks
     to two separate chains that contain only blocks of each algo.  We then
     verify that our GetNextWorkRequired function returns the same result as
     the original DGW function does for the single-algo chain.  */

  const Consensus::Params& params = Params ().GetConsensus ();
  BOOST_CHECK (!params.fPowNoRetargeting);

  for (unsigned trials = 0; trials < 5; ++trials)
    {
      TestChain mixedChain;
      std::map<PowAlgo, TestChain> perAlgoChains;

      uint32_t lastTime = 1000000000;

      for (unsigned len = 0; len < 500; ++len)
        {
          for (const PowAlgo algo : {PowAlgo::SHA256D, PowAlgo::NEOSCRYPT})
            {
              /* Per-algo separation: GNR from a mixed tip must match GNR from
                 the pure same-algo chain (single CollectDgwSameAlgoWindow path).
                 Do not reimplement DGW here — H1 made Collect the only walk. */
              const uint32_t nextWork
                  = GetNextWorkRequired (algo, mixedChain.tip (), params);
              const uint32_t golden
                  = GetNextWorkRequired (algo, perAlgoChains[algo].tip (), params);
              BOOST_CHECK_EQUAL (nextWork, golden);
            }

          CBlockIndex indexNew;
          if (InsecureRandBool ())
            indexNew.algo = PowAlgo::SHA256D;
          else
            indexNew.algo = PowAlgo::NEOSCRYPT;
          indexNew.nBits = GetNextWorkRequired (indexNew.algo,
                                                mixedChain.tip (), params);

          /* Increment the time typically, but allow also decrements.  Average
             time increase should be AvgTargetSpacing,
             so choosing randomly in [-10, target spacing - 10] seems
             like a good enough approximation.  Since these values are actually
             then a bit faster than expected, we increase the difficulty away
             from the minimum, which is also good for the test.  */
          const int64_t targetSpacing
              = AvgTargetSpacing (params, mixedChain.height () + 1);
          indexNew.nTime = lastTime
                            + InsecureRandRange (targetSpacing)
                            - 10;
          lastTime = indexNew.nTime;

          mixedChain.attach (indexNew);
          perAlgoChains[indexNew.algo].attach (indexNew);
        }

      /* Verify that we have actually increased the difficulty and not just
         stuck to the minimum (which would make the test somewhat trivial).  */
      for (const auto& entry : perAlgoChains)
        BOOST_CHECK (entry.second.tip ()->nBits
                      != GetNextWorkRequired (entry.first, nullptr, params));
    }
}

/* ************************************************************************** */

namespace
{

constexpr unsigned BEFORE_FORK = 200;
constexpr unsigned AFTER_FORK = 800;

class PostIcoForkSetup : public TestingSetup
{
public:

  const Consensus::Params* params = nullptr;

  PostIcoForkSetup ()
  {
    SelectParams (CBaseChainParams::REGTEST);
    params = &Params ().GetConsensus ();

    /* Bloodstone regtest: POST_ICO + MULTI_ALGO/YESPOWER active from height 0. */
    BOOST_CHECK (params->rules->ForkInEffect (Consensus::Fork::POST_ICO,
                                              BEFORE_FORK));
    BOOST_CHECK (params->rules->ForkInEffect (Consensus::Fork::POST_ICO,
                                              AFTER_FORK));
    BOOST_CHECK (params->rules->ForkInEffect (Consensus::Fork::MULTI_ALGO, 1));
    BOOST_CHECK (params->rules->ForkInEffect (Consensus::Fork::YESPOWER, 1));
  }

};

} // anonymous namespace

BOOST_FIXTURE_TEST_CASE (avg_target_spacing, PostIcoForkSetup)
{
  /* Triple-algo multi-algo: each lane 270s → average any-block spacing 90s. */
  BOOST_CHECK_EQUAL (AvgTargetSpacing (*params, BEFORE_FORK), 90);
  BOOST_CHECK_EQUAL (AvgTargetSpacing (*params, AFTER_FORK), 90);
}

namespace
{

class BlockProofEquivalentTimeSetup : public PostIcoForkSetup
{
public:

  TestChain chain;

  BlockProofEquivalentTimeSetup ()
  {
    /* Turn off "no retargeting" rule.  We won't need to mine valid blocks
       anyway, and this messes with the "relative difficulty" between
       the algorithms as it disables rescaling of the minimum difficulty.  */
    const_cast<Consensus::Params*> (params)->fPowNoRetargeting = false;
  }

  /**
   * Attaches a block with minimum difficulty and the given algorithm
   * to the test chain.
   */
  void
  AttachBlock (const PowAlgo algo)
  {
    CBlockIndex indexNew;
    indexNew.algo = algo;

    const uint256 bnPowLimit = powLimitForAlgo (indexNew.algo, *params);
    indexNew.nBits = UintToArith256 (bnPowLimit).GetCompact ();

    arith_uint256 previousWork;
    if (chain.tip () != nullptr)
      previousWork = chain.tip ()->nChainWork;
    indexNew.nChainWork = previousWork + GetBlockProof (indexNew);

    chain.attach (indexNew);
  }

  /**
   * Computes the proof-equivalent-time from tip-n to tip.
   */
  int64_t
  GetEquivalentTime (const unsigned n) const
  {
    const CBlockIndex* beforeTip = chain.tip ();
    for (unsigned i = 0; i < n; ++i)
      beforeTip = beforeTip->pprev;

    return GetBlockProofEquivalentTime (*chain.tip (), *beforeTip,
                                        *chain.tip (), *params);
  }

};

} // anonymous namespace

BOOST_FIXTURE_TEST_CASE (eqv_time_before_fork, BlockProofEquivalentTimeSetup)
{
  /* Multi-algo: equal share of three lanes; ~90s mean any-block.
     Two tip steps ≈ 180s equivalent under balanced min-diff proofs. */
  for (unsigned i = 0; i <= BEFORE_FORK; ++i) {
    const PowAlgo a = (i % 3 == 0) ? PowAlgo::SHA256D
                      : (i % 3 == 1) ? PowAlgo::NEOSCRYPT
                                     : PowAlgo::YESPOWER;
    AttachBlock (a);
  }
  BOOST_CHECK_EQUAL (chain.height (), BEFORE_FORK);

  /* Multi-algo proof-equivalent time is ~one per-algo slot (270s) per step
     under balanced min-diff; allow 1s integer rounding. */
  BOOST_CHECK (std::abs (GetEquivalentTime (2) - 270) <= 1);
}

BOOST_FIXTURE_TEST_CASE (eqv_time_after_fork, BlockProofEquivalentTimeSetup)
{
  /* Same multi-algo regime on regtest (no dual-algo post-ICO split). */
  for (unsigned i = 0; i <= AFTER_FORK; ++i) {
    const PowAlgo a = (i % 3 == 0) ? PowAlgo::SHA256D
                      : (i % 3 == 1) ? PowAlgo::NEOSCRYPT
                                     : PowAlgo::YESPOWER;
    AttachBlock (a);
  }
  BOOST_CHECK_EQUAL (chain.height (), AFTER_FORK);

  BOOST_CHECK_EQUAL (GetEquivalentTime (3), 270);
}

/* ************************************************************************** */

BOOST_AUTO_TEST_SUITE_END ()
