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
function mono(text) {
  return new Paragraph({
    spacing: { after: 100 },
    children: [new TextRun({ text, font: "Courier New", size: 20 })],
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
        text: "Bloodstone × Blurt",
        size: 52,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "Chain Mesh Storage Partnership — Technical & Economic Proposal",
        size: 32,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Response to Blurt team inquiry (Megadrive)",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "Blurt.blog currently stores media in a centralized object bucket (~1.2 TB for ~€22.80/month). Bloodstone offers an alternative storage layer — Chain Mesh — where files are content-addressed, replicated across network peers, and anchored on-chain (BSM1) for integrity. This white paper answers Blurt's technical questions, proposes a practical integration model, and outlines STONE-denominated economics competitive with traditional object storage."
  ),
  p(
    "Bloodstone's economic white paper today focuses on mining reward distribution. Mesh storage utility is the complementary consumption layer Megadrive identified: STONE paid for durable bytes funds edge replication and coordinator services, while miners and mesh peers earn from holding and serving chunks."
  ),

  h1("1. Answers to Blurt Technical Questions"),

  h2("1.1 Is the 64 MiB file limit a hard cap?"),
  p(
    "No — it is a coordinator policy default, not a protocol ceiling. The publish validator reads CHAIN_MESH_MAX_ASSET_BYTES (default 64 MiB) and CHAIN_MESH_MAX_ASSET_CHUNKS (default 256). With 256 KiB chunks, 256 × 256 KiB = 64 MiB maximum per asset revision at default settings."
  ),
  p(
    "A 161 MiB screen-share video exceeds today's default but fits the same chunking model once limits are raised. Example operator configuration for Blurt media tier:"
  ),
  mono("CHAIN_MESH_MAX_ASSET_BYTES=268435456   # 256 MiB per file"),
  mono("CHAIN_MESH_MAX_ASSET_CHUNKS=1024       # up to 1 GiB at 256 KiB chunks"),
  p(
    "Chunk size (CHAIN_MESH_CHUNK_SIZE) is also tunable. The blockchain never stores raw bytes — only manifests and optional BSM1 anchors — so raising per-file limits is an infrastructure decision, not a consensus fork."
  ),

  h2("1.2 What does this look like for Blurt in practice?"),
  p(
    "Blurt does not need to expose Bloodstone keys to every end user on day one. Three deployment models are supported:"
  ),
  table(
    ["Model", "Who holds keys", "User experience", "Best for"],
    [
      [
        "A — Blurt bulk tenant",
        "Blurt team operates one STONE wallet + publish token",
        "Users upload via Blurt UI; Blurt maps files to namespaced mesh keys",
        "Launch phase — mirrors current S3 bucket model",
      ],
      [
        "B — Per-user namespaces",
        "Blurt provisions assets/blurt/users/<blurt_account>/… per user",
        "Users see Blurt storage quotas; keys managed by Blurt backend",
        "Free tier + paid expansion without wallet onboarding",
      ],
      [
        "C — Direct user STONE",
        "Individual users pay STONE for extra quota",
        "Power users buy storage from Bloodstone network directly",
        "Premium tier, creators, large archives",
      ],
    ],
    [1600, 2200, 2800, 2760]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Recommended launch path: Model A (bulk tenant) with namespaced keys such as assets/blurt/media/<post_id>/<filename>. Blurt.blog pays STONE (or BLURT converted via outpost) for aggregate quota. End users interact only with Blurt — same as today's S3 integration."
  ),
  bullet("bullets", "Blurt team receives CHAIN_MESH_PUBLISH_TOKEN for immediate publish on approved keys"),
  bullet("bullets", "Community uploads use assets/ prefix with optional admin review queue"),
  bullet("bullets", "Official Blurt media uses assets/blurt/… namespace — overwrite by key updates posts in place"),
  bullet("bullets", "Download URLs served via Bloodstone CDN path or Blurt proxy to GET /api/chain-mesh/asset/<key>/download"),

  h2("1.3 Can it stream live video at full resolution?"),
  p(
    "Chain Mesh today is optimized for durable file storage and verified download — not sub-second live broadcast. Bytes are stored as 256 KiB content-addressed chunks with whole-file SHA-256 verification. That model excels at APKs, documents, images, and pre-recorded video."
  ),
  h3("Pre-recorded video (VOD) — supported with a buffer layer"),
  bullet("numbers", "Upload MP4/WebM to mesh (after limit raise for files > 64 MiB)"),
  bullet("numbers", "Blurt embed uses progressive chunk fetch or a thin edge cache in front of mesh download API"),
  bullet("numbers", "HTML5 <video> with range requests can be added via coordinator byte-range proxy (roadmap item)"),
  bullet("numbers", "Optional: transcode to HLS segments as separate mesh keys (assets/blurt/hls/<id>/seg000.ts)"),

  h3("Live video — requires a streaming layer (not native today)"),
  p(
    "Full-resolution live stream at broadcast latency needs RTMP/WebRTC ingest → segmenter → CDN edge. Bloodstone's BSM3/BSM4 virtual LAN and mesh-gateway can relay bytes between peers, but that is a transport fabric — not a turnkey live streaming product."
  ),
  p(
    "Practical recommendation for Blurt: use Chain Mesh for recorded clips, thumbnails, and attachments; use a dedicated live ingest service (or Blurt's existing stream provider) for real-time broadcast, with optional post-stream archive to mesh."
  ),

  h2("1.4 Network fees for storage"),
  p(
    "Two fee categories apply:"
  ),
  table(
    ["Fee type", "What it pays for", "Typical magnitude"],
    [
      ["BSM1 anchor tx", "On-chain commit of file Merkle root (integrity proof)", "Normal Bloodstone tx fee (~dust level)"],
      ["Storage allocation (proposed)", "Durable bytes + replication + coordinator catalog", "Per-GB-month in STONE (see §3)"],
      ["Chunk relay (future)", "Bandwidth served by mesh peers", "Optional per-GB egress rebate to peers"],
    ],
    [2200, 4160, 3000]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Today's codebase funds mesh coordination from pool operator fees (1% slice in the Economic Model white paper). Dedicated storage billing — quota accounts, STONE debits, peer replication incentives — is the utility layer Blurt would help pioneer. Section 3 proposes pricing anchored to Blurt's current €22.80 / 1.2 TB benchmark."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("2. Proposed Blurt Integration Architecture"),

  h2("2.1 Storage flow"),
  bullet("numbers", "User uploads media in Blurt UI → Blurt backend"),
  bullet("numbers", "Backend chunks file, POSTs to /api/chain-mesh/publish-upload (Blurt publish token)"),
  bullet("numbers", "Backend registers manifest at assets/blurt/… key with optional BSM1 anchor"),
  bullet("numbers", "Blurt stores mesh asset_key in post metadata; serves download URL to readers"),
  bullet("numbers", "Mesh peers replicate chunks per CHAIN_MESH_BACKUP_PCT policy; LAN peers serve :18341 for recovery"),

  h2("2.2 Free tier and stakeholder perks"),
  p(
    "Megadrive's suggestion: Blurt team provides X MB free per user, paid from a Blurt bulk STONE allocation. Implementation:"
  ),
  bullet("bullets", "Quota table: blurt_account → bytes_allowed, bytes_used, tier (free / stakeholder / paid)"),
  bullet("bullets", "Stakeholder tiers: higher BLURT stake → larger free quota (configured by Blurt governance)"),
  bullet("bullets", "Overage: user buys STONE storage directly OR Blurt bills BLURT → STONE conversion"),

  h2("2.3 BLURT → STONE payment rail (outpost account)"),
  p(
    "Bloodstone will operate (or designate) an outpost account that accepts BLURT with a structured memo:"
  ),
  mono("MEMO: storage:<STONE_ADDRESS>:<bytes>"),
  p(
    "Example: sender transfers BLURT to @bloodstone-storage; memo storage:STNabc123…:1073741824 credits 1 GiB to that STONE wallet's storage quota. Blurt team can use the same rail for bulk monthly payment instead of per-user billing."
  ),
  table(
    ["Party", "Action"],
    [
      ["Blurt user (optional)", "Buy extra quota — BLURT to outpost + memo with their STONE address"],
      ["Blurt team (bulk)", "Monthly invoice — BLURT payment + memo with Blurt tenant STONE address"],
      ["Bloodstone coordinator", "Credits quota, enables publish on namespaced keys"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("3. Economic Comparison — Blurt S3 vs Chain Mesh"),

  h2("3.1 Blurt baseline (Megadrive figures)"),
  p("Current cost: €22.80/month for 1.2 TB storage with free-tier bandwidth."),
  p("Effective rate: ~€0.019 per GiB-month (~$0.021 USD)."),

  h2("3.2 Proposed Bloodstone storage pricing"),
  p(
    "Target: match or beat €0.019/GiB-month in STONE equivalent, while routing value to mesh peers who replicate data."
  ),
  table(
    ["Tier", "Quota", "Indicative STONE price", "Notes"],
    [
      ["Blurt bulk (1.2 TB)", "1,228,800 MiB", "Quoted monthly in STONE at spot ≤ €22.80", "Primary partner rate"],
      ["Per-user free", "50–500 MiB", "Subsidized by Blurt bulk allocation", "Stakeholder multipliers"],
      ["Direct user overage", "Per GiB-month", "≤ €0.019 equivalent in STONE", "Paid via outpost or STONE wallet"],
      ["BSM1 anchor", "Per file revision", "Tx fee only", "Optional integrity proof"],
    ],
    [2000, 1800, 2800, 2760]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Exact STONE amounts float with market price — quoted as STONE/GiB-month at order time. Blurt receives a partner lock rate for bulk 1.2 TB comparable to current S3 spend."
  ),

  h2("3.3 Why this is compelling beyond price"),
  bullet("bullets", "Bytes replicated on mesh peers — not a single-provider bucket risk"),
  bullet("bullets", "BSM1 on-chain integrity proofs for audit and dispute resolution"),
  bullet("bullets", "Same storage layer powers APK recovery, white papers, and block archives — real utility, not speculative"),
  bullet("bullets", "STONE payments fund edge-of-network participants (aligned with Megadrive's praise of proportional miner economics)"),
  bullet("bullets", "Progressive decentralization: Blurt bulk tenant today → peer replication tomorrow"),

  h1("4. Implementation Roadmap"),

  table(
    ["Phase", "Deliverable", "Timeline"],
    [
      ["P0", "Raise mesh limits for Blurt tenant (256 MiB–1 GiB per file)", "Days"],
      ["P0", "Blurt bulk namespace + publish token + quota API", "1–2 weeks"],
      ["P1", "Blurt backend upload adapter (S3-compatible or direct mesh SDK)", "2–4 weeks"],
      ["P1", "BLURT outpost account + memo parser for storage credits", "2–3 weeks"],
      ["P2", "Byte-range proxy for HTML5 video progressive playback", "4–6 weeks"],
      ["P2", "Per-user quota dashboard in Blurt admin", "4 weeks"],
      ["P3", "HLS segment pipeline for long-form video", "8+ weeks"],
      ["P3", "Live ingest integration (external RTMP → post-record to mesh)", "Partner-dependent"],
    ],
    [1200, 5160, 3000]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("5. Risk & Honest Limits"),
  bullet("bullets", "Default 64 MiB cap blocks 161 MiB videos until operator raises limits — not a fundamental barrier"),
  bullet("bullets", "Live full-resolution streaming is not a drop-in replacement — needs buffer/segment layer"),
  bullet("bullets", "Mesh peer replication is growing; early phase still uses coordinator as primary catalog"),
  bullet("bullets", "BLURT→STONE rail requires outpost implementation — proposed, not yet live"),
  bullet("bullets", "Storage-specific STONE billing is a new utility SKU — mining economics doc covers issuance, not consumption pricing"),

  h1("6. Conclusion"),
  p(
    "Blurt's inquiry maps directly to Bloodstone's storage utility roadmap. The 64 MiB limit is policy, not protocol. Blurt can start with a bulk tenant model identical in UX to today's S3 bucket. Pre-recorded media fits Chain Mesh today with a modest limit raise and optional edge cache; live broadcast needs a streaming layer alongside mesh archive. STONE pricing can meet or beat €22.80/1.2 TB with a BLURT payment rail via outpost memo."
  ),
  p(
    "Megadrive is correct that storage completes the utility puzzle beside mining. Bloodstone welcomes Blurt as a primary storage partner and proposes a phased integration beginning with namespaced bulk tenancy, quota APIs, and partner-rate STONE billing."
  ),

  new Paragraph({
    spacing: { before: 400 },
    children: [new TextRun({ text: "Document version: 1.0 · July 2026", italics: true, size: 20 })],
  }),
  p("Related documents:"),
  linkPara(
    "Chain Mesh Storage White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  linkPara(
    "Mesh File Upload White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx"
  ),
  linkPara(
    "Economic Model White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Economic-Model-White-Paper.docx"
  ),
  linkPara("Network Data Portal", "https://bloodstonewallet.mytunnel.org/mining/network-data"),
  linkPara("Bloodstone downloads", "https://bloodstonewallet.mytunnel.org/downloads/"),
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
                  text: "Bloodstone × Blurt — Chain Mesh Storage Partnership",
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
  "/root/bloodstone-docs/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});