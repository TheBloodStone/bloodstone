#!/usr/bin/env node
/** Bloodstone Treasury & Concentration Disclosure — DOCX generator. */
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
    children: [new TextRun({ text: "Bloodstone Treasury & Concentration Disclosure", size: 48, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [new TextRun({ text: "Addendum to the Economic Model White Paper", size: 28 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({ text: "July 2026 · v1.0 (draft) · Snapshot height 9,704", size: 24, italics: true }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "Bloodstone launched in June 2026 with a 199,999,998 STONE genesis premine paid to a single public address. That output was spent and re-split into project-operational wallets during the first weeks of mainnet. As of block 9,704, on-chain supply is ~200.97 million STONE (~970,400 STONE from PoW at 100 STONE/block; the remainder is treasury-derived)."
  ),
  p(
    "Concentration today is high. The top three addresses hold ~77.1% of supply; the top ten hold ~96.0%. This reflects project treasury custody that has not yet been disbursed at scale — not a broad independent holder base."
  ),
  p(
    "This addendum publishes genesis history, a labeled wallet registry, allocation buckets, a 12–24 month disbursement framework, and partner-facing rails. It does not claim on-chain vesting or trustless treasury contracts — those do not exist yet."
  ),

  h1("1. Scope and Methodology"),
  table(
    ["Item", "Detail"],
    [
      ["Data source", "Full UTXO scan via Bloodstone Core RPC"],
      ["Rich list", "Live at bloodstonewallet.mytunnel.org/#rich-list"],
      ["Supply basis", "Sum of unspent outputs at tip (~200,970,398 STONE at height 9,704)"],
      ["Wallet labels", "Genesis docs, mine/webuser wallet exports, operational knowledge"],
      ["Update cadence", "Within 30 days of treasury moves ≥ 1M STONE, or quarterly"],
    ],
    [2800, 6560]
  ),
  p(
    "Limitation: Individual signatory names behind multi-key or offline custody are not included in v1.0. A v1.1 addendum will attach named controllers where legally permissible.",
    { italics: true }
  ),

  h1("2. Genesis Premine"),
  table(
    ["Field", "Value"],
    [
      ["Amount", "199,999,998 STONE"],
      ["Genesis address", "SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N (P2PKH)"],
      ["Genesis block hash", "df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0"],
      ["Coinbase message", "22/Jun/2026: Bloodstone independent chain relaunch"],
      ["Custody change vs ROD", "Single P2PKH output instead of legacy 2-of-4 multisig"],
    ],
    [3200, 6160]
  ),

  h2("2.1 Post-Genesis Distribution"),
  p(
    "The genesis address no longer appears in the top 25 by balance at height 9,704. The premine was moved into multiple project-operational addresses between genesis and block ~1,500. This was an operational split, not a public sale or airdrop. No on-chain vesting schedule was encoded at genesis."
  ),

  h1("3. Concentration Snapshot (Height 9,704)"),
  table(
    ["Metric", "Value"],
    [
      ["Total on-chain STONE", "200,970,398"],
      ["PoW minted (era 0)", "~970,400 (~0.48% of supply)"],
      ["Treasury-derived (approx.)", "~200,000,000 (~99.5%)"],
      ["Addresses with balance", "49"],
      ["Top 3 holders", "77.09%"],
      ["Top 10 holders", "96.02%"],
    ],
    [4200, 5160]
  ),

  h2("3.1 Why This Matters for Partners"),
  p(
    "High rich-list concentration primarily means undisbursed project treasury in cold and operational wallets. Partners should treat this as an economic risk until disbursement is visible on-chain — but the remedy is published outflows, not assuming OTC purchases from independent holders."
  ),

  h2("3.2 Dilution vs Decentralization"),
  p(
    "Era-0 PoW will mint ~1.04 billion STONE after the 1,000 STONE fork at block 12,000. If treasury wallets are static, premine share of total supply falls toward ~16% by end of era 0. Issuance alone does not decentralize control if the same entity captures PoW payouts or treasury never moves."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("4. Wallet Registry (Top Holders)"),
  p("Statuses: Cold = long-hold reserve; Operational = day-to-day disbursement; Earmarked = allocated bucket; Spent = genesis fully distributed."),
  table(
    ["Rank", "Address (short)", "Balance", "% supply", "Label", "Bucket"],
    [
      ["—", "SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N", "~0", "—", "Genesis premine (historical)", "Spent"],
      ["1", "SaYQKHQrRMnjtbupzi1Bb9oEWe1rHf1jkk", "60.8M", "30.27%", "Treasury cold (webuser3)", "Core treasury"],
      ["2", "SkAsaotDaF2y8KqJdZaFs9hnpwmaCA7Equ", "51.1M", "25.43%", "Infrastructure reserve", "Infrastructure"],
      ["3", "SPWDbxeVc9BGUepmT5FDECTKr8ucdu91Hh", "45.0M", "22.39%", "Operational (webuser2)", "Partner + ecosystem"],
      ["4", "SarFkPCFripGoPSy6jKag8fYsKiMQhfP3L", "11.0M", "5.47%", "Grants (webuser7)", "Community grants"],
      ["5", "SNK6tDSHYVybJt5HTj5BSwb1PYhoSuZAz6", "8.0M", "4.00%", "Operational reserve", "Infrastructure"],
      ["6–9", "(5M tranches)", "~19.0M", "~9.5%", "Treasury sub-allocations", "Grants / partners / liquidity"],
      ["10", "SbqzoTuDp5ozPWCyj3ykY72TS6Wzk3YArB", "2.0M", "1.00%", "Operational float", "Community"],
      ["18", "SNQ2mNsQSumv1P4QdiDqYz5sjCwdDTnbWV", "66.6K", "0.03%", "Pool operator (mine)", "Pool ops"],
    ],
    [600, 2800, 1100, 900, 2200, 1760]
  ),
  p(
    "Note: Ranks 2 and 5 are not in published wallet exports; labeled from operational custody mapping. Signatory attribution deferred to v1.1.",
    { italics: true }
  ),

  h1("5. Allocation Buckets (Policy Framework)"),
  p("Total treasury envelope: ~200M STONE (genesis premine, now distributed across registry wallets)."),
  table(
    ["Bucket", "Target % of premine", "Purpose", "Primary wallets"],
    [
      ["Infrastructure & core development", "25–30%", "Node, pool, mesh, miners, security", "Ranks 2, 5"],
      ["Ecosystem grants", "15–20%", "Builders, mesh operators, replicators", "Ranks 6–7, 4"],
      ["Partner programs", "15–20%", "Bulk storage quotas, integrators", "Ranks 3, 8"],
      ["Community distribution", "10–15%", "Faucets, rebates, mining incentives", "Ranks 4, 10"],
      ["Liquidity / market making", "5–10%", "CEX/DEX when live", "Rank 9"],
      ["Core treasury — unallocated", "15–25%", "Strategic reserve", "Rank 1"],
    ],
    [2800, 1400, 2800, 2360]
  ),
  p("These are target ranges, not on-chain locks.", { italics: true }),

  h1("6. Disbursement Plan (12–24 Months)"),
  h2("6.1 Principles"),
  bullet("bullets", "No silent re-concentration — treasury moves ≥ 1M STONE are announced with destination label"),
  bullet("bullets", "Partner-first rails — integrators receive STONE from designated outposts, not OTC cold reserves"),
  bullet("bullets", "Measurable reduction — track top-3 and top-10 % of supply each quarter"),
  bullet("bullets", "Blurt benchmark — reduce spot-float dependence before bulk storage invoices go live"),

  h2("6.2 Quarterly Outflow Targets"),
  table(
    ["Period", "Target gross outflow", "Channels"],
    [
      ["Q3 2026", "2–5M STONE", "Mesh pilots, small grants, faucet"],
      ["Q4 2026", "5–10M STONE", "Partner outpost, ecosystem grants"],
      ["H1 2027", "15–25M STONE", "Blurt bulk quota, mesh rebates"],
      ["H2 2027", "20–35M STONE", "Partner programs, liquidity seeding"],
      ["2028", "30–50M / year", "Sustained grants + partner quotas"],
    ],
    [1800, 2400, 5160]
  ),
  p(
    "Cumulative target: ≥ 50M STONE disbursed by July 2027; ≥ 120M STONE by July 2028, subject to partnership cadence."
  ),

  h2("6.3 Concentration Targets (Top-3 % of Supply)"),
  table(
    ["Date", "Target top-3 share", "Notes"],
    [
      ["July 2026", "~77%", "Baseline — pre-disbursement"],
      ["January 2027", "≤ 65%", "First partner outpost flows"],
      ["July 2027", "≤ 55%", "PoW dilution + ≥ 50M disbursed"],
      ["July 2028", "≤ 40%", "Era-0 PoW > 500M; policy mature"],
    ],
    [2200, 2200, 4960]
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("7. Partner Outpost Rail"),
  p("Integrators (including Blurt) should not source large STONE blocks from rich-list addresses on the open market."),
  table(
    ["Item", "Detail"],
    [
      ["Purpose", "Ring-fenced STONE for bulk storage quotas and BLURT→STONE memo credits"],
      ["Funding source", "Rank 3 operational wallet and/or partner bucket (rank 8)"],
      ["Address", "To be published before first production invoice (separate P2PKH)"],
      ["BLURT memo format", "storage:<STONE_ADDRESS>:<bytes>"],
      ["Reporting", "Monthly: opening balance, credits, debits, bytes stored"],
    ],
    [2800, 6560]
  ),

  h1("8. What Is Not On-Chain Today"),
  table(
    ["Item", "Status"],
    [
      ["Time-locked vesting contracts", "Not deployed"],
      ["Multisig treasury with published signers", "Not deployed"],
      ["On-chain bucket enforcement", "Not deployed"],
      ["Automated per-GB storage debits", "Proposed — billing rules in progress"],
      ["Individual signatory names", "Deferred to v1.1 (target Q4 2026)"],
    ],
    [4680, 4680]
  ),

  h1("9. Transparency Commitments"),
  table(
    ["Commitment", "Cadence"],
    [
      ["Rich list", "Live (~10 min TTL)"],
      ["This disclosure", "Quarterly or within 30 days of major treasury moves"],
      ["Treasury move log", "TXIDs + labels for moves ≥ 1M STONE"],
      ["Signatory disclosure", "v1.1 by Q4 2026"],
    ],
    [4680, 4680]
  ),

  h1("10. Related Documents"),
  linkPara("Economic Model White Paper", `${COORDINATOR}/downloads/`),
  linkPara(
    "Blurt Partnership Response",
    `${COORDINATOR}/downloads/Bloodstone-Blurt-Partnership-Response.md`
  ),
  linkPara("Halving Schedule", `${COORDINATOR}/downloads/Bloodstone-Halving-Schedule.md`),
  linkPara("Live rich list", RICH_LIST),
  linkPara("Subsidy schedule API", API_URL),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({
        text: "Bloodstone · July 2026 · Addendum v1.0 (draft)",
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
                  text: "Bloodstone Treasury & Concentration Disclosure",
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
  process.argv[2] ||
  "/root/bloodstone-docs/Bloodstone-Treasury-and-Concentration-Disclosure.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote " + outPath);
});