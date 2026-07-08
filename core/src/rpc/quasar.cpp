// Copyright (c) 2026 The Bloodstone developers
// QUASAR Phase 3 — braid index RPC (reads indexes/braid/rpc-export.json).

#include <fs.h>
#include <rpc/server.h>
#include <rpc/util.h>
#include <univalue.h>
#include <util/system.h>

#include <fstream>
#include <sstream>

static UniValue ReadBraidExport()
{
    const fs::path path = fsbridge::AbsPathJoin(gArgs.GetDataDirNet(), "indexes/braid/rpc-export.json");
    std::ifstream file{path};
    if (!file.good()) {
        UniValue empty(UniValue::VOBJ);
        empty.pushKV("ok", false);
        empty.pushKV("error", "braid index not synced — run sync-quasar-braid-index.py");
        empty.pushKV("phase", 3);
        empty.pushKV("enforcement_mode", "policy");
        return empty;
    }
    std::ostringstream ss;
    ss << file.rdbuf();
    UniValue parsed;
    if (!parsed.read(ss.str())) {
        throw JSONRPCError(RPC_INTERNAL_ERROR, "invalid braid index JSON");
    }
    return parsed;
}

static RPCHelpMan getquasarbraid()
{
    return RPCHelpMan{"getquasarbraid",
        "\nReturns QUASAR epoch braid index state from indexes/braid/ (Phase 3).\n",
        {},
        RPCResult{RPCResult::Type::OBJ, "", "",
            {
                {RPCResult::Type::BOOL, "ok", "Whether braid index data is available"},
                {RPCResult::Type::STR, "braid_status", "Current epoch braid status"},
                {RPCResult::Type::NUM, "phase", "QUASAR phase"},
                {RPCResult::Type::NUM, "synced_height", "Last indexed block height"},
            }},
        RPCExamples{
            HelpExampleCli("getquasarbraid", "")
          + HelpExampleRpc("getquasarbraid", "")
        },
        [&](const RPCHelpMan& self, const JSONRPCRequest& request) -> UniValue
    {
        return ReadBraidExport();
    }};
}

static RPCHelpMan getquasaractivation()
{
    return RPCHelpMan{"getquasaractivation",
        "\nReturns QUASAR braid finality soft-fork deployment parameters (Phase 3 research).\n",
        {},
        RPCResult{RPCResult::Type::OBJ, "", "",
            {
                {RPCResult::Type::STR, "deployment", "BIP9 deployment name"},
                {RPCResult::Type::NUM, "version_bit", "Signaling version bit"},
                {RPCResult::Type::STR, "state", "Deployment state"},
                {RPCResult::Type::NUM, "epoch_blocks", "Epoch braid block count"},
            }},
        RPCExamples{
            HelpExampleCli("getquasaractivation", "")
          + HelpExampleRpc("getquasaractivation", "")
        },
        [&](const RPCHelpMan& self, const JSONRPCRequest& request) -> UniValue
    {
        UniValue ret(UniValue::VOBJ);
        ret.pushKV("deployment", "quasar_braid_finality");
        ret.pushKV("phase", 5);
        ret.pushKV("version_bit", 3);
        ret.pushKV("state", gArgs.GetArg("-quasarbraidfork", "defined"));
        ret.pushKV("enforcement_mode", gArgs.GetArg("-quasarenforce", "policy"));
        ret.pushKV("epoch_blocks", gArgs.GetArg("-quasarepochblocks", int64_t{10}));
        ret.pushKV("window_blocks", 2016);
        ret.pushKV("threshold_mainnet", 1815);
        ret.pushKV("threshold_testnet", 1512);
        ret.pushKV("consensus_braid_rejection", true);
        ret.pushKV("note", "Phase 5: consensus braid rejection at epoch boundaries when deployment active; signal bit 3 for lock-in.");
        return ret;
    }};
}

void RegisterQuasarRPCCommands(CRPCTable& t)
{
    static const CRPCCommand commands[] = {
        {"quasar", &getquasarbraid},
        {"quasar", &getquasaractivation},
    };
    for (const auto& c : commands) {
        t.appendCommand(c.name, &c);
    }
}