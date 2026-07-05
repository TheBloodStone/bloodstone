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
    children: [new TextRun({ text: "Bloodstone Master Creator Key", size: 48, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "Admin Panel FAQ · July 2026 · Downloads only",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("What is it?"),
  p(
    "The Master Creator key is not a blockchain key, wallet key, or mesh publish token. It is a second admin unlock code for the Bloodstone miner-web admin panel — layered on top of the normal admin password."
  ),
  p("Admin password = enter the building. Master Creator code = permission to change live infrastructure."),

  h1("Two-step admin access"),
  table(
    ["Step", "Input", "Access level"],
    [
      ["1. Admin password", "Standard login", "Admin panel — mostly read-only"],
      ["2. Master Creator code", "Separate access code", "Write access to fleet & infrastructure"],
    ],
    [1200, 3600, 4560]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("What Master Creator unlocks"),
  h2("Device fleet"),
  bullet("bullets", "Edit registered miners in device_fleet (addresses, workers, algo, labels)"),
  h2("Service settings (save enabled)"),
  bullet("bullets", "Faucet — claim amount, cooldowns, minimum balance"),
  bullet("bullets", "Pool payout — chunk limits"),
  bullet("bullets", "Stratum — VPS IP, ports, share difficulties, GPU vardiff, ROD merge mode"),
  h2("Live node patches (OTA)"),
  bullet("bullets", "Apply hot patches without stopping bloodstoned"),
  bullet("bullets", "Publish patches to /downloads/ for fleet auto-update"),
  h2("Time Capsule"),
  bullet("bullets", "Archive-to-mesh and optional local prune controls"),

  h1("What it does not do"),
  table(
    ["Not this", "Why"],
    [
      ["STONE wallet / private keys", "Web admin session only"],
      ["Mesh publish token", "Separate credential (CHAIN_MESH_PUBLISH_TOKEN)"],
      ["On-chain governance", "No consensus control"],
      ["Chain Mesh file upload", "Does not grant mesh publish by itself"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("Without Master Creator"),
  bullet("bullets", "Admin login still works — view settings, fleet, pool status"),
  bullet("bullets", "Faucet and stratum fields are read-only (disabled)"),
  bullet("bullets", "Fleet edits, node patches, and Time Capsule writes blocked"),

  h1("Storage & setup"),
  bullet("bullets", "Scrypt hash in bloodstone-miner-web/secrets.conf (master_creator_code_hash)"),
  bullet("bullets", "Optional env preset: MASTER_CREATOR_CODE on first boot"),
  bullet("bullets", "Auto-generated once if unset: MASTER-CREATOR-XXXXXXXX (save immediately)"),

  h1("How to unlock"),
  bullet("numbers", "At login: /admin/login → password + optional Master Creator code"),
  bullet("numbers", "After login: /admin → Master Creator panel → Unlock fleet admin"),
  bullet("numbers", "End: End edit access (admin session remains until full logout)"),

  h1("Quick reference"),
  table(
    ["Question", "Answer"],
    [
      ["Blockchain key?", "No"],
      ["Needed to view admin?", "No — admin password only"],
      ["Needed to change stratum/faucet?", "Yes"],
      ["Needed to edit fleet devices?", "Yes"],
      ["Same as mesh publish token?", "No"],
    ],
    [4680, 4680]
  ),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({
        text: "Document version: 1.0 · July 2026 · Downloads only",
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
                  text: "Master Creator Key — Admin FAQ",
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
  process.argv[2] || "/root/bloodstone-docs/Bloodstone-Master-Creator-Key-FAQ.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});