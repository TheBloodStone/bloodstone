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
      new TextRun({
        text: "Bloodstone Chain Mesh Storage",
        size: 48,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "Cost & Value Proposal — vs Decentralized Storage Alternatives",
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Competitive analysis for partners (Blurt, enterprise, creators)",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "Decentralized storage spans a wide price spectrum — from Filecoin's subsidized ~$0.19/TiB/month cold archive to Storj's ~$7/TiB plus download fees and a $50/month minimum. Bloodstone Chain Mesh targets a differentiated position: beat mid-tier protocols on total cost of ownership (TCO), match enterprise S3 spend for bulk partners, and undercut cold-storage leaders on value-per-dollar through integrated utility rather than token subsidies alone."
  ),
  p(
    "Honest headline: Bloodstone does not today beat Filecoin's raw $/TiB for passive cold archive. We do beat Storj, Jackal, and StorX on TCO for active workloads; we beat every competitor on same-chain integrity (BSM1 anchors), unified STONE/ETH payment rails, HTTP Range VOD, and operational integration with Bloodstone mining, wallet, and APK distribution."
  ),
  p(
    "This proposal introduces three Bloodstone storage tiers — Cold Archive, Standard Mesh, and Hot Partner — with published and roadmap pricing designed to win partner contracts (e.g. Blurt at €22.80/1.2 TB) while scaling toward sub-$1/TiB cold storage via mining-pool-funded replication."
  ),

  h1("1. Competitor Landscape"),
  p(
    "The table below summarizes publicly cited decentralized storage economics (July 2026 market research). Rates vary with token price, deal structure, and subsidies — use as directional comparison, not binding quotes."
  ),
  table(
    ["Protocol", "Monthly / TiB", "Download fee", "Best for", "Key drawback"],
    [
      ["Filecoin", "~$0.19", "Usually free", "Cheapest cold archive", "Miner subsidies; retrieval latency; separate FIL wallet"],
      ["Siacoin", "~$0.80", "~$1.00 / TiB", "Dynamic marketplace", "Smart contract setup; SC wallet complexity"],
      ["BitTorrent (BTT)", "~$2.24", "Varies", "Heavy P2P sharing", "TRX/BTT token exposure; unpredictable peers"],
      ["StorX", "~$4.00", "Free / minimal", "Enterprise hybrid", "Smaller network; less PoW alignment"],
      ["Storj", "~$7.00", "$7.00 / TiB", "S3-compatible API", "$50/month minimum; STORJ token"],
      ["Jackal", "~$8.00", "Free", "Private encrypted hot data", "Cosmos ecosystem; separate wallet"],
      ["AIOZ", "Dynamic", "Varies", "Streaming / AI", "Media-focused; not general archive"],
      ["Arweave", "One-time (high)", "Free", "200+ year permanence", "Large upfront cost; no mutable updates"],
      ["AWS S3 (ref.)", "~$23.00", "Egress fees", "Enterprise default", "Centralized; single-provider risk"],
    ],
    [1400, 1400, 1400, 2200, 2960]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("1.1 What “per TiB” really means"),
  bullet("bullets", "1 TiB = 1,024 GiB. A $7/TiB storage fee plus $7/TiB download = $14 effective cost if you read the full dataset once per month."),
  bullet("bullets", "Minimum monthly charges (Storj $50) punish small tenants — a 100 GiB user pays enterprise rates."),
  bullet("bullets", "Subsidized networks (Filecoin) may raise effective price when subsidies end or retrieval QoS is required."),
  bullet("bullets", "Arweave eliminates recurring fees but requires large upfront capital — poor fit for mutable media libraries."),

  new Paragraph({ children: [new PageBreak()] }),

  h1("2. Bloodstone Pricing Tiers"),
  p(
    "Bloodstone quotes storage in STONE or ETH equivalent at order time. Three tiers map to replication depth, latency, and file-size policy."
  ),
  table(
    ["Tier", "Target $/TiB / month", "Download", "Replication", "File size policy"],
    [
      ["Cold Archive", "$0.49", "Free (coordinator)", "1× catalog + optional peer cache", "Any size; hours retrieval OK"],
      ["Standard Mesh", "$4.99", "Free (coordinator)", "Multi-peer (CHAIN_MESH_BACKUP_PCT)", "Default 64 MiB; tenant raise to 1 GiB"],
      ["Hot Partner", "$1.89 (bulk ≥1 TiB)", "Free + HTTP Range VOD", "Coordinator + overflow edge", "256 MiB–1 GiB; Blurt namespace"],
      ["Overflow cover", "+$0.54 / TiB on spill", "€0.01/GiB egress after free tier", "VPS hot object store", "When mesh limit or lag exceeded"],
    ],
    [1600, 1800, 2200, 2400, 1360]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("2.1 Partner lock rate (Blurt benchmark)"),
  p("Megadrive cited €22.80/month for 1.2 TB (~1.09 TiB) with free-tier bandwidth."),
  bullet("bullets", "Effective: ~€20.90/TiB/month (~$22.50 USD) — matches AWS S3 class, not Filecoin cold."),
  bullet("bullets", "Bloodstone Hot Partner tier at $1.89/TiB bulk: 1.2 TB ≈ $2.06/month storage — far below €22.80 — when mining-pool subsidy + hash-rate rental ETH cross-fund replication (see §4)."),
  bullet("bullets", "Practical launch quote for Blurt: ≤ €22.80/month total (storage + coordinator + Range VOD) — parity with current S3 spend, superior integrity."),

  h2("2.2 Published floor (no subsidy)"),
  p("Without cross-subsidy from pool fees or rental ETH:"),
  mono("≤ €0.019 / GiB-month  ≈  €19.46 / TiB-month  ≈  $21.00 / TiB-month"),
  p("This floor beats Storj TCO ($7 + $7 download on first full read) for tenants that serve ≥3 TiB/month egress per TiB stored, and beats Jackal/StorX on combined storage+download for active VOD."),

  h1("3. Head-to-Head Comparison"),
  table(
    ["vs Competitor", "Bloodstone wins on price?", "Bloodstone wins on value?"],
    [
      ["Filecoin ($0.19/TiB)", "Cold Archive $0.49 approaches but does not beat subsidized rate", "Yes — BSM1 on-chain proof, STONE wallet, no FIL; faster coordinator retrieval for hot files"],
      ["Siacoin ($0.80/TiB)", "Yes — Cold Archive $0.49/TiB undercuts storage; free coordinator download vs ~$1/TiB", "Yes — no per-deal smart contract; HTTP API + partner token"],
      ["BitTorrent ($2.24/TiB)", "Yes — Hot Partner $1.89/TiB bulk; Standard $4.99 still competitive", "Yes — stable coordinator; not dependent on BTT/TRX liquidity"],
      ["StorX ($4.00/TiB)", "Yes — Hot Partner bulk; Standard $4.99 comparable with more replication", "Yes — same chain as PoW rewards; mesh LAN recovery"],
      ["Storj ($7/TiB + $7 DL)", "Yes — all tiers beat $14 TCO; no $50/month minimum", "Yes — Range VOD built-in; BSM1 anchor; no STORJ token"],
      ["Jackal ($8/TiB)", "Yes — Standard $4.99 and Hot $1.89 bulk beat headline", "Yes — broader ecosystem (mining, DEX, APK mesh)"],
      ["AIOZ (dynamic)", "Case-by-case", "Yes for general archive; AIOZ wins niche AI/streaming compute"],
      ["Arweave (one-time)", "Different model", "Yes for mutable media + updates; Arweave wins immutable permanence"],
      ["AWS S3 (~$23/TiB)", "Yes — all Bloodstone tiers beat S3 storage class", "Yes — peer replication + on-chain integrity; hybrid S3 mirror path"],
    ],
    [2200, 3580, 3580]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  new Paragraph({ children: [new PageBreak()] }),

  h1("4. Why Bloodstone Storage Is Better"),
  p(
    "Price per TiB is one column. Partners choose Bloodstone when total value exceeds raw byte cost."
  ),

  h2("4.1 Integrity & audit"),
  bullet("bullets", "BSM1 on-chain anchors — file Merkle root committed in Bloodstone blocks (no competitor offers same-chain PoW attestation)"),
  bullet("bullets", "Content-addressed 256 KiB chunks — SHA-256 verified on every download"),
  bullet("bullets", "Dispute resolution — hash proof survives provider changes; critical for creator platforms (Blurt)"),

  h2("4.2 Operational integration"),
  bullet("bullets", "One wallet — STONE web wallet, ETH escrow (hash-rate rental), BLURT outpost memos — no FIL/SC/STORJ/BTT/JKL token sprawl"),
  bullet("bullets", "Same mesh serves APKs, white papers, block archives, Time Capsule — production-proven, not greenfield"),
  bullet("bullets", "Partner APIs — publish token, assets/blurt/ namespace, S3 mirror cron — days to integrate, not months"),

  h2("4.3 Media & VOD"),
  bullet("bullets", "HTTP Range proxy (July 2026) — HTML5 <video> scrubbing without full-file download"),
  bullet("bullets", "Overflow server — hot edge when mesh peers lag; cover cost transparent"),
  bullet("bullets", "Hybrid S3 path — keep Blurt bucket primary; mesh mirror for integrity; beats Filecoin retrieval UX for screen shares"),

  h2("4.4 Economics alignment"),
  bullet("bullets", "Storage fees route to mesh peers replicating chunks — miners earn from holding data, not only block subsidy"),
  bullet("bullets", "Pool operator 1% slice + hash-rate rental ETH can cross-subsidize partner bulk (explains $1.89/TiB Hot tier)"),
  bullet("bullets", "Proportional reward philosophy Megadrive praised on mining applies to storage replication"),

  h2("4.5 Resilience"),
  bullet("bullets", "Multi-peer replication — not single datacenter (S3) or single deal (Filecoin)"),
  bullet("bullets", "LAN chunk recovery (:18341) — household mesh serves bytes when coordinator is distant"),
  bullet("bullets", "Overflow + mesh manifest pointer — bytes survive mesh policy limits without losing catalog integrity"),

  h1("5. Total Cost of Ownership Scenarios"),
  h3("Scenario A — 1.2 TB media library (Blurt)"),
  table(
    ["Provider", "Storage / mo", "Download (1× full read)", "Minimums", "Total TCO"],
    [
      ["AWS S3", "~€22.80", "Egress extra", "None", "~€25+"],
      ["Storj", "~$8.40", "~$8.40", "$50 min", "~$50+"],
      ["Filecoin", "~$0.23", "Free", "FIL wallet setup", "~$0.23 + ops complexity"],
      ["Bloodstone Hot Partner", "≤€22.80 quoted", "Free Range VOD", "None", "≤€22.80 all-in"],
    ],
    [1800, 1800, 2200, 1400, 2160]
  ),
  new Paragraph({ spacing: { after: 160 }, children: [] }),
  p("Bloodstone matches S3 spend with superior integrity; beats Storj on TCO for this size; trades Filecoin's $0.23 for integrated VOD + BSM1 + no new token."),

  h3("Scenario B — 10 TiB cold archive"),
  table(
    ["Provider", "Storage / mo", "Notes"],
    [
      ["Filecoin", "~$1.90", "Cheapest if subsidies hold"],
      ["Siacoin", "~$8.00 + DL", "Plus contract overhead"],
      ["Bloodstone Cold", "~$4.90", "BSM1 anchor + STONE wallet; coordinator catalog"],
    ],
    [2200, 2200, 4960]
  ),
  new Paragraph({ spacing: { after: 160 }, children: [] }),
  p("Roadmap: pool-funded Cold Archive target $0.39/TiB by Q1 2027 — undercutting Siacoin with simpler onboarding."),

  h3("Scenario C — 100 GiB creator tier"),
  table(
    ["Provider", "Monthly cost", "Problem"],
    [
      ["Storj", "$50 minimum", "Pays 5× fair share for small quota"],
      ["Bloodstone Standard", "~$0.49", "No minimum; pay for bytes used"],
    ],
    [3120, 3120, 3120]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("6. How We Beat Them — Action Plan"),
  table(
    ["Goal", "Action", "Target"],
    [
      ["Beat Storj / Jackal / StorX on TCO", "Hot Partner $1.89/TiB bulk + free Range download", "Live for Blurt tenant"],
      ["Approach Filecoin cold pricing", "Cold Archive tier + pool 1% subsidy", "$0.39/TiB by Q1 2027"],
      ["Beat AWS S3 for partners", "Lock ≤€22.80/1.2 TB all-in quote", "Contract ready"],
      ["Beat ‘complexity tax’", "Partner token + mirror cron + no new token", "Days to deploy"],
      ["Beat Arweave for mutable media", "Overwrite-by-key mesh assets + BSM1 revision history", "Live"],
    ],
    [2800, 4160, 2400]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("7. Recommendation"),
  p(
    "For Blurt and similar partners: adopt Bloodstone Hot Partner tier at S3 parity (≤€22.80/1.2 TB) with hybrid S3 mirror + mesh integrity + Range VOD. You beat Storj, Jackal, StorX, and AWS on TCO and integration; you trade Filecoin's subsidized $0.19/TiB for production VOD UX and same-chain proofs."
  ),
  p(
    "For cold-only archive at petabyte scale: evaluate Bloodstone Cold Archive alongside Filecoin — use Filecoin for lowest $/byte if FIL ops are acceptable; use Bloodstone when STONE ecosystem, BSM1 audit, or unified billing with mining/storage rental matters."
  ),

  h1("8. Related Documents"),
  linkPara("Blurt Mesh Storage Partnership White Paper", COORDINATOR + "/downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx"),
  linkPara("Chain Mesh Storage White Paper", COORDINATOR + "/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"),
  linkPara("S3 + Mesh Integration Operations Guide", COORDINATOR + "/downloads/Bloodstone-Blurt-S3-Mesh-Integration-Operations-Guide.docx"),
  linkPara("Economic Model White Paper", COORDINATOR + "/downloads/Bloodstone-Economic-Model-White-Paper.docx"),

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
                  text: "Bloodstone Storage — Competitive Cost Proposal",
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
  "/root/bloodstone-docs/Bloodstone-Storage-Cost-Comparison-Proposal.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});