// Copyright (c) 2026 The Bloodstone developers
// QUASAR Phase 5 — epoch braid finality checks when quasar_braid_finality is active.

#ifndef BITCOIN_QUASAR_BRAID_VALIDATION_H
#define BITCOIN_QUASAR_BRAID_VALIDATION_H

#include <consensus/params.h>
#include <powdata.h>
#include <validation.h>

class CBlock;
class CBlockIndex;

namespace Consensus {
struct Params;
}

/** Returns false and sets state when braid finality rules reject the block. */
bool QuasarCheckBraidFinality(
    const CBlock& block,
    const CBlockIndex* pindexPrev,
    const Consensus::Params& consensusParams,
    BlockValidationState& state);

#endif // BITCOIN_QUASAR_BRAID_VALIDATION_H