#!/usr/bin/env node
/** Bloodstone Blurt LAN pool + mesh technical response — DOCX generator. */
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
      new TextRun({
        text: "Bloodstone Technical Response to Blurt",
        bold: true,
        size: 32,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [
      new TextRun({
        text: "LAN Pool, Mesh Manifests & Multi-Algo Security",
        size: 24,
      }),
    ],
  }),
  p("Document version: 1.0 · July 2026", { italics: true }),
  p("Audience: Blurt Core (Megadrive)", { italics: true }),
  linkPara("Coordinator portal", COORDINATOR),

  h1("Executive summary"),
  p(
    "Blurt asked whether Bloodstone's LAN pool coordinator (mining) has an equivalent for storage manifests versus the central mytunnel.org coordinator, and raised follow-up questions on 51% / SHA256d dominance, Neoscrypt/Yespower validation on Android, and on-chain payouts from LAN coordinators."
  ),
  table(
    ["Question", "Answer"],
    [
      [
        "Storage manifests vs central coordinator?",
        "Mining LAN coordinator is live. Storage follows the same decentralization philosophy via chain mesh v2.0-Lite (Blurt L1 manifests + trustless chunks). Household LAN mesh cache is the planned analogue.",
      ],
      [
        "51% / peer verification?",
        "LAN peer verification is pool accounting only, not consensus-level 51% protection. Multi-algo PoW exists at consensus; ASIC dominance rebalance is pool-level. DigiByte-style geometric-mean consensus is a future option.",
      ],
      [
        "Neoscrypt/Yespower on Android?",
        "SHA256d has full hash validation on-device; Neoscrypt/Yespower use submit + peer cross-check today. Native CPU hash modules are on the roadmap.",
      ],
      [
        "LAN coordinator payouts?",
        "Block rewards credit pending_stone in SQLite automatically; on-chain sendtoaddress is a separate operator step requiring a funded host wallet.",
      ],
    ],
    [3120, 6240]
  ),

  h1("1. LAN pool coordinator vs storage manifests"),
  h2("1.1 What shipped (mining)"),
  p(
    "The LAN pool coordinator (Android APK 1.3.84+, web UI OTA 1.3.129-web+) replaces the VPS stratum relay (64.188.22.190) for jobs, shares, and pool accounting on household Wi-Fi — after at least one synced peer agrees on chain/pool state over HTTP port 18342."
  ),
  p("It does not replace the mesh manifest catalog or chunk plane."),

  h2("1.2 Storage manifests (separate layer)"),
  p("Chain mesh handles file storage in two layers:"),
  table(
    ["Layer", "Today", "Direction"],
    [
      [
        "Manifest registry",
        "BSM1 anchors on Bloodstone chain + coordinator catalog",
        "v2.0-Lite: Blurt L1 via chain_mesh_anchor; coordinator as fallback",
      ],
      [
        "Chunk plane",
        "256 KiB content-addressed chunks; SHA-256 + Merkle verify",
        "Peer replication; libp2p/DHT planned",
      ],
      [
        "LAN equivalent",
        "Not shipped yet",
        "Household nodes cache manifests + replicate chunks; resolve from L1 anchors",
      ],
    ],
    [2200, 3580, 3580]
  ),
  h2("1.3 Summary"),
  bullet("bullets", "Mining LAN coordinator = live (pool jobs/shares/payout ledger on LAN)."),
  bullet(
    "bullets",
    "Storage LAN = same philosophy, implemented first for Blurt via v2.0-Lite, extensible to other tenants."
  ),

  h1("2. 51% attack protection and peer verification"),
  h2("2.1 What LAN peer verification does"),
  p(
    "Peer verification is pool accounting trust, not consensus-level 51% protection. Synced nodes compare chain tip, per-algo job heights, share weights (±5%), and recent block finds. When at least one peer agrees, the node becomes a verified LAN pool coordinator."
  ),
  p(
    "This stops a rogue phone from inventing pool credits on the LAN. It does not stop a SHA256d majority from rewriting chain history — that requires a consensus change (e.g. DigiByte multi-algo geometric mean)."
  ),

  h2("2.2 Consensus vs pool level"),
  bullet("bullets", "Consensus: multi-algo PoW from block 1 (Neoscrypt-Xaya, Yespower R16, SHA256d)."),
  bullet(
    "bullets",
    "Pool (VPS + LAN): ASIC dominance rebalance when ASIC weight >75% on CPU algos — redistributes 25% of ASIC weight to CPU miners."
  ),

  h2("2.3 Roadmap option (not committed)"),
  p(
    "Consensus fork toward work-weight blending across algos if SHA256d chain-work share becomes a concern. Peer verification remains complementary."
  ),

  h1("3. Neoscrypt / Yespower validation on Android"),
  table(
    ["Algorithm", "LAN coordinator today"],
    [
      ["SHA256d", "Full share hash validation (native stratum server)"],
      ["Neoscrypt / Yespower", "Share accepted on submit; peer cross-check is the trust layer"],
    ],
    [3120, 6240]
  ),
  p(
    "No bundled Neoscrypt/Yespower hash binary on Android yet — on-device PoW re-check for CPU algos is not available today."
  ),
  h3("Roadmap"),
  bullet("numbers", "Near term: peer verification for CPU algos on LAN (live)."),
  bullet("numbers", "Medium term: JNI/native hash modules for on-device validation."),
  bullet("numbers", "Permanent fallback: multi-peer quorum even after native validation."),

  h1("4. Payouts from LAN coordinators"),
  h2("4.1 Pool accounting (automatic)"),
  p(
    "On block find: reward (~100 STONE) split per pool rules (1% fee, 5 STONE finder bonus, remainder pro-rata). Credits land as pending_stone in SQLite; peers replicate over port 18342."
  ),
  mono("GET http://<lan-ip>:18342/api/lan-pool/balance?address=YOUR_STONE_ADDRESS"),

  h2("4.2 On-chain sends (operator step)"),
  p(
    "Moving pending_stone to miner wallets via sendtoaddress is separate from share accounting. The coordinator bloodstoned wallet must hold spendable STONE."
  ),
  table(
    ["Event", "What happens"],
    [
      ["Block coinbase", "Pays to host node wallet that mined the block"],
      ["Pool credits", "IOUs in SQLite until operator batches payouts"],
      ["VPS comparison", "Same pattern as public pool — LAN moves ledger local"],
    ],
    [3120, 6240]
  ),
  p(
    "Future: optional auto-payout (threshold + sendtoaddress) in a future APK."
  ),

  h1("5. Partner one-liner"),
  p(
    "Mining LAN coordinator is live. Storage follows via mesh v2.0-Lite (Blurt L1 manifests + trustless chunks). Peer verification secures pool books, not consensus; native CPU hash validation is on the roadmap; on-chain payouts need a funded host wallet — accounting is automatic, sends are operator-triggered.",
    { italics: true }
  ),

  h1("Related documents"),
  linkPara(
    "LAN Pool Coordinator Guide",
    `${COORDINATOR}/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md`
  ),
  linkPara(
    "Blurt Mesh v2.0-Lite System",
    `${COORDINATOR}/downloads/Bloodstone-Blurt-Mesh-v2-Lite-System.docx`
  ),
  linkPara(
    "Chain Mesh Capacity FAQ",
    `${COORDINATOR}/downloads/Bloodstone-Chain-Mesh-Capacity-And-Usage-FAQ.md`
  ),
  linkPara(
    "Infrastructure Independence White Paper",
    `${COORDINATOR}/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx`
  ),

  p("Bloodstone · Blurt technical response · July 2026", { italics: true, size: 20 }),
];

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT }],
      },
      {
        reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT }],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              alignment: AlignmentType.RIGHT,
              children: [new TextRun({ text: "Bloodstone · Blurt technical response", size: 18, color: "666666" })],
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

const outPath = "/root/bloodstone-docs/Bloodstone-Blurt-LAN-Pool-And-Mesh-Technical-Response.docx";
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath, buffer.length, "bytes");
});