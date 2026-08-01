// Copyright (c) 2026 The Bloodstone developers
// QUASAR Phase 5 — consensus braid validation (active only after fork lock-in).

#include <quasar/braid_validation.h>

#include <chain.h>
#include <consensus/params.h>
#include <deploymentstatus.h>
#include <powdata.h>
#include <util/system.h>

#include <map>
#include <string>

namespace {

constexpr int DEFAULT_EPOCH_BLOCKS = 10;
constexpr double SKEW_SHA256D_FRACTION = 0.85;
constexpr double SKEW_CPU_MIN_FRACTION = 0.10;

struct BraidCounts {
    int sha256d{0};
    int neoscrypt{0};
    int yespower{0};
    int unknown{0};
};

int EpochBlocks()
{
    return std::max(1, static_cast<int>(gArgs.GetArg("-quasarepochblocks", int64_t{DEFAULT_EPOCH_BLOCKS})));
}

bool EnforcementEnabled()
{
    return gArgs.GetBoolArg("-quasarbraidconsensus", true);
}

BraidCounts CountAlgo(PowAlgo algo)
{
    BraidCounts c;
    switch (algo) {
    case PowAlgo::SHA256D:
        ++c.sha256d;
        break;
    case PowAlgo::NEOSCRYPT:
        ++c.neoscrypt;
        break;
    case PowAlgo::YESPOWER:
        ++c.yespower;
        break;
    default:
        ++c.unknown;
        break;
    }
    return c;
}

BraidCounts& operator+=(BraidCounts& a, const BraidCounts& b)
{
    a.sha256d += b.sha256d;
    a.neoscrypt += b.neoscrypt;
    a.yespower += b.yespower;
    a.unknown += b.unknown;
    return a;
}

const char* BraidStatus(const BraidCounts& c)
{
    const int total = c.sha256d + c.neoscrypt + c.yespower;
    if (total == 0) return "empty";
    const double sha_frac = static_cast<double>(c.sha256d) / total;
    const double cpu_frac = static_cast<double>(c.neoscrypt + c.yespower) / total;
    if (sha_frac >= SKEW_SHA256D_FRACTION && cpu_frac < SKEW_CPU_MIN_FRACTION) {
        return "deferred";
    }
    return "healthy";
}

struct AlgoSample {
    int height{0};
    const CBlockIndex* pindex{nullptr};
};

/** Highest block per algo within the epoch ending at epoch_end_height. */
void CollectEpochAlgos(
    const CBlock& block,
    const CBlockIndex* pindexPrev,
    int epoch_end_height,
    int epoch_blocks,
    std::map<PowAlgo, AlgoSample>& best_per_algo)
{
    const int epoch_start = epoch_end_height - epoch_blocks + 1;

    auto consider = [&](int height, PowAlgo algo, const CBlockIndex* pindex) {
        if (height < epoch_start || height > epoch_end_height) return;
        if (algo == PowAlgo::INVALID) return;
        auto it = best_per_algo.find(algo);
        if (it == best_per_algo.end() || height > it->second.height) {
            best_per_algo[algo] = {height, pindex};
        }
    };

    consider(epoch_end_height, block.pow.getCoreAlgo(), pindexPrev);

    const CBlockIndex* walk = pindexPrev;
    while (walk != nullptr && static_cast<int>(walk->nHeight) >= epoch_start) {
        consider(static_cast<int>(walk->nHeight), walk->algo, walk);
        if (static_cast<int>(walk->nHeight) == epoch_start) break;
        walk = walk->pprev;
    }
}

bool AncestorWithinEpoch(const CBlockIndex* start, const uint256& target_hash, int epoch_start)
{
    const CBlockIndex* walk = start;
    int steps = 0;
    while (walk != nullptr && static_cast<int>(walk->nHeight) >= epoch_start && steps < DEFAULT_EPOCH_BLOCKS * 3) {
        if (walk->GetBlockHash() == target_hash) return true;
        walk = walk->pprev;
        ++steps;
    }
    return false;
}

bool EpochContinuityOk(
    const CBlockIndex* prev_epoch_tip,
    const std::map<PowAlgo, AlgoSample>& best_per_algo,
    int epoch_start)
{
    if (prev_epoch_tip == nullptr) return true;

    const uint256 prev_hash = prev_epoch_tip->GetBlockHash();
    int streams = 0;
    for (const auto& item : best_per_algo) {
        const CBlockIndex* start = item.second.pindex;
        if (start == nullptr) continue;
        if (AncestorWithinEpoch(start, prev_hash, epoch_start)) {
            ++streams;
        }
    }
    return streams >= 2;
}

const CBlockIndex* PreviousEpochTip(const CBlockIndex* pindexPrev, int epoch_blocks)
{
    if (pindexPrev == nullptr) return nullptr;
    const CBlockIndex* walk = pindexPrev;
    for (int i = 0; i < epoch_blocks - 1 && walk != nullptr; ++i) {
        walk = walk->pprev;
    }
    return walk != nullptr ? walk->pprev : nullptr;
}

} // namespace

bool QuasarCheckBraidFinality(
    const CBlock& block,
    const CBlockIndex* pindexPrev,
    const Consensus::Params& consensusParams,
    BlockValidationState& state)
{
    if (!EnforcementEnabled()) return true;
    if (pindexPrev == nullptr) return true;
    if (!DeploymentActiveAfter(pindexPrev, consensusParams, Consensus::DEPLOYMENT_QUASAR_BRAID)) {
        return true;
    }

    const int epoch_blocks = EpochBlocks();
    const int height = pindexPrev->nHeight + 1;

    // Evaluate at epoch boundary only.
    if ((height + 1) % epoch_blocks != 0) return true;

    BraidCounts counts;
    const int epoch_start = height - epoch_blocks + 1;
    const CBlockIndex* walk = pindexPrev;
    while (walk != nullptr && static_cast<int>(walk->nHeight) >= epoch_start) {
        counts += CountAlgo(walk->algo);
        if (static_cast<int>(walk->nHeight) == epoch_start) break;
        walk = walk->pprev;
    }
    counts += CountAlgo(block.pow.getCoreAlgo());

    const char* status = BraidStatus(counts);
    if (std::string(status) != "deferred") return true;

    std::map<PowAlgo, AlgoSample> best_per_algo;
    CollectEpochAlgos(block, pindexPrev, height, epoch_blocks, best_per_algo);

    const CBlockIndex* prev_epoch_tip = PreviousEpochTip(pindexPrev, epoch_blocks);
    if (!EpochContinuityOk(prev_epoch_tip, best_per_algo, epoch_start)) {
        return state.Invalid(
            BlockValidationResult::BLOCK_CONSENSUS,
            "bad-quasar-braid",
            strprintf(
                "quasar braid finality: deferred epoch at height %d lacks cross-algo restitch (sha256d=%d neoscrypt=%d yespower=%d)",
                height, counts.sha256d, counts.neoscrypt, counts.yespower));
    }

    return true;
}