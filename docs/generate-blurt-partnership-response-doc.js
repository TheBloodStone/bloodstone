#!/usr/bin/env node
/** Bloodstone Blurt Partnership Response — MD companion DOCX generator. */
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

const COORDINATOR = "https://bloodstonewallet.mytunnel.org";
const RICH_LIST = `${COORDINATOR}/#rich-list`;
const API_URL = `${COORDINATOR}/mining/api/pool/subsidy-schedule`;

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
function numbered(ref, text) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80 },
    children: [new TextRun(text)],
  });
}
function mono(text) {
  return new Paragraph({
    spacing: { after: 100 },
    children: [new TextRun({ text, font: "Courier New", size: 20 })],
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
  const widths = colWidths || headers.map(() => Math.floor(tableWidth / headers.length));
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
    children: [
      new TextRun({
        text: "Bloodstone Response to Blurt",
        size: 52,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "Tokenomics, Storage Economics & Multi-Algo Security",
        size: 28,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · v1.0 · Audience: Blurt Core team",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "Thank you for laying this out clearly. We take these concerns seriously — especially coming from a team that deliberately reduced its own holdings from ~15% to ~7% because you believe broad ownership matters. That is the standard we want partners to hold us to."
  ),
  p(
    "This document is our current, honest position: what is already designed and deployed, what changes the dilution math materially from your model, and what we have not yet published but should."
  ),

  h1("On Concentration and Your Dilution Math"),
  p(
    "Your concern is valid. At block ~9,687, on-chain supply is ~201M STONE, and the top three addresses hold roughly 30% + 25% + 22% ≈ 77% of circulating supply. If Blurt paid for storage in STONE, you would be buying into a market where a small number of wallets dominate float today."
  ),

  h2("Two Clarifications on the Dilution Timeline"),
  h3("1. The genesis treasury is a single, public address."),
  p(
    "The June 2026 relaunch allocated 199,999,998 STONE in one coinbase output to:"
  ),
  mono("SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N"),
  p(
    "This is documented in our Development Journey and Economic Model white papers. We have not yet published a formal wallet-by-wallet disclosure tying rich-list entries to named entities — that is a gap we intend to close."
  ),

  h3("2. Your “100 STONE/block for 4+ years” model understates near-term PoW issuance."),
  p(
    "Mainnet is still in era 0 at 100 STONE/block, but a scheduled consensus upgrade at block 12,000 raises the era-0 base to 1,000 STONE for the remainder of the era (blocks 12,000–1,054,079). Era 0 PoW issuance alone is projected at ~1.04 billion STONE — versus ~200M from the premine."
  ),
  p(
    "Even if treasury wallets did not move, premine share of total supply after era 0 would fall toward ~16%, not ~50%+, before the first halving."
  ),
  p(
    "Your directional concern (concentration matters for utility-token economics) is right; the timeline to meaningful dilution is shorter than a flat 100 STONE/block model suggests — provided PoW participation continues and treasury is not simply re-accumulating mined coins."
  ),
  p(
    "We also hear the deeper point: dilution from mining ≠ decentralization of control if the same entities capture PoW payouts or treasury never disburses. Issuance alone is not enough."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("1. Treasury Strategy (~200M STONE)"),
  h2("What Exists Today"),
  p(
    "One genesis treasury output (~200M STONE). There is no on-chain automated vesting contract yet. Disbursement is operational, not trustlessly encoded."
  ),

  h2("Planned Allocation Buckets (Working Framework)"),
  table(
    ["Bucket", "Purpose"],
    [
      ["Infrastructure & core development", "Node, pool, mesh coordinator, Android/desktop miners, security maintenance"],
      ["Ecosystem grants", "Third-party builders, LAN/mesh operators, storage replicators"],
      [
        "Partner programs",
        "Structured allocations for integrations (e.g. Blurt bulk storage quotas) paid from treasury or fresh issuance — not requiring partners to buy float from top holders",
      ],
      ["Liquidity / market making", "As needed when CEX/DEX routes exist"],
      ["Community distribution", "Faucets, onboarding, mesh replication rebates, mining participation"],
    ],
    [3200, 6160]
  ),
  p(
    "We agree a published treasury policy (addresses, buckets, and disbursement cadence) is a prerequisite for a serious storage partnership. We will prepare that as a short addendum to the Economic Model white paper."
  ),

  h1("2. Decentralization Roadmap"),
  h2("Mechanisms Already in Code or Operation"),
  bullet("bullets", "PoW issuance — multi-algorithm mining open to phones, browsers, CPUs, and ASICs via a unified pool"),
  bullet("bullets", "Per-address pool weight cap (75%) — no single payout address can hold more than three-quarters of an open round"),
  bullet("bullets", "Cross-algo subsidies (35%) — a block found on one algorithm shares STONE with miners on the others"),
  bullet("bullets", "Staking pool slice (1% of every block) — routes value to long-term stakers, not only active hashers"),
  bullet("bullets", "Mesh / LAN participation — storage replication and local full nodes spread infrastructure beyond our VPS"),

  h2("What We Are Committing to Publish"),
  bullet("bullets", "Treasury wallet labeling (team / foundation / operational / unallocated)"),
  bullet("bullets", "Target ranges for treasury disbursement over the next 12–24 months"),
  bullet(
    "bullets",
    "Partner-facing structure so Blurt (or any integrator) can prepay storage in STONE via a designated outpost account without sourcing large blocks from the rich list"
  ),
  p(
    "Your path from 15% → 7% is a useful benchmark. We are not there yet on transparency or demonstrated outflow, and we do not want to pretend otherwise."
  ),

  h1("3. Storage Economics — Avoiding “Captive Token” Dynamics"),
  p(
    "If Blurt integrates STONE for mesh storage, we do not want you buying float exclusively from concentrated holders."
  ),

  h2("Proposed Rails (Blurt Mesh Storage Partnership Draft)"),
  bullet(
    "bullets",
    "Bulk partner quota — Blurt pays a monthly STONE amount (spot-equivalent to your current ~€22.80 / 1.2 TB benchmark) into a Bloodstone outpost; users receive quota without hitting the open market"
  ),
  bullet(
    "bullets",
    "BLURT → STONE memo rail — storage:<STONE_ADDRESS>:<bytes> so Blurt can fund storage without OTC purchases from whales"
  ),
  bullet("bullets", "Mesh replication rebates — STONE flows to peers who store chunks, not only to the coordinator"),

  h2("Important Honesty"),
  p(
    "Per-GB storage billing in STONE is proposed, not fully live in code today. Mesh coordination is operational; automated quota debits and peer replication incentives are on the roadmap. A partnership would help define those rules with a real customer — but we will not represent them as already trustless on-chain."
  ),

  h2("Structural Protections for Blurt"),
  bullet("bullets", "Contracted bulk rate, not spot market dependency"),
  bullet("bullets", "Option to denominate invoices in BLURT with STONE credited at payment time"),
  bullet("bullets", "No requirement to accumulate STONE from the top three wallets"),

  new Paragraph({ children: [new PageBreak()] }),

  h1("4. 51% Attack Surface — Consensus vs Pool Economics"),
  p("This distinction matters: pool payout rules ≠ consensus security."),

  h2("What Bloodstone Inherits (SpaceXpanse / Xaya Multi-Algo Consensus)"),
  p(
    "This is not a DigiByte geometric-mean clone. It is the Xaya triple-algo weighting scheme:"
  ),
  table(
    ["Layer", "Mechanism"],
    [
      [
        "Per-algorithm difficulty",
        "Dark Gravity retargeting runs on separate block streams per algo (GetNextWorkRequired only considers ancestors with the same PowAlgo)",
      ],
      [
        "Algorithm work weighting",
        "powAlgoLog2Weight: SHA256d = 6, Neoscrypt = 10, Yespower = 22 — SHA256d work is deliberately down-weighted in cumulative chain work vs CPU algorithms",
      ],
      [
        "Cross-algo timing normalization",
        "AvgTargetSpacing and GetBlockProofEquivalentTime combine contributions from all three consensus algos (~270s target per algo, ~80–90s between blocks overall)",
      ],
      [
        "Longest-work chain rule",
        "Best chain is selected on weighted nChainWork, not raw SHA256 hashrate alone",
      ],
    ],
    [2800, 6560]
  ),
  p(
    "We do not rely solely on the assumption that no single algorithm can be dominated. SHA256d dominance does not translate 1:1 into chain-work dominance the way it would on a single-algo SHA256 chain."
  ),

  h2("What We Do Not Have Today"),
  p(
    "DigiByte-style geometric mean difficulty adjustment as a separate, named layer. The Economic white paper’s cross-algo payout subsidies and even-share rebalancing are pool accounting — they affect who gets paid, not which fork wins."
  ),

  h2("SHA256d / Rental-Hashrate Risk — Candid Assessment"),
  p(
    "You are right that rented SHA256 hashrate is cheaper per unit than attacking Bitcoin. Mitigations today:"
  ),
  bullet("bullets", "Down-weighted SHA256d chain work (consensus)"),
  bullet("bullets", "Independent per-algo difficulty floors/ceilings"),
  bullet("bullets", "Merge-mining (auxpow) path for SHA256 blocks"),
  bullet("bullets", "Pool monitoring and operator visibility"),

  h2("Roadmap Items We Are Open to Discussing"),
  bullet(
    "bullets",
    "Publishing a security appendix with worked examples (e.g. “X% SHA256d + Y% Neoscrypt required to outpace tip”)"
  ),
  bullet(
    "bullets",
    "Stricter anchoring if SHA256d share of chain work (not just pool weight) exceeds thresholds"
  ),
  bullet("bullets", "Incentivizing Neoscrypt/Yespower full-node share alongside ASIC LAN forwarding"),

  h2("Note on “Four Algorithms”"),
  p(
    "Consensus mainnet uses three PoW algorithms (SHA256d, Neoscrypt, Yespower). ROD Neoscrypt is a fourth pool lane for the auxiliary ROD chain — not a fourth independent consensus weight on Bloodstone mainnet."
  ),

  h1("5. Transparency"),
  table(
    ["Item", "Status"],
    [
      ["Genesis premine address", "Public — SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N"],
      ["Rich list", "Live — bloodstonewallet.mytunnel.org/#rich-list"],
      ["Top-wallet entity labels", "Not yet published — gap acknowledged"],
      ["Lock-up / vesting schedule", "Not on-chain — policy document in progress"],
      [
        "Halving / issuance schedule",
        "Published — Halving Schedule MD/DOCX + /mining/api/pool/subsidy-schedule",
      ],
    ],
    [3600, 5760]
  ),
  p(
    "We will publish a Treasury & Concentration Disclosure covering: known entities behind top addresses, intended use, and disbursement timeline."
  ),

  h1("Our Intent Back to Blurt"),
  p(
    "We are not asking you to accept concentration as permanent, or to trust pool cleverness instead of consensus review. We are saying:"
  ),
  numbered(
    "numbers",
    "Your economic concern is legitimate — and it matches concerns we have internally."
  ),
  numbered(
    "numbers",
    "The issuance curve is more dilutive than a flat 100 STONE model — but dilution alone is not decentralization."
  ),
  numbered(
    "numbers",
    "Consensus is stronger than “hope no algo dominates” — with explicit per-algo retargeting and SHA256d down-weighting — but it is not identical to DigiByte’s geometric mean, and rented-hashrate risk deserves continued attention."
  ),
  numbered(
    "numbers",
    "A storage partnership should be structured so Blurt is not a price-taker from three wallets."
  ),
  p(
    "We would welcome a follow-up call to walk through the consensus code paths (powdata.cpp, chain.cpp, pow.cpp) and to co-design treasury disbursement + Blurt bulk-storage rails so the economic foundation catches up to the technical one."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("References"),
  table(
    ["Document", "URL"],
    [
      ["Bloodstone Economic Model White Paper (July 2026)", `${COORDINATOR}/downloads/`],
      ["Bloodstone Halving Schedule", `${COORDINATOR}/downloads/Bloodstone-Halving-Schedule.md`],
      ["Blurt Mesh Storage Partnership draft", `${COORDINATOR}/downloads/`],
      ["Development Journey white paper", `${COORDINATOR}/downloads/`],
      ["Live rich list", RICH_LIST],
      ["Subsidy schedule API", API_URL],
    ],
    [4200, 5160]
  ),

  h2("Blurt’s Cited On-Chain Data"),
  bullet(
    "bullets",
    "Rich list at block ~9,687: supply ~200,968,698 STONE; top addresses ~30.27%, 25.43%, 22.39%"
  ),
  bullet(
    "bullets",
    "Economic Model white paper: genesis premine 199,999,998 STONE; 100 STONE/block era-0 (pre–block 12,000 fork)"
  ),
  bullet(
    "bullets",
    "Network white paper: four pool algorithms; three consensus PoW algorithms on mainnet"
  ),

  linkPara("Live rich list", RICH_LIST),
  linkPara("Subsidy schedule API", API_URL),
  linkPara("Bloodstone Halving Schedule", `${COORDINATOR}/downloads/Bloodstone-Halving-Schedule.md`),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({
        text: "Bloodstone · July 2026 · For partnership discussion with Blurt Core",
        italics: true,
        size: 20,
      }),
    ],
  }),
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
                  text: "Bloodstone Response to Blurt — Tokenomics & Security",
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

const outPath =
  process.argv[2] || "/root/bloodstone-docs/Bloodstone-Blurt-Partnership-Response.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote " + outPath);
});