// Temporary genesis hash diagnostic (cross-platform).
#include <consensus/merkle.h>
#include <powdata.h>
#include <primitives/block.h>
#include <primitives/transaction.h>
#include <uint256.h>
#include <amount.h>
#include <script/script.h>
#include <iostream>
#include <cstdlib>

namespace {

constexpr const char pszTimestampMainnet[]
    = "22/Jun/2026: Bloodstone independent chain relaunch";
constexpr CAmount premineAmount = 199999998 * COIN;
constexpr const char hexPreminePubKeyHashMainnet[]
    = "848e5af187579f268773a58e44e882d2c04ca883";

CBlock CreateGenesisBlock(const CScript& genesisInputScript, const CScript& genesisOutputScript,
                          uint32_t nTime, uint32_t nNonce, uint32_t nBits, int32_t nVersion,
                          const CAmount& genesisReward)
{
    CMutableTransaction txNew;
    txNew.nVersion = 1;
    txNew.vin.resize(1);
    txNew.vout.resize(1);
    txNew.vin[0].scriptSig = genesisInputScript;
    txNew.vout[0].nValue = genesisReward;
    txNew.vout[0].scriptPubKey = genesisOutputScript;

    CBlock genesis;
    genesis.nTime = nTime;
    genesis.nBits = 0;
    genesis.nNonce = 0;
    genesis.nVersion = nVersion;
    genesis.vtx.push_back(MakeTransactionRef(std::move(txNew)));
    genesis.hashPrevBlock.SetNull();
    genesis.hashMerkleRoot = BlockMerkleRoot(genesis);

    std::unique_ptr<CPureBlockHeader> fakeHeader(new CPureBlockHeader());
    fakeHeader->nNonce = nNonce;
    fakeHeader->hashMerkleRoot = genesis.GetHash();
    genesis.pow.setCoreAlgo(PowAlgo::NEOSCRYPT);
    genesis.pow.setBits(nBits);
    genesis.pow.setFakeHeader(std::move(fakeHeader));

    return genesis;
}

CBlock CreateGenesisBlockP2PKH(uint32_t nTime, uint32_t nNonce, uint32_t nBits,
                               const std::string& timestamp, const uint160& preminePubKeyHash)
{
    const std::vector<unsigned char> timestampData(timestamp.begin(), timestamp.end());
    const CScript genesisInput = CScript() << timestampData;

    std::vector<unsigned char> pubKeyHash(preminePubKeyHash.begin(), preminePubKeyHash.end());
    std::reverse(pubKeyHash.begin(), pubKeyHash.end());
    const CScript genesisOutput = CScript()
        << OP_DUP << OP_HASH160 << pubKeyHash << OP_EQUALVERIFY << OP_CHECKSIG;

    return CreateGenesisBlock(genesisInput, genesisOutput, nTime, nNonce, nBits, 1, premineAmount);
}

} // namespace

int main()
{
    const CBlock genesis = CreateGenesisBlockP2PKH(
        1780569600, 676154, 0x1e0ffff0,
        pszTimestampMainnet,
        uint160S(hexPreminePubKeyHashMainnet));

    std::cout << "block_hash=" << genesis.GetHash().GetHex() << std::endl;
    std::cout << "merkle_root=" << genesis.hashMerkleRoot.GetHex() << std::endl;
    std::cout << "tx_hash=" << genesis.vtx[0]->GetHash().GetHex() << std::endl;
    std::cout << "expected=df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0" << std::endl;
    return 0;
}