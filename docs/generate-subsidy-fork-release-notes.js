#!/usr/bin/env node
/** Bloodstone Core 0.7.0 subsidy fork — release notes (draft). */
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
function mono(text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text, font: "Courier New", size: 20 })],
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
    children: [
      new TextRun({
        text: "Bloodstone Core — Subsidy Schedule Fork Release Notes",
        size: 44,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [new TextRun({ text: "Draft · July 2026", size: 28, italics: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "Target release: Bloodstone Core 0.7.0 (consensus + pool alignment)",
        size: 24,
      }),
    ],
  }),

  h1("Summary"),
  p(
    "This release documents and hardens Bloodstone's proof-of-work issuance schedule: five halving eras followed by a long-run inflation phase. It aligns Bloodstone Core consensus with the live relaunch parameters (100 STONE era-0 reward) and fixes a monetary discontinuity at era 5 where legacy SpaceXpanse inflation math would otherwise jump the block subsidy from ~6.25 STONE to ~52.95 STONE despite Bloodstone's lower initial reward."
  ),
  p(
    "The unified mining pool already adapts in software (July 2026): payouts and dashboard estimates read the on-chain subsidy via getblockstats. This core release makes the chain match the intended Bloodstone economics for later years."
  ),

  h1("Why this fork matters"),
  table(
    ["Issue", "Without fix", "With 0.7.0"],
    [
      ["Era 0–4 halvings", "100 → 50 → 25 → 12.5 → 6.25 STONE", "Same (unchanged)"],
      ["Era 5 subsidy (block 5,270,400+)", "~52.95 STONE (800-ROD inflation curve)", "~6.62 STONE (scaled to 100 STONE base)"],
      ["Pool payout vs chain", "Pool reads chain; estimates could diverge at era 5", "Chain and pool projections align"],
      ["POST_ICO bootstrap", "Legacy 55,560-block × 1 STONE phase (ROD)", "Full schedule from block 1 on relaunch chain"],
    ],
    [2200, 3580, 3580]
  ),
  p(
    "Recommendation: Deploy 0.7.0 to all full nodes and pool infrastructure before block 5,270,400 (halving era 5). Earlier deployment is safe and documents the relaunch parameters in official source.",
    { bold: true }
  ),

  h1("Consensus changes (hard fork at era 5 inflation)"),
  p(
    "These changes are in bloodstone-linux-build and require a network-wide node upgrade before era 5 takes effect. Eras 0–4 remain compatible with current mainnet behaviour."
  ),

  h2("1. Initial PoW subsidy — 100 STONE"),
  mono("// chainparams.cpp (mainnet)"),
  mono("consensus.initialSubsidy = 100 * COIN;"),
  p("Matches live relaunch coinbase outputs (verified at heights 1–8,000+)."),

  h2("2. Post-ICO fork height — block 1"),
  mono("// consensus/params.h — MainNetConsensus"),
  mono("case Fork::POST_ICO:"),
  mono("    return height >= 1;"),
  p("Bloodstone relaunch does not use the legacy 55,560-block × 1 STONE pre-ICO bootstrap."),

  h2("3. Scaled inflation after era 4"),
  mono("// validation.cpp — GetBlockSubsidy(), halvings > 4"),
  mono("if (consensusParams.initialSubsidy < 800 * COIN) {"),
  mono("    nSubsidy = nSubsidy * initialSubsidy / (800 * COIN);"),
  mono("}"),
  p(
    "Legacy SpaceXpanse formula still computes the inflation tranche, but issuance is scaled when initialSubsidy is below 800 ROD. For Bloodstone (100 STONE), scale factor = 0.125."
  ),
  p("Halving interval (unchanged): 1,054,080 blocks per era."),

  h1("Subsidy schedule reference (Bloodstone 0.7.0)"),
  p(
    "Approximate calendar dates assume ~80 s average block time (triple-algo mainnet, July 2026). Adjust if block times change."
  ),
  table(
    ["Era", "Start block", "Subsidy / block", "Phase", "Approx. year"],
    [
      ["0", "1", "100 STONE", "Halving", "2026"],
      ["1", "1,054,080", "50 STONE", "Halving", "~2029"],
      ["2", "2,108,160", "25 STONE", "Halving", "~2031"],
      ["3", "3,162,240", "12.5 STONE", "Halving", "~2034"],
      ["4", "4,216,320", "6.25 STONE", "Halving", "~2037"],
      ["5", "5,270,400", "~6.62 STONE", "Inflation (scaled)", "~2039"],
      ["10", "10,540,800", "~7.66 STONE", "Inflation (scaled)", "~2053"],
    ],
    [700, 1800, 2200, 2200, 2460]
  ),
  p(
    "Eras 5–63 continue with ~2.956% growth per era (factor 1.02956), scaled for the 100 STONE base. Era 64+: subsidy 0 (PoW issuance ends)."
  ),
  p("Next halving (era 1): block 1,054,080.", { bold: true }),

  h1("Pool changes (already deployed — no node upgrade required)"),
  table(
    ["Component", "Change"],
    [
      ["pool_block_subsidy.py", "Mirrors GetBlockSubsidy(); reads live subsidy via RPC/getblockstats"],
      ["pool_db.distribute_block()", "Uses on-chain subsidy at block height when crediting miners"],
      ["Dashboard", "subsidy_schedule + halving era on next-block estimates"],
      ["API", "GET /mining/api/pool/subsidy-schedule"],
      ["Config", "service-overrides.conf: BLOODSTONE_INITIAL_SUBSIDY_STONE=100, BLOODSTONE_INFLATION_SCALE=0.125"],
    ],
    [3200, 6160]
  ),
  p(
    "Pool payouts today follow whatever the chain pays. The inflation-scale env var affects projections only until 0.7.0 is active on-chain at era 5."
  ),

  h1("Upgrade instructions"),
  h2("Full node operators"),
  bullet("numbers", "Build or install Bloodstone Core 0.7.0 (bloodstoned, bloodstone-cli, bloodstone-qt)."),
  bullet("numbers", "Restart the daemon on pool VPS, home nodes, and explorers."),
  bullet("numbers", "Confirm subsidy at tip:"),
  mono("bloodstone-cli getblockstats $(bloodstone-cli getblockcount) '[\"subsidy\"]'"),
  p('Expect "subsidy": 10000000000 (100 STONE in satoshis) during era 0.'),
  bullet("numbers", "Confirm pool API:"),
  mono(
    'curl -sS "https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule" | python3 -m json.tool'
  ),

  h2("Miners"),
  bullet("bullets", "No stratum or wallet changes required for eras 0–4."),
  bullet("bullets", "Dashboard next-block STONE estimates will track halvings automatically."),
  bullet("bullets", "After era 1, expect per-block gross pool revenue to drop ~50% unless price/hashrate compensates."),

  h2("Pool operator"),
  bullet("bullets", "Remove or update BLOODSTONE_BLOCK_REWARD_STONE if set manually — it is now a fallback only."),
  bullet("bullets", "After 0.7.0 is network-wide at era 5, projected_reward_stone and chain subsidy should match."),

  h1("Compatibility and risks"),
  bullet("bullets", "Eras 0–4: Compatible with Bloodstone relaunch mainnet (100 STONE reward). Upgrade is documentation + forward-fix for era 5."),
  bullet(
    "bullets",
    "Era 5+: Hard fork if any miners still run pre-0.7.0 inflation (unscaled). A chain split at block 5,270,400 would produce different coinbase amounts; pools credit blocks from the chain they validate."
  ),
  bullet("bullets", "Do not mix old inflation nodes with 0.7.0 nodes past era 4 — coordinate upgrade via pool announcements and downloads page."),
  bullet("bullets", "Reorgs: Recent anchors and pool settlements should wait for standard confirmations across halving boundaries."),

  h1("Files changed (reference)"),
  table(
    ["Area", "Path"],
    [
      ["Subsidy logic", "bloodstone-linux-build/src/validation.cpp"],
      ["Mainnet params", "bloodstone-linux-build/src/chainparams.cpp"],
      ["Fork heights", "bloodstone-linux-build/src/consensus/params.h"],
      ["Pool resolver", "/root/pool_block_subsidy.py"],
      ["Pool payouts", "/root/pool_db.py"],
      ["Pool API", "bloodstone-miner-web/app.py"],
      ["Economic white paper", "bloodstone-docs/generate-economic-whitepaper.js (v1.1)"],
    ],
    [2800, 6560]
  ),

  h1("Checklist before era 5 (block 5,270,400)"),
  bullet("bullets", "Bloodstone Core 0.7.0 binaries on downloads page"),
  bullet("bullets", "Pool VPS and stratum services on 0.7.0"),
  bullet("bullets", "Public announcement (Discord / portal / mining dashboard banner)"),
  bullet("bullets", "Verify subsidy_stone_chain ≈ subsidy_stone_projected at era 4→5 boundary on testnet or regtest"),
  bullet("bullets", "Update BLOODSTONE_BLOCK_REWARD_STONE env only if RPC unavailable (emergency fallback)"),

  h1("Related documentation"),
  linkPara(
    "Bloodstone Economic Model White Paper — §1.2 Halving schedule",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Economic-Model-White-Paper.docx"
  ),
  linkPara("Mining dashboard", "https://bloodstonewallet.mytunnel.org/mining/"),
  p(
    "Live schedule API: https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule"
  ),

  h1("Draft status"),
  p("This document is a draft for operator review. Final release should include:"),
  bullet("bullets", "Exact build version string and git tag (e.g. v0.7.0)"),
  bullet("bullets", "SHA256 checksums for bloodstoned / bloodstone-qt builds"),
  bullet("bullets", "Confirmed testnet regression height for era-4→5 transition"),
  bullet("bullets", "Official activation announcement date"),
  new Paragraph({
    spacing: { before: 200, after: 160 },
    children: [
      new TextRun({
        text: "Questions: pool operator via mining dashboard or Bloodstone portal support.",
        italics: true,
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
                  text: "Bloodstone Core 0.7.0 — Subsidy Fork Release Notes (draft)",
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

const outDocx = "/root/bloodstone-docs/Bloodstone-Subsidy-Fork-Release-Notes.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outDocx, buffer);
  console.log("Wrote", outDocx, buffer.length, "bytes");
});