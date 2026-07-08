#!/usr/bin/env node
/** Bloodstone Halving Schedule — MD companion DOCX generator. */
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
    children: [new TextRun({ text: "Bloodstone Halving Schedule", size: 52, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "STONE Proof-of-Work Issuance — Halving Eras, Inflation Phase, and Pool Alignment",
        size: 28,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [new TextRun({ text: "July 2026 · v1.0 · bloodstonewallet.mytunnel.org", size: 24, italics: true })],
  }),

  h1("Executive Summary"),
  p(
    "Bloodstone proof-of-work issuance follows a two-phase monetary schedule inherited from SpaceXpanse ROD consensus: five halving eras, then a long-run inflation phase (~2.956% growth per era), before PoW subsidies end at era 64."
  ),
  p(
    "Bloodstone relaunched in June 2026 with a 100 STONE era-0 reward. A scheduled upgrade at block 12,000 raises the subsidy base to 1,000 STONE for all subsequent halving math. As of July 2026 (tip height ~9,626), the network is still in era 0 at 100 STONE per block."
  ),
  p(
    "This document breaks down halving index math, the 1,000 STONE fork, era-by-era subsidy tables, inflation scaling, cumulative PoW supply, and how the unified mining pool aligns payouts with on-chain rewards."
  ),

  h1("1. How the Halving Index Works"),
  h2("1.1 Consensus constants"),
  table(
    ["Constant", "Value", "Meaning"],
    [
      ["nSubsidyHalvingInterval", "1,054,080", "Blocks per era (~2.7 years at ~80 s block time)"],
      ["initialSubsidy", "100 / 1,000 STONE", "Pre- and post-fork era-0 base"],
      ["Inflation factor", "1.02956", "~2.956% per era after era 4"],
      ["Inflation base coins", "1,833,823,998", "Legacy ROD inflation curve anchor"],
      ["Genesis premine", "199,999,998 STONE", "One-time treasury (not PoW)"],
    ],
    [2800, 1800, 4760]
  ),
  p("Halving index (era) is computed as:"),
  mono("era = floor(blockHeight / 1,054,080)"),

  h2("1.2 Halving phase (eras 0–4)"),
  p("For halving indices 0 through 4, the subsidy halves each era:"),
  mono("subsidy = effectiveInitialSubsidy >> era"),
  p(
    "effectiveInitialSubsidy is 100 STONE for heights 1–11,999 and 1,000 STONE for heights ≥ 12,000 (the scheduled 1,000 STONE fork)."
  ),

  h2("1.3 Inflation phase (eras 5–63)"),
  p(
    "From era 5 onward, the reward is no longer halved. Each era mints a calculated inflation tranche spread evenly across 1,054,080 blocks. When initial subsidy differs from legacy 800 ROD, issuance is scaled:"
  ),
  mono("scale = effectiveInitialSubsidy / 800"),
  mono("subsidy = (inflationTranche / 1,054,080) × scale"),
  p("For the 1,000 STONE post-fork base, scale = 1.25. Era 64+: subsidy = 0 (PoW issuance ends)."),

  new Paragraph({ children: [new PageBreak()] }),

  h1("2. 1,000 STONE Fork at Block 12,000"),
  table(
    ["Item", "Detail"],
    [
      ["Activation height", "12,000"],
      ["Pre-fork subsidy", "100 STONE per block (heights 1–11,999)"],
      ["Post-fork subsidy", "1,000 STONE per block (heights ≥ 12,000, era 0)"],
      ["Compatibility", "All pre-fork blocks remain valid; no genesis change"],
      ["Halving math", "Eras 1–4 halve from the 1,000 STONE base"],
    ],
    [3200, 6160]
  ),

  h2("2.1 Era 0 minting split"),
  table(
    ["Segment", "Blocks", "Rate", "STONE minted"],
    [
      ["Pre-fork", "1 – 11,999", "100 STONE", "1,199,900"],
      ["Post-fork", "12,000 – 1,054,079", "1,000 STONE", "1,042,080,000"],
      ["Era 0 total", "1,054,080 PoW blocks", "—", "~1.043 billion STONE"],
    ],
    [2200, 2000, 2000, 3160]
  ),

  h1("3. Halving Schedule — Eras 0–4"),
  p(
    "Approximate calendar years assume ~80 s mean block time from the June 2026 genesis. Era 0 uses 100 STONE until block 12,000, then 1,000 STONE for the remainder of the era."
  ),
  table(
    ["Era", "Start block", "Subsidy / block", "Phase", "STONE / era", "Approx. year"],
    [
      ["0", "1", "100 → 1,000", "Halving", "~1.043 B", "2026"],
      ["1", "1,054,080", "500", "Halving", "~528 M", "~2029"],
      ["2", "2,108,160", "250", "Halving", "~265 M", "~2031"],
      ["3", "3,162,240", "125", "Halving", "~132 M", "~2034"],
      ["4", "4,216,320", "62.5", "Halving", "~66 M", "~2037"],
    ],
    [700, 1600, 1500, 1100, 1400, 1060]
  ),

  h2("3.1 Milestones from current tip (~9,626)"),
  table(
    ["Event", "Block height", "Blocks remaining"],
    [
      ["1,000 STONE fork", "12,000", "~2,374"],
      ["Era 1 halving (500 STONE)", "1,054,080", "~1,044,454"],
      ["Era 5 inflation begins", "5,270,400", "~5,260,774"],
    ],
    [3600, 2800, 2960]
  ),

  h1("4. Inflation Phase — Eras 5+"),
  p(
    "At block 5,270,400 (era 5), halving stops and inflation begins. With the 1,000 STONE base and scale factor 1.25, projected subsidies are:"
  ),
  table(
    ["Era", "Start block", "Subsidy / block", "STONE / era", "Approx. year"],
    [
      ["5", "5,270,400", "~66.19", "~70 M", "~2039"],
      ["6", "6,324,480", "~68.14", "~72 M", "~2042"],
      ["7", "7,378,560", "~70.15", "~74 M", "~2045"],
      ["8", "8,432,640", "~72.23", "~76 M", "~2047"],
      ["9", "9,486,720", "~74.36", "~78 M", "~2050"],
      ["10", "10,540,800", "~76.56", "~81 M", "~2053"],
    ],
    [700, 2000, 1800, 1400, 1460]
  ),
  p("Eras 5–63 continue with ~2.956% growth per era. Era 64+ ends PoW issuance."),

  h2("4.1 Chain vs projected at era 5 (Bloodstone Core 0.7.0)"),
  p(
    "Without the 0.7.0 inflation-scaling fix, on-chain era-5 subsidy would follow the unscaled legacy ROD curve. Bloodstone Core 0.7.0 scales inflation when initialSubsidy < 800 STONE."
  ),
  table(
    ["Era", "On-chain (pre-0.7.0)", "Projected (0.7.0 scaled)"],
    [
      ["5", "~52.95 STONE", "~66.19 STONE"],
      ["6", "~54.51 STONE", "~68.14 STONE"],
      ["7", "~56.12 STONE", "~70.15 STONE"],
    ],
    [1200, 4080, 4080]
  ),
  p("Recommendation: Deploy Bloodstone Core 0.7.0 network-wide before block 5,270,400.", { bold: true }),

  new Paragraph({ children: [new PageBreak()] }),

  h1("5. Cumulative PoW Supply"),
  table(
    ["Source", "STONE"],
    [
      ["Genesis premine", "199,999,998"],
      ["Era 0 PoW (with 1,000 fork)", "~1,043,000,000"],
      ["Eras 1–4 PoW", "~991,000,000"],
      ["Eras 5–14 PoW (inflation)", "~799,000,000"],
      ["Cumulative after era 14", "~3.03 billion STONE"],
    ],
    [4680, 4680]
  ),
  p("PoW issuance dominates long-run supply growth; the premine is a fixed one-time allocation."),

  h1("6. Pool and Miner Alignment"),
  p("The unified mining pool reads the on-chain subsidy at each block height when crediting miners:"),
  bullet("bullets", "pool_block_subsidy.py — mirrors GetBlockSubsidy(); queries getblockstats via RPC"),
  bullet("bullets", "pool_db.distribute_block() — credits miners using actual coinbase subsidy + fees"),
  bullet("bullets", "Dashboard — halving era, next halving height, subsidy projections"),
  bullet("bullets", "API — GET /mining/api/pool/subsidy-schedule"),
  p(
    "Miner impact at halvings: gross per-block pool revenue drops ~50% at each era boundary (eras 0–4). Dashboard estimates update automatically; no stratum or wallet changes required."
  ),
  mono("bloodstone-cli getblockstats <height> '[\"subsidy\"]'"),
  mono(`curl -sS "${API_URL}" | python3 -m json.tool`),

  h1("7. Related Documentation"),
  linkPara(
    "Bloodstone Economic Model White Paper",
    `${COORDINATOR}/downloads/Bloodstone-Economic-Model-White-Paper.docx`
  ),
  linkPara(
    "Subsidy Fork Release Notes (0.7.0)",
    `${COORDINATOR}/downloads/Bloodstone-Subsidy-Fork-Release-Notes.docx`
  ),
  linkPara(
    "Subsidy Fork 1000 STONE White Paper",
    `${COORDINATOR}/downloads/Bloodstone-Subsidy-Fork-1000-White-Paper.docx`
  ),
  linkPara("Mining dashboard", `${COORDINATOR}/mining/`),
  linkPara("Live subsidy schedule API", API_URL),

  p("Document generated July 2026. Use the subsidy-schedule API for current tip height and rewards.", {
    italics: true,
    size: 20,
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
                  text: "Bloodstone Halving Schedule — STONE Issuance",
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
  process.argv[2] || "/root/bloodstone-docs/Bloodstone-Halving-Schedule.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote " + outPath);
});