#!/usr/bin/env node
/** Bloodstone Economic Model white paper — pool rewards, subsidies, staking, and incentives. */
const fs = require("fs");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  Header,
  Footer,
  AlignmentType,
  LevelFormat,
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  PageNumber,
  PageBreak,
  ExternalHyperlink,
} = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
}
function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 160 },
    children: [new TextRun({ text, ...opts })],
  });
}
function bullet(ref, text) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80 },
    children: [new TextRun(text)],
  });
}
function linkPara(label, url) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [
      new ExternalHyperlink({
        children: [new TextRun({ text: label, style: "Hyperlink" })],
        link: url,
      }),
    ],
  });
}
function table(headers, rows, colWidths) {
  const tableWidth = 9360;
  const widths = colWidths || Array(headers.length).fill(Math.floor(tableWidth / headers.length));
  const headerRow = new TableRow({
    children: headers.map(
      (text, i) =>
        new TableCell({
          borders,
          width: { size: widths[i], type: WidthType.DXA },
          shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun({ text, bold: true })] })],
        })
    ),
  });
  const dataRows = rows.map(
    (row) =>
      new TableRow({
        children: row.map(
          (text, i) =>
            new TableCell({
              borders,
              width: { size: widths[i], type: WidthType.DXA },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun(String(text))] })],
            })
        ),
      })
  );
  return new Table({
    width: { size: tableWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: [headerRow, ...dataRows],
  });
}

const children = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: "Bloodstone Economic Model", size: 52, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "White Paper — STONE Issuance, Pool Incentives, and Long-Term Alignment",
        size: 32,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [new TextRun({ text: "July 2026 · v1.1 · Unified multi-algo pool", size: 24, italics: true })],
  }),

  h1("Executive Summary"),
  p(
    "Bloodstone (STONE) is a proof-of-work asset in the SpaceXpanse ecosystem. Its economic design ties together block issuance, a scheduled halving and long-run inflation curve, a unified mining pool across four algorithms, cross-algo subsidies, ASIC–mobile revenue sharing, staking contributions, and operator sustainability — without requiring miners to run separate pools per algorithm."
  ),
  p(
    "The central economic thesis: STONE should reward active hashrate proportionally, while deliberately routing value across CPU, browser, mobile, and ASIC participants so no single hardware class can capture the entire network. Block rewards flow through a transparent waterfall (finder bonus → staking slice → pool fee → proportional miners), then through algorithm-specific distribution rules that keep neoscrypt, yespower, and SHA256d rounds economically linked."
  ),
  p(
    "Issuance is not fixed forever. Bloodstone follows a two-phase monetary schedule inherited from SpaceXpanse ROD consensus: five halving eras, then ~2.956% annual inflation of the block reward for roughly six decades, before subsidies eventually tail to zero."
  ),

  h1("1. Monetary Base and Block Rewards"),
  h2("1.1 Bloodstone relaunch and genesis"),
  p(
    "Bloodstone mainnet relaunched in June 2026 as an independent chain (genesis message: “Bloodstone independent chain relaunch”). The genesis block allocates a one-time premine of 199,999,998 STONE to the project treasury address — the same premine magnitude used on legacy SpaceXpanse ROD mainnet, but on a fresh chain with no inherited UTXO set."
  ),
  p(
    "All proof-of-work blocks after genesis mint additional STONE according to GetBlockSubsidy() in the Bloodstone Core consensus code. The unified pool reads the actual coinbase value when closing a round; dashboard projections use the live subsidy when known, otherwise the configured default (currently 100 STONE in era 0)."
  ),

  h2("1.2 Halving schedule — how issuance works"),
  p(
    "Bloodstone inherits SpaceXpanse’s subsidy engine. Three consensus constants govern PoW minting:"
  ),
  bullet("bullets", "nSubsidyHalvingInterval = 1,054,080 blocks — one “era” per interval"),
  bullet("bullets", "initialSubsidy — starting PoW reward after the post-ICO fork (800 ROD on legacy SpaceXpanse; 100 STONE on the Bloodstone relaunch observed on mainnet in July 2026)"),
  bullet("bullets", "Inflation factor 1.02956 (~2.956% per era) — applied after the fifth halving instead of further halving"),
  p(
    "Halving index is computed as floor(blockHeight / 1,054,080). For halving indices 0 through 4, the subsidy is initialSubsidy right-shifted by the halving index (each era cuts the reward in half). From halving index 5 onward, the reward is no longer halved; instead each era mints a calculated inflation tranche spread evenly across the 1,054,080 blocks in that era."
  ),
  p(
    "On the Bloodstone relaunch there is no 1 STONE pre-ICO bootstrap phase — PoW blocks from height 1 pay the full era-0 subsidy (100 STONE as of July 2026). Legacy SpaceXpanse ROD used a 55,560-block pre-ICO period at 1 ROD before switching to the 800 ROD schedule."
  ),

  h3("1.2.1 Era 0–4 — the halving years"),
  p(
    "With a 100 STONE initial PoW reward (Bloodstone relaunch), the first five eras are:"
  ),
  table(
    ["Era", "Block height (start)", "Subsidy per block", "STONE minted in era¹"],
    [
      ["0", "1", "100 STONE", "~105.4 million"],
      ["1", "1,054,080", "50 STONE", "~52.7 million"],
      ["2", "2,108,160", "25 STONE", "~26.4 million"],
      ["3", "3,162,240", "12.5 STONE", "~13.2 million"],
      ["4", "4,216,320", "6.25 STONE", "~6.6 million"],
    ],
    [900, 2200, 2200, 4060]
  ),
  new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "¹Approximate; assumes full interval at constant subsidy.", italics: true, size: 22 })] }),
  p(
    "Calendar timing depends on average block spacing. Bloodstone triple-algo consensus targets ~270 seconds between blocks of the same algorithm, yielding roughly 80–90 seconds between successive blocks of any algorithm on mainnet in 2026. At ~80 seconds per block, one era is about 2.7 years; era 1 halving would fall around early 2029, era 4 around 2037."
  ),
  p(
    "If initialSubsidy were 800 STONE (legacy ROD parameter in chainparams), the same halving math applies but amounts are 8× larger during eras 0–4 (800 → 400 → 200 → 100 → 50 → 25)."
  ),

  h3("1.2.2 Era 5+ — inflation replaces halving"),
  p(
    "After the fifth halving (block 5,270,400), further halving would drive subsidies below sustainable mining incentives. SpaceXpanse instead switches to a closed-form inflation curve: each era mints additional STONE proportional to (1.02956^era − 1.02956^(era−1)) against a calibrated base supply constant, then divides that tranche across the 1,054,080 blocks in the era."
  ),
  p(
    "With the reference formula in Bloodstone Core, era 5 begins near 52.95 STONE per block — a deliberate step up from the 6.25 STONE era-4 floor. This is not a bug: it marks the transition from deflationary halving to a long inflation phase designed to keep PoW rewards viable for decades while total supply growth slows toward an asymptotic cap (SpaceXpanse documentation describes ~3% annual inflation for ~59 years after the fifth halving, targeting roughly 2.5× supply growth across the inflation phase on the legacy 800 ROD schedule)."
  ),
  table(
    ["Era", "Block height (start)", "Subsidy per block (reference formula)", "Phase"],
    [
      ["5", "5,270,400", "~52.95 STONE", "Inflation"],
      ["10", "10,540,800", "~61.25 STONE", "Inflation"],
      ["20", "21,081,600", "~82.5 STONE", "Inflation"],
      ["40", "42,163,200", "~149 STONE", "Inflation"],
      ["60", "63,244,800", "~269 STONE", "Inflation"],
    ],
    [900, 2200, 3260, 3000]
  ),
  p(
    "Subsidy per block continues rising slowly era-over-era (~2.956% growth in total era issuance) until halving index 64, when GetBlockSubsidy() returns zero and PoW issuance ends. Cumulative PoW issuance from eras 0–69 is on the order of 8.8 billion STONE under the reference formula, before adding the ~200 million STONE genesis premine."
  ),

  h3("1.2.3 What later years mean for miners"),
  p(
    "Years 0–11 (eras 0–4): Predictable halving cliffs. Pool revenue per block falls by half each era unless hashrate and price compensate. Cross-algo subsidies and mobile participation become more important as per-block STONE drops."
  ),
  p(
    "Years 11–180 (eras 5–64, inflation phase): Block subsidies rise gradually rather than fall. Mining remains economically meaningful long after Bitcoin-style halving would have driven rewards to dust. Fee revenue and name-value activity on-chain matter more over time, but the protocol still funds security through coinbase issuance."
  ),
  p(
    "After era 64: PoW subsidy goes to zero. Miners would rely entirely on transaction fees and any off-chain incentive layers (staking yield, pool operator policies). This tail is far in the future — at ~80 s/block, era 64 begins near block 67.5 million, roughly 170+ years from the 2026 relaunch."
  ),
  p(
    "Pool operators should update BLOODSTONE_BLOCK_REWARD_STONE when eras change, or preferably read subsidy from the confirmed block at payout time, so dashboard “next block” estimates stay accurate across halvings."
  ),

  h2("1.3 Pool accounting vs on-chain subsidy"),
  p(
    "Pool accounting assumes a nominal block reward of 100 STONE per found block during era 0 unless the chain reports a different value at payout time. This figure is configurable via BLOODSTONE_BLOCK_REWARD_STONE and is read when the pool closes a round and credits miner balances."
  ),
  p(
    "Actual on-chain issuance follows GetBlockSubsidy(height). Miners should treat dashboard estimates as projections based on the configured default until a block is confirmed and reconciled against the coinbase output."
  ),

  h2("1.4 Reward Waterfall"),
  p("Every pool-found block is split in a fixed order before proportional distribution:"),
  table(
    ["Step", "Recipient", "Default", "Notes"],
    [
      ["1", "Block finder", "5 STONE", "Off-the-top bonus to the worker that submitted the winning share"],
      ["2", "Staking rewards pool", "1% of gross", "Funded to the staking deposit wallet each block"],
      ["3", "Pool operator", "1% of remainder", "Sustainability fee on what is left after steps 1–2"],
      ["4", "Miner pool", "Balance", "Split across open rounds per distribution rules below"],
    ],
    [1200, 2200, 1800, 4160]
  ),
  p(
    "Example on a 100 STONE block: 5 STONE finder bonus, 1 STONE staking contribution, 0.94 STONE pool fee (1% of 94), and 93.06 STONE entering the miner distribution pipeline."
  ),

  h1("2. Unified Pool Architecture"),
  h2("2.1 One balance, four algorithms"),
  p(
    "Miners connect to a single Bloodstone pool namespace. Accepted shares accrue weight in algorithm-specific open rounds, but pending balances and payouts are tracked per payout address across neoscrypt-xaya, yespower, rod_neoscrypt, and sha256d."
  ),
  table(
    ["Algorithm", "Typical hardware", "Stratum role"],
    [
      ["Neoscrypt (STONE)", "CPU, GPU, browser", "Primary CPU-friendly PoW for STONE"],
      ["Yespower", "CPU, GPU, browser", "Memory-hard diversification"],
      ["ROD Neoscrypt", "CPU, GPU", "Auxiliary SpaceXpanse/ROD chain"],
      ["SHA256d", "ASIC (Bitaxe, Luck, etc.)", "High-throughput merge-mining capable PoW"],
    ],
    [2200, 2800, 4360]
  ),

  h2("2.2 Share weight and decay"),
  p(
    "Shares carry difficulty-derived weight. Recent shares count more than stale ones through time decay (BLOODSTONE_SHARE_DECAY_SEC). Open-round weight determines each miner’s percentage of the next payout for that algorithm."
  ),
  bullet(
    "bullets",
    "Per-address weight cap: no single payout address may hold more than 75% of an open round’s weight; excess is redistributed to other miners on that algorithm."
  ),
  bullet(
    "bullets",
    "Algorithm balance multipliers: the pool can boost under-used algorithms so CPU rounds are not permanently dominated by ASIC hashrate on SHA256d."
  ),

  h1("3. Cross-Algorithm Subsidy"),
  h2("3.1 Default mode (cross_subsidy)"),
  p(
    "When any algorithm finds a block, 65% of the miner-pool slice goes to that algorithm’s open round, and 35% is split across the other pool algorithms proportional to their open-round weight. This is the default cross_subsidy mode (BLOODSTONE_CROSS_ALGO_STONE_SHARE = 0.35)."
  ),
  p(
    "Economic intent: a SHA256d block does not pay only ASIC miners — a substantial minority flows to CPU and browser miners on neoscrypt and yespower. Conversely, when CPU algorithms find blocks, ASIC participants on SHA256d receive a cross-algo slice, keeping large miners invested in the unified pool."
  ),

  h2("3.2 Even-share mode (conditional)"),
  p(
    "After a SHA256d block, the pool may arm a rebalance that boosts CPU algorithm multipliers until combined neoscrypt + yespower open weight reaches 75% of the SHA256d round weight. When that target is met, even-share mode can activate: each of the three STONE pool algorithms receives one-third of distributable STONE from subsequent blocks until CPU weight falls below 30% of SHA256 again."
  ),
  p(
    "This is a deliberate macro-economic stabilizer — it temporarily increases CPU revenue share when ASIC weight would otherwise starve browser and phone mining."
  ),

  h1("4. SHA256d / ASIC Economics"),
  h2("4.1 Stratum V1 vs SV2"),
  p(
    "ASIC miners should use Stratum V1 on port 3429 for shares that can yield on-chain block finder credit. Stratum V2 (port 3425) is useful for work-rate telemetry but submits pool-difficulty solutions that do not substitute for network block targets."
  ),

  h2("4.2 Mobile / browser cross-subsidy from ASIC blocks"),
  p(
    "A portion of STONE paid from SHA256 subsidy and cross-algo payout paths is allocated to phone and browser miners (Android app, web miner). The dashboard tracks total STONE shared with mobile participants from ASIC-driven payout algorithms."
  ),
  p(
    "At least 90% of the CPU→SHA256 cross-subsidy path can be credited to ASIC-class miners where configured (BLOODSTONE_SHA256_CROSS_ASIC_MIN_FRAC), with the remainder supporting mobile presence — aligning pocket devices with datacenter-scale hashrate without merging their wallets."
  ),

  h2("4.3 Operator subsidies and reconciliation"),
  p(
    "Historical SHA256 blocks that were closed under even-share (33% each) rather than the intended subsidy (75% primary / 25% cross) can be reconciled via one-time back-credit scripts. This preserves economic promises when payout mode flags were wrong at block time."
  ),

  h1("5. Payouts and Balances"),
  h2("5.1 Proportional settlement"),
  p(
    "When a round closes, each miner’s pending_stone increases by: (open-round weight share) × (algorithm’s fraction of distributable STONE). Payouts batch to on-chain transactions when balances exceed the configured minimum (default 0.01 STONE) and respect chunk limits for RPC safety."
  ),

  h2("5.2 Finder bonus"),
  p(
    "The block finder receives the finder bonus in addition to their proportional round share. This incentivizes low-latency, valid share submission on the algorithm that actually found the block — especially important for ASIC operators competing on SHA256d."
  ),

  h2("5.3 Staking pool contribution"),
  p(
    "Each block routes 1% of gross reward to the staking rewards pool wallet before fees. This links PoW issuance to long-term staking infrastructure: validators and stakers benefit from continued mining activity even when they are not hashing directly."
  ),

  h1("6. Testnet Faucet and Onboarding"),
  p(
    "The Bloodstone faucet distributes 25 STONE per successful claim to web-wallet users for testnet onboarding (wallet setup, mining experiments, donations back to the faucet). Claims enforce:"
  ),
  bullet("bullets", "Per-address cooldown: random 3–6 hours between claims"),
  bullet("bullets", "Per-IP cooldown: same window, preventing rapid repeat claims"),
  bullet("bullets", "One wallet account per IP: an IP address is permanently bound to the first account that claimed from it"),
  p(
    "The faucet is funded by community donations. Economically it is a sink-to-source loop for new users, not inflationary issuance — it redistributes STONE already held in the faucet wallet."
  ),

  h1("7. Operator Revenue and Sustainability"),
  p(
    "The pool operator fee defaults to 1% of STONE remaining after finder bonus and staking contribution. This fee funds VPS infrastructure, stratum bridges, dashboard services, chain mesh coordination, and payout transaction costs."
  ),
  p(
    "Operator revenue scales linearly with blocks found; it does not depend on withholding miner payouts. Fee percentage is capped at 50% in code as a safety bound; live configuration uses the nominal 1% default."
  ),

  h1("8. Incentive Alignment Over Time"),
  h3("8.1 Short term (days–weeks)"),
  bullet("numbers", "Miners optimize for open-round weight on their best hardware."),
  bullet("numbers", "Cross-algo subsidy immediately shares each block across algorithms."),
  bullet("numbers", "Finder bonus rewards the lucky/share-tight worker that found the block."),

  h3("8.2 Medium term (months)"),
  bullet("numbers", "Algorithm multipliers rebalance when SHA256d dominates share weight."),
  bullet("numbers", "Mobile subsidy paths keep phones economically relevant beside ASIC farms."),
  bullet("numbers", "Staking pool accumulation creates a parallel yield route for holders."),

  h3("8.3 Long term (years)"),
  bullet("numbers", "Halving eras 1–4 reduce per-block STONE ~50% each time; inflation eras 5+ gradually restore issuance for multi-decade mining."),
  bullet("numbers", "Decentralized nodes, mesh storage, and LAN miners reduce payout centralization risk."),
  bullet("numbers", "Weight caps prevent single-address pool capture as farms scale."),
  bullet("numbers", "Documented reconciliation tools preserve trust when payout modes change."),
  bullet("numbers", "After PoW subsidy exhaustion (halving index ≥ 64), fee markets and staking become the primary holder incentives."),

  h1("9. Parameters Reference"),
  table(
    ["Parameter", "Default", "Purpose"],
    [
      ["nSubsidyHalvingInterval", "1,054,080 blocks", "On-chain era length (~2.7 yr at 80 s/block)"],
      ["initialSubsidy (relaunch)", "100 STONE", "Era-0 PoW reward observed on Bloodstone mainnet"],
      ["Inflation factor", "1.02956 / era", "After 5th halving (reference consensus)"],
      ["BLOODSTONE_BLOCK_REWARD_STONE", "100", "Pool default during era 0"],
      ["BLOODSTONE_BLOCK_FINDER_BONUS_STONE", "5", "Off-top finder reward"],
      ["BLOODSTONE_STAKING_BLOCK_PCT", "1%", "Gross reward to staking pool"],
      ["BLOODSTONE_POOL_FEE_PCT", "1%", "Operator fee after top slices"],
      ["BLOODSTONE_CROSS_ALGO_STONE_SHARE", "35%", "Fraction to non-finding algos"],
      ["BLOODSTONE_SHA256_CROSS_ALGO_SHARE_RATIO", "75%", "CPU weight target vs SHA256"],
      ["BLOODSTONE_MINER_WEIGHT_CAP", "75%", "Max open-round share per address"],
      ["BLOODSTONE_SHA256_CROSS_ASIC_MIN_FRAC", "90%", "ASIC share of cross-subsidy slice"],
      ["Faucet claim_amount", "25 STONE", "Per-claim testnet distribution"],
    ],
    [3600, 1800, 3960]
  ),

  h1("10. Risks and Limitations"),
  bullet("bullets", "Dashboard hashrate for LAN ASICs requires a home-network forwarder; stratum-only estimates under-report terahash."),
  bullet("bullets", "Cross-algo subsidies assume honest share accounting; decay and weight caps mitigate but do not eliminate gaming."),
  bullet("bullets", "Staking contributions require the staking wallet and RPC to be online at payout time."),
  bullet("bullets", "Parameter changes (fees, subsidy ratios) require operator configuration discipline and miner communication."),
  bullet("bullets", "Halving transitions change gross pool revenue; cross-algo rules do not automatically compensate for era cliffs."),
  bullet("bullets", "Inflation-era subsidies in consensus use SpaceXpanse calibration constants — verify on-chain coinbase at era boundaries after era 4."),

  h1("11. Related Documents"),
  linkPara(
    "Bloodstone Decentralized Network white paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Decentralized-Network-White-Paper.docx"
  ),
  linkPara(
    "Chain Mesh Storage white paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  linkPara("Mining dashboard", "https://bloodstonewallet.mytunnel.org/mining/"),
  linkPara("Rich list", "https://bloodstonewallet.mytunnel.org/#rich-list"),

  new Paragraph({ children: [new PageBreak()] }),
  h1("Summary"),
  p(
    "Bloodstone’s economics are built around a single unified pool that treats CPU, browser, mobile, and ASIC hashrate as complementary inputs to one STONE issuance stream governed by a transparent halving-and-inflation schedule. Block rewards flow through a clear waterfall, then split across algorithms by design — not by accident — so that adding a Gamma on SHA256d or a phone on yespower changes everyone’s expected payout. Early years halve issuance every ~1.05 million blocks; later years inflate slowly to keep PoW viable for decades. The model is parameter-driven, auditable in open-source core and pool code, and intended to grow more decentralized as mesh nodes, LAN forwarders, and home miners join the network."
  ),
];

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 28, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 180, after: 180 }, outlineLevel: 1 },
      },
      {
        id: "Heading3",
        name: "Heading 3",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 26, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 140, after: 140 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
      {
        reference: "numbers",
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: "%1.",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              children: [
                new TextRun({
                  text: "Bloodstone Economic Model — White Paper",
                  size: 18,
                  color: "666666",
                }),
              ],
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ text: "Page ", size: 18 }),
                new TextRun({ children: [PageNumber.CURRENT], size: 18 }),
              ],
            }),
          ],
        }),
      },
      children,
    },
  ],
});

const outDocx = "/root/bloodstone-docs/Bloodstone-Economic-Model-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outDocx, buffer);
  console.log("Wrote", outDocx, buffer.length, "bytes");
});