// Copyright (c) 2014-2020 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <chainparams.h>
#include <net.h>
#include <signet.h>
#include <uint256.h>
#include <validation.h>

#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

BOOST_FIXTURE_TEST_SUITE(validation_tests, TestingSetup)

/** Bloodstone mainnet: stepped issuance + QSE tail (not classic halvings). */
static void TestBlockSubsidyStepped(const Consensus::Params& consensusParams)
{
    BOOST_REQUIRE(consensusParams.nBlocksPerYear > 0);
    const int bpy = consensusParams.nBlocksPerYear;

    auto at_year = [&](int yearIndex) {
        // sample mid-year, after POST_ICO on mainnet
        const int h = yearIndex * bpy + bpy / 2;
        return GetBlockSubsidy(h, consensusParams);
    };

    BOOST_CHECK_EQUAL(at_year(0), 100 * COIN);
    BOOST_CHECK_EQUAL(at_year(1), 1000 * COIN);
    BOOST_CHECK_EQUAL(at_year(2), 1000 * COIN);
    BOOST_CHECK_EQUAL(at_year(3), 750 * COIN);
    BOOST_CHECK_EQUAL(at_year(4), 500 * COIN);
    BOOST_CHECK_EQUAL(at_year(5), 350 * COIN);
    BOOST_CHECK_EQUAL(at_year(6), 250 * COIN);
    BOOST_CHECK_EQUAL(at_year(7), consensusParams.qseBaseSubsidy); // 200
    BOOST_CHECK_EQUAL(at_year(20), consensusParams.qseBaseSubsidy);

    // Boundaries
    BOOST_CHECK_EQUAL(GetBlockSubsidy(bpy - 1, consensusParams), 100 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(bpy, consensusParams), 1000 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(3 * bpy, consensusParams), 750 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(7 * bpy, consensusParams), 200 * COIN);
}

BOOST_AUTO_TEST_CASE(block_subsidy_test)
{
    const auto chainParams = CreateChainParams(*m_node.args, CBaseChainParams::MAIN);
    TestBlockSubsidyStepped(chainParams->GetConsensus());
}

BOOST_AUTO_TEST_CASE(subsidy_limit_test)
{
    const auto chainParams = CreateChainParams(*m_node.args, CBaseChainParams::MAIN);
    const auto& cp = chainParams->GetConsensus();
    BOOST_REQUIRE(cp.nBlocksPerYear > 0);

    CAmount nSum = 0;
    // Sum year-1 mint only (bounded check)
    const int bpy = cp.nBlocksPerYear;
    // After POST_ICO heights pay stepped schedule; sum a slice of year 1
    for (int h = 10000; h < 10000 + 1000; ++h) {
        CAmount s = GetBlockSubsidy(h, cp);
        BOOST_CHECK_EQUAL(s, 100 * COIN);
        nSum += s;
        BOOST_CHECK(MoneyRange(nSum));
    }
    BOOST_CHECK_EQUAL(nSum, 1000 * 100 * COIN);

    // QSE never zero
    BOOST_CHECK(GetBlockSubsidy(20 * bpy, cp) > 0);
}

BOOST_AUTO_TEST_CASE(signet_parse_tests)
{
    ArgsManager signet_argsman;
    signet_argsman.ForceSetArg("-signetchallenge", "51"); // set challenge to OP_TRUE
    const auto signet_params = CreateChainParams(signet_argsman, CBaseChainParams::SIGNET);
    BOOST_CHECK_EQUAL(signet_params->GetConsensus().signet_blocks, true);
}

BOOST_AUTO_TEST_SUITE_END()
