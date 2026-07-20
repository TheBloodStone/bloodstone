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
function table(headers, rows) {
  const tableWidth = 9360;
  const widths = headers.map(() => Math.floor(tableWidth / headers.length));
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
    children: [new TextRun({ text: "How do I become a Bloodstone witness?", size: 44, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "FAQ · July 2026 · Downloads only — not chain-mesh anchored",
        size: 22,
        italics: true,
      }),
    ],
  }),

  h1("Short answer"),
  p(
    "Install the Bloodstone miner app → set Local node mode to Consensus or Consensus witness → start the node → stay online."
  ),
  p(
    "There is no election, no stake vote, and no paid office. A Bloodstone witness is a node that verifies the chain and attests to the tip it sees (for the network and QUASAR defense)."
  ),

  h1("What “witness” means"),
  table(
    ["Term", "Meaning"],
    [
      ["Consensus / Consensus witness", "App modes that validate the chain without hosting LAN mining"],
      ["Mesh witness capsule", "Signed tip attestation used by QUASAR / exchanges"],
      ["Not Hive/Blurt witness", "Bloodstone is not DPoS — no voted producer schedule"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p("Witnesses observe and verify. Miners produce blocks. Different roles."),

  h1("Phone steps (exact menu names)"),
  bullet("steps", "Download the miner APK from bloodstonewallet.mytunnel.org/downloads/"),
  bullet("steps", "Set your STONE payout address (wallet you control)"),
  bullet("steps", "Open Local node mode on the miner screen"),
  bullet(
    "steps",
    "Pick: “Consensus — validate chain + P2P witness (~550 MiB, no stratum)” OR “Consensus witness — lightweight witness only…” OR “Full chain — host for household…”"
  ),
  bullet(
    "steps",
    "Tap Start consensus node / Start witness node / Start full node (matches your mode)"
  ),
  bullet("steps", "Wi‑Fi · plugged in · battery saver off · wait for chain sync"),
  bullet("steps", "Stay online when you can; optional mining via Pool mode"),

  h1("Mode cheat sheet"),
  table(
    ["Goal", "Local node mode", "Start button"],
    [
      ["Help verify, low resources", "Consensus witness", "Start witness node"],
      ["Help verify + P2P peer", "Consensus", "Start consensus node"],
      ["Home hub + witness", "Full chain", "Start full node"],
      ["Only mine, no local chain", "LAN client", "(no node start)"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("What you do not need"),
  bullet("bullets", "Stake / bond — no DPoS witness deposit"),
  bullet("bullets", "Votes or “vote for me” posts — not elected"),
  bullet("bullets", "Master Creator admin key — VPS ops only, unrelated"),
  bullet("bullets", "Paying STONE for a title — witness means run verifying software"),

  h1("Links"),
  p("FAQ .md: /downloads/Bloodstone-Become-A-Witness-FAQ.md"),
  p("Discord paste: /downloads/Bloodstone-Become-A-Witness-Discord-Paste.txt"),
  p("How the network works: /downloads/Bloodstone-How-The-Network-Works.md"),
  p("QUASAR: https://bloodstonewallet.mytunnel.org/quasar/"),
];

const doc = new Document({
  styles: {
    default: { document: { styles: [{ id: "Normal", run: { font: "Calibri", size: 22 } }] } },
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
    ],
  },
  sections: [
    {
      properties: {
        page: { margin: { top: 720, bottom: 720, left: 720, right: 720 } },
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({
                  text: "Bloodstone · Become a Witness FAQ v1.0 · ",
                  size: 16,
                  color: "666666",
                }),
                new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "666666" }),
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
const outFile = path.join(outDir, "Bloodstone-Become-A-Witness-FAQ.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(outFile, buf);
  console.log("Wrote", outFile);
});
