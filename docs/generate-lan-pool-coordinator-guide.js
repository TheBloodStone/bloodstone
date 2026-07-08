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
const COORDINATOR = "https://bloodstonewallet.mytunnel.org";

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
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
  const bodyRows = rows.map(
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
  return new Table({ width: { size: tableWidth, type: WidthType.DXA }, rows: [headerRow, ...bodyRows] });
}

const children = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [new TextRun({ text: "Bloodstone LAN Pool Coordinator Guide", bold: true, size: 36 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({ text: "Document version 1.0 · July 2026 · APK 1.3.84 · Web 1.3.129-web", size: 22 }),
    ],
  }),

  h1("Summary"),
  p(
    "Bloodstone Android full nodes can act as LAN pool coordinators that replace the central VPS pool for jobs, shares, and payouts on your household Wi‑Fi. A node only takes over after it speaks with at least one other synced node and compares notes (chain tip, open rounds, recent block finds). Until verification succeeds, pool mode continues to relay to the VPS as before."
  ),

  h1("How it works"),
  bullet("numbers", "Two or more synced nodes on the same Wi‑Fi run Full chain or Pruned mode with the local node started."),
  bullet(
    "numbers",
    "Every ~20 seconds each node exchanges a pool snapshot over LAN HTTP port 18342 (GET /api/lan-pool/snapshot)."
  ),
  bullet("numbers", "Nodes compare chain tip, open round job heights, share weights (within 5%), and recent block finds."),
  bullet(
    "numbers",
    "When at least one peer agrees, the node becomes a verified LAN pool coordinator: local jobs, share ledger, proportional payouts, peer replication — no VPS pool."
  ),

  h1("Requirements"),
  table(
    ["Component", "Version", "Required for"],
    [
      ["Android APK", "1.3.84+", "Native coordinator, stratum, SQLite ledger"],
      ["Web UI OTA", "1.3.129-web+", "Routing, status panel, miner log messages"],
    ],
    [2800, 2200, 4360]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  linkPara("Download latest APK", COORDINATOR + "/downloads/bloodstone-miner-android-latest.apk"),

  h1("Household setup"),
  h2("Host nodes (coordinator candidates)"),
  bullet("bullets", "Local node mode → Full chain or Pruned (~550 MiB)."),
  bullet("bullets", "Tap Start full node; stay on Wi‑Fi and power until sync completes."),
  bullet("bullets", "Run a second synced node on the same LAN (verification needs ≥1 peer)."),

  h2("Miners (LAN clients, Bitaxe, other phones)"),
  bullet("bullets", "Local node mode → LAN client — no chain download."),
  bullet("bullets", "Enter STONE payout address; mining mode → Pool."),
  bullet("bullets", "Start mining — app finds a verified coordinator on Wi‑Fi."),

  h2("Bitaxe (SHA256d)"),
  bullet("bullets", "Host: phone LAN IP, port 3429."),
  bullet("bullets", "Worker: YOUR_STONE_ADDRESS.rig1"),
  bullet("bullets", "Password x = pool via LAN coordinator; password solo = local blocks."),

  h1("Status in the app"),
  table(
    ["Location", "Message"],
    [
      ["Local node detail (active)", "LAN pool coordinator active — verified with N peer(s)"],
      ["Local node detail (waiting)", "Need another synced node on Wi‑Fi to compare notes"],
      ["Miner log (local)", "LAN pool coordinator on this phone — jobs, shares, payouts local"],
      ["Miner log (remote)", "LAN pool coordinator <ip> — no VPS"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p("Pending balance (LAN only):"),
  mono("GET http://<lan-ip>:18342/api/lan-pool/balance?address=YOUR_STONE_ADDRESS"),

  h1("LAN pool HTTP API (port 18342)"),
  table(
    ["Endpoint", "Method", "Purpose"],
    [
      ["/api/lan-pool/snapshot", "GET", "Peer verification — chain + pool state"],
      ["/api/lan-pool/status", "GET", "Coordinator running / verified / active"],
      ["/api/lan-pool/balance?address=", "GET", "Pending STONE balance"],
      ["/api/lan-pool/share-import", "POST", "Replicate credited share from peer"],
      ["/api/lan-pool/block-find", "POST", "Replicate block distribution from peer"],
    ],
    [3600, 1200, 4560]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p("All endpoints accept LAN clients only (private RFC1918 addresses)."),

  h1("Stratum ports"),
  table(
    ["Algorithm", "Port"],
    [
      ["Neoscrypt-Xaya", "3437"],
      ["Yespower R16", "3438"],
      ["SHA256d / Bitaxe", "3429"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Before verification, pool password x relays to the VPS (64.188.22.190). After verification, the same ports serve the local pool."
  ),

  h1("Before vs after verification"),
  table(
    ["Phase", "Jobs", "Shares", "Payouts", "VPS"],
    [
      ["Before", "Relayed from VPS", "VPS pool.db", "VPS", "Required"],
      ["After", "Local bloodstoned", "On-device SQLite + peers", "pending_stone", "Not used"],
    ],
    [1800, 2000, 2000, 1800, 1760]
  ),

  h1("Algorithm notes"),
  bullet("bullets", "SHA256d: full share hash validation on the coordinator."),
  bullet(
    "bullets",
    "Neoscrypt / Yespower: shares credited after submit; peer cross-check is the trust layer."
  ),
  bullet(
    "bullets",
    "Solo mode: always mines through the local full node — independent of VPS and verification."
  ),

  h1("Payouts"),
  p(
    "Coordinators track pending_stone per address. On-chain payout transactions are separate from share accounting. Default per block: 100 STONE reward, 1% pool fee, 5 STONE finder bonus."
  ),

  h1("Troubleshooting"),
  table(
    ["Symptom", "Fix"],
    [
      ["Waiting for peers", "Start a second full/pruned node on same Wi‑Fi"],
      ["Still using VPS", "Wait for sync; ensure two nodes see each other (mDNS)"],
      ["LAN client finds no host", "Start full node on one plugged-in device"],
      ["No coordinator features", "Upgrade to APK 1.3.84+"],
    ],
    [4000, 5360]
  ),

  h1("Related documents"),
  linkPara(
    "Infrastructure Independence White Paper",
    COORDINATOR + "/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx"
  ),
  linkPara(
    "Mesh Virtual LAN White Paper",
    COORDINATOR + "/downloads/Bloodstone-Mesh-Virtual-LAN-White-Paper.docx"
  ),
  linkPara(
    "Chain Mesh Storage White Paper",
    COORDINATOR + "/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  linkPara("Markdown edition", COORDINATOR + "/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md"),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({
        text: "Bloodstone · LAN pool coordinator · bloodstonewallet.mytunnel.org",
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
                  text: "LAN Pool Coordinator Guide",
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
  "/root/bloodstone-docs/Bloodstone-LAN-Pool-Coordinator-Guide.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});