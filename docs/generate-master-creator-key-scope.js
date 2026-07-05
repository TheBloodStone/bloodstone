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
    children: [
      new TextRun({
        text: "Master Creator Key — Scope of Control",
        size: 44,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Admin operations reference (downloads only)",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Short answer"),
  p(
    "The Master Creator key unlocks write access on your coordinator VPS admin panel — stratum, faucet, pool settings, local node patches, and fleet metadata for devices registered with your pool."
  ),
  p(
    "It does not remotely update the entire Bloodstone network’s fleet. Other operators’ nodes are unaffected unless they independently choose to pull patches from your coordinator’s downloads manifest."
  ),

  h1("What it is (and is not)"),
  p(
    "The Master Creator key is not a blockchain key, wallet key, or mesh publish token. It is a second admin unlock code for the Bloodstone miner-web admin panel, layered on top of the normal admin password."
  ),
  table(
    ["Concept", "Master Creator?"],
    [
      ["Admin password", "No — opens panel (mostly read-only)"],
      ["Master Creator code", "Yes — enables infrastructure writes"],
      ["STONE wallet / private keys", "No"],
      ["Mesh publish token", "No"],
      ["On-chain governance", "No"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p("Admin password = enter the building. Master Creator code = permission to change live infrastructure on the coordinator you operate."),

  h1("What it controls"),
  h2("Your coordinator / VPS fleet — yes"),
  bullet("bullets", "Stratum ports, share difficulty, public VPS IP"),
  bullet("bullets", "Faucet and pool payout settings"),
  bullet("bullets", "Live node patches on the coordinator (bloodstoned hot OTA via upkeep)"),
  bullet("bullets", "Publish patch bundles to /downloads/ for opt-in consumers"),
  bullet("bullets", "Time Capsule archive/prune on that host"),
  p("This is the VPS stack you deployed and operate — not a global network console."),

  h2("Devices in your pool registry — partial"),
  bullet("bullets", "Edit device_fleet rows for devices that registered with your coordinator"),
  bullet("bullets", "Labels, addresses, workers, creator_role, admin notes"),
  bullet("bullets", "Cannot remotely drive arbitrary hardware worldwide — metadata only"),

  h2("The entire network’s fleet — no"),
  bullet("bullets", "No control over other operators’ VPSes, stratum pools, or nodes"),
  bullet("bullets", "No global push to every Bloodstone miner or node"),
  bullet("bullets", "No on-chain governance or wallet/mesh token access"),

  h1("Node patches — scope in detail"),
  table(
    ["Action", "Scope"],
    [
      ["Apply patch (admin)", "This coordinator VPS only"],
      ["Auto-apply (upkeep)", "This coordinator VPS only"],
      ["Publish to /downloads/", "Available to nodes that opt in via manifest"],
      ["Force-update all network nodes", "Not supported"],
    ],
    [4200, 5160]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Patches are opt-in pull from your downloads server (/api/node-patch/update manifest), not a mandatory network-wide update."
  ),

  h1("Scope summary"),
  table(
    ["Scope", "Master Creator control?"],
    [
      ["Coordinator VPS you operate", "Full"],
      ["Devices in your pool device_fleet DB", "Metadata edits only"],
      ["Other operators’ VPS / pool / nodes", "None"],
      ["Entire Bloodstone network fleet", "None"],
      ["On-chain / consensus", "None"],
    ],
    [5200, 4160]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("Discord-ready reply"),
  p(
    "Master Creator unlocks admin on your coordinator VPS — stratum, faucet, pool settings, local node patches, and fleet metadata for devices registered with your pool. It does not remotely update the entire Bloodstone network’s fleet; other operators’ nodes are unaffected unless they independently pull patches from your coordinator’s downloads manifest."
  ),

  h1("Related documents"),
  bullet("bullets", "Bloodstone-Master-Creator-Key-FAQ.md — full unlock list, login flow, security notes"),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({
        text: "Document version: 1.0 · July 2026 · Downloads only (not chain-mesh anchored)",
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
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ text: "Bloodstone · Master Creator Scope · Page " }),
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

const outDir = path.join(__dirname);
const docxPath = path.join(outDir, "Bloodstone-Master-Creator-Key-Scope.docx");

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(docxPath, buffer);
  console.log("Wrote", docxPath);
});