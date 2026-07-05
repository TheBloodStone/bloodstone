const fs = require("fs");
const path = require("path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  Footer,
  AlignmentType,
  LevelFormat,
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  PageNumber,
} = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}
function p(text) {
  return new Paragraph({ spacing: { after: 160 }, children: [new TextRun(text)] });
}
function bullet(ref, text) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80 },
    children: [new TextRun(text)],
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
    children: [new TextRun({ text: "How the Bloodstone Network Works", bold: true, size: 36 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 280 },
    children: [
      new TextRun({
        text: "A plain-language guide for everyday users · July 2026",
        italics: true,
        size: 22,
      }),
    ],
  }),

  h1("The one-minute version"),
  p(
    "Bloodstone is a shared digital ledger (the blockchain). People who do math work called mining help add new pages to that ledger and can earn STONE coins. Separate computers and phones called nodes download the ledger and check that every page is real before trusting it."
  ),
  p(
    "Most people only need the miner app and a payout address. You tap Start, your phone does work for the pool, and rewards show up over time. You do not need servers, ports, or blockchain engineering to mine."
  ),
  p(
    "Running a node on your phone is optional. It helps the network stay honest and can let your household mine through your own Wi‑Fi instead of a far-away server."
  ),

  h1("Three kinds of participants"),
  p("Think of the network like a town library and a gold-panning creek:"),
  table(
    ["Role", "Plain English", "Do you need this?"],
    [
      ["Miner", "Does math puzzles to help secure the network and earn coins", "Yes, if you want to mine"],
      ["Node", "Keeps a copy of the ledger and checks new pages are valid", "Optional — helpful, not required for basic mining"],
      ["Pool", "Groups miners, tracks work fairly, pays rewards", "Yes for phone mining (the app connects automatically)"],
    ],
    [2200, 4160, 3000]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p("You can be a miner only, a node only, or both on the same phone."),

  h1("How mining works on your phone"),
  bullet("steps", "Install the Bloodstone miner app (Android)."),
  bullet("steps", "Paste your STONE payout address."),
  bullet("steps", "Tap Start mining."),
  bullet("steps", "The app connects to the pool over the internet."),
  bullet("steps", "The pool sends small math jobs; your phone runs them."),
  bullet("steps", "Valid results (shares) are recorded; rewards accumulate per pool rules."),
  p(
    "You do not need the full blockchain for pool mode. Solo mining needs your own synced node — most beginners should stay on pool mode."
  ),

  h1("What a node is"),
  p(
    "A node is a copy of the Bloodstone program that downloads chain data, verifies blocks follow the rules, and can relay information on your Wi‑Fi. Nodes are the network's fact-checkers."
  ),
  p("You choose how much storage and responsibility you want in Local node mode."),

  h1("Local node modes"),
  table(
    ["Mode", "What it does", "Storage", "Best for"],
    [
      ["LAN client", "No chain on this phone; mines via a full node on Wi‑Fi", "Almost none", "Extra phones that just mine"],
      ["Pruned", "Small chain (~550 MB); can host household miners", "~550 MB+", "Light household host"],
      ["Full chain", "Complete blockchain; strongest home server", "~2 GB+", "One plugged-in home host"],
      ["Consensus", "Validates chain + network peer; no mining hosting", "~550 MB+", "Help secure network without hosting miners"],
      ["Consensus witness", "Lightest verifier; outbound only", "~550 MB+", "Low-RAM phones helping verify"],
      ["Mesh federation", "Pruned tip + optional backups", "~550 MB+", "Advanced backup helpers"],
    ],
    [1800, 3360, 1600, 2600]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("A simple household setup"),
  p("On one phone: Full chain mode, start node, wait for sync (Wi‑Fi, plugged in)."),
  p("On other phones: LAN client mode, start mining — they find the home node on Wi‑Fi."),
  p("Everyone can still use the online pool if the home node is syncing or unavailable."),

  h1("What the central server does today"),
  bullet("bullets", "Pool — connects miners, tracks shares, runs payouts"),
  bullet("bullets", "Chain sync helper — mining can use the pool while your node catches up"),
  bullet("bullets", "Downloads & app updates — APK, guides, web UI"),
  bullet("bullets", "LAN registry — helps phones find home nodes on the same network (optional)"),
  p(
    "More full and consensus nodes worldwide means less reliance on any single central machine."
  ),

  h1("Consensus-only nodes"),
  p(
    "Consensus and Consensus witness modes help validate the network without turning your phone into a mining server for others. To mine on the same device, use pool mode or a household full node on Wi‑Fi."
  ),

  h1("Practical tips"),
  bullet("tips", "Use a payout address you control — the app does not need your private keys for pool mining."),
  bullet("tips", "Use Wi‑Fi for chain download and large updates."),
  bullet("tips", "Plug in and relax battery saver while syncing a node."),
  bullet("tips", "Install APK updates from Downloads when offered for native fixes."),

  h1("Quick choices"),
  table(
    ["Your goal", "Suggested setting"],
    [
      ["Just mine on one phone", "Pool mode · LAN client or pruned"],
      ["Family mines on home Wi‑Fi", "Full node on one phone · LAN client on others"],
      ["Help network, not host miners", "Consensus or Consensus witness"],
      ["Very little storage", "LAN client or pool-only without a node"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("Where to get help"),
  p("Downloads: https://bloodstonewallet.mytunnel.org/downloads/"),
  p("Miner portal: https://bloodstonewallet.mytunnel.org/mining/mine"),
  p("Document version 1.0 · July 2026 · Downloads only (not chain-mesh anchored)"),
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
    ],
  },
  numbering: {
    config: [
      {
        reference: "steps",
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
        reference: "tips",
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
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ text: "Bloodstone · How the Network Works · Page " }),
                new TextRun({ children: [PageNumber.CURRENT] }),
              ],
            }),
          ],
        }),
      },
      children,
    },
  ],
});

const outDir = __dirname;
const docxPath = path.join(outDir, "Bloodstone-How-The-Network-Works.docx");

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(docxPath, buffer);
  console.log("Wrote", docxPath);
});