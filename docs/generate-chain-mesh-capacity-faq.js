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
    children: [
      new TextRun({ text: "Bloodstone Chain Mesh", size: 48, bold: true }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "Capacity, Chain Sync & Key Overwrite — FAQ",
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Downloads only (not chain-mesh anchored)",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "This FAQ answers: (1) how much data the mesh can hold vs. coin supply, (2) whether mesh avoids downloading the full chain for files, and (3) whether files can be changed by key."
  ),
  p(
    "Short answers: capacity is not STONE-capped in consensus; mesh files download independently of chain sync; republishing the same asset_key replaces the current revision."
  ),

  h1("1. Mesh Capacity vs. Coin Supply"),
  h2("1.1 No consensus link"),
  p(
    "Bloodstone consensus does not tie mesh bytes to total STONE supply. The chain stores manifests and optional BSM1 anchors — not raw file bytes. Capacity depends on coordinator disk, peer replication, per-file policy, and economics."
  ),

  h2("1.2 Per-file policy defaults"),
  table(
    ["Setting", "Default", "Effect"],
    [
      ["CHAIN_MESH_MAX_ASSET_BYTES", "64 MiB", "Max single published file"],
      ["CHAIN_MESH_MAX_ASSET_CHUNKS", "256", "Max chunks per file"],
      ["CHAIN_MESH_CHUNK_SIZE", "256 KiB", "256 × 256 KiB = 64 MiB max at defaults"],
    ],
    [3600, 1800, 3960]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p("Tenant operators can raise limits (e.g. Blurt: 256 MiB–1 GiB per file)."),

  h2("1.3 Live snapshot (July 2026)"),
  table(
    ["Metric", "Value"],
    [
      ["Catalogued assets", "29"],
      ["Total file bytes", "~137 MiB"],
      ["Coordinator chunks", "~1,536"],
      ["Time Capsule manifest", "~17 MiB"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("1.4 Economic illustration"),
  p("At €0.019/GiB-month (~€19.5/TiB-month), if €1.05M of STONE value funded storage:"),
  bullet("bullets", "Era-0 PoW (~105M STONE @ €0.01) → ~54 TiB-month (illustrative)"),
  bullet("bullets", "Premine (~200M STONE @ €0.01) → ~100+ TiB-month (illustrative)"),
  p("No automatic supply→storage allocation exists in code. Practical scale = disk + paid replication."),

  h2("1.5 Growth limits"),
  bullet("bullets", "CHAIN_MESH_BACKUP_PCT=10 — each peer backs ~10% of chunk hashes"),
  bullet("bullets", "MAX_CHUNKS_PER_DEVICE=32 — ~8 MiB announced per device"),
  bullet("bullets", "Overflow server — spill when mesh policy or replication lag exceeded"),

  new Paragraph({ children: [new PageBreak()] }),

  h1("2. Mesh vs. Full Chain Download"),
  h2("2.1 Mesh files — no full chain needed"),
  mono("GET /api/chain-mesh/asset/<asset_key>/download"),
  mono("GET /api/chain-mesh/chunk/<chunk_hash>"),
  p("Fetch only that asset's chunks — or a byte Range slice for VOD. Full chain not required."),

  h2("2.2 Time Capsule — pruned tip"),
  p(
    "Block history archived to mesh lets nodes run a pruned tip (~550 MiB local) instead of retaining full chain history on disk."
  ),

  h2("2.3 When full chain is still needed"),
  table(
    ["Goal", "Full chain?"],
    [
      ["Download mesh file (APK, doc, video)", "No"],
      ["Run pruned node + wallet", "No — ~550 MiB tip + P2P sync"],
      ["Restore blocks from Time Capsule", "No — mesh chunks"],
      ["Validate from genesis (classic)", "Yes"],
    ],
    [5600, 3760]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("3. Overwrite Files by Key"),
  h2("3.1 Confirmed — same asset_key replaces revision"),
  p(
    "Republishing with the same asset_key UPDATEs the catalog row, replaces chunk manifest, and optionally anchors new BSM1 Merkle root."
  ),

  h2("3.2 Writable keys API"),
  mono("GET /api/chain-mesh/writable-keys?prefix=assets/"),
  p('Returns overwrite: true. Note: "Publish with same asset_key to replace current revision."'),

  h2("3.3 Namespace rules"),
  table(
    ["Prefix", "Who overwrites", "Method"],
    [
      ["assets/...", "Users (review) or partner token", "Republish same key"],
      ["downloads/...", "Admin publish token only", "Republish same key"],
    ],
    [2200, 3580, 3580]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("3.4 What changes vs. what stays"),
  bullet("bullets", "Stable: asset_key and download URL path"),
  bullet("bullets", "Changes: file_sha256, merkle_root, chunk list, version label"),
  bullet("bullets", "Old chunks may remain on disk (content-addressed dedup)"),
  bullet("bullets", "Optional BSM1 anchor per revision"),

  h2("3.5 Examples"),
  mono("downloads/bloodstone-miner-android-1.3.36.apk → same key, new APK bytes"),
  mono("assets/blurt/s3/uploads/user123/video.mp4 → partner token republish"),

  h1("4. Quick Reference"),
  table(
    ["Question", "Answer"],
    [
      ["Capped by coin supply?", "No in consensus; disk + economics"],
      ["Default max per file?", "64 MiB (raiseable)"],
      ["Files without full chain?", "Yes"],
      ["Node needs chain data?", "Yes — pruned tip, not full history"],
      ["Overwrite by key?", "Yes"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("5. Related Documents"),
  linkPara("Chain Mesh Storage White Paper", COORDINATOR + "/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"),
  linkPara("Mesh File Upload White Paper", COORDINATOR + "/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx"),
  linkPara("Storage Cost Comparison (MD)", COORDINATOR + "/downloads/Bloodstone-Storage-Cost-Comparison-Proposal.md"),

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
                  text: "Chain Mesh Capacity & Usage FAQ",
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
  "/root/bloodstone-docs/Bloodstone-Chain-Mesh-Capacity-And-Usage-FAQ.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});