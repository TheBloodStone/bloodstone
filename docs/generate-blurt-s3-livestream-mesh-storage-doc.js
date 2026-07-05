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
        text: "Blurt S3 Livestream & Bloodstone Chain Mesh",
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
        text: "How Media Is Handled Today — and What Changes With Mesh Storage",
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Technical note for Blurt partnership (Megadrive inquiry)",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "This document answers how livestream and media from an S3 bucket are handled today in the Blurt ecosystem, what Bloodstone Chain Mesh does instead, and where the two paths overlap or diverge. Bloodstone does not currently operate Blurt's S3 livestream pipeline. Chain Mesh provides durable file storage and verified download — not sub-second live broadcast."
  ),
  p(
    "For Blurt's stated economics (~€22.80/month for 1.2 TB S3), recorded media (screen shares, attachments, VOD) maps cleanly to mesh storage once per-file limits are raised. Live broadcast should continue to use a dedicated ingest stack; mesh can archive recordings after streams end."
  ),

  h1("1. What Bloodstone Handles Today (This Infrastructure)"),
  p(
    "The Bloodstone VPS codebase contains no S3 client, no livestream ingest (RTMP/WebRTC), and no HLS segment server. Media on Chain Mesh follows a file-storage model:"
  ),
  bullet("numbers", "Upload: file chunked into 256 KiB content-addressed pieces via POST /api/chain-mesh/upload"),
  bullet("numbers", "Catalog: manifest registered at a stable asset key (e.g. assets/blurt/media/…)"),
  bullet("numbers", "Download: GET /api/chain-mesh/asset/<key>/download reconstructs the full file server-side"),
  bullet("numbers", "Delivery: Flask send_file with as_attachment=True — optimized for download, not inline streaming"),
  bullet("numbers", "No HTTP Range request support — browsers cannot scrub progressive video without buffering the whole file"),
  bullet("numbers", "No live path — only completed files exist in the mesh catalog"),

  h2("1.1 Chain Mesh download flow (technical)"),
  table(
    ["Step", "Component", "Behavior"],
    [
      ["1", "Chunk store", "SHA-256 addressed blobs on coordinator + peer replication"],
      ["2", "Manifest API", "Ordered chunk list, Merkle root, optional BSM1 on-chain anchor"],
      ["3", "reconstruct_asset_bytes()", "Loads all chunks, concatenates, verifies size/hash"],
      ["4", "send_file(BytesIO)", "Entire blob returned in one HTTP response"],
    ],
    [800, 2800, 5760]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Default publish limits: 64 MiB per file (CHAIN_MESH_MAX_ASSET_BYTES), 256 chunks — policy defaults, not protocol ceilings. A 161 MiB screen-share recording exceeds the default but fits once operator limits are raised for a Blurt tenant."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("2. What Blurt Likely Has Today (S3 Bucket)"),
  p(
    "Blurt.blog application source is not hosted on the Bloodstone VPS. The following is inferred from the Blurt team's stated costs (~€22.80/month, 1.2 TB), Megadrive's Discord questions, and the public Blurt media ecosystem — and should be confirmed with Blurt backend operators."
  ),

  h2("2.1 S3 bucket role"),
  table(
    ["Function", "Typical implementation"],
    [
      ["Object storage", "Images, MP4/WebM recordings, screen shares uploaded via Blurt UI"],
      ["Backend", "Blurt server PUTs objects to S3; stores URL or key in post metadata"],
      ["Frontend", "Embeds media via HTTPS URL to S3 or CDN in front of S3"],
      ["Bandwidth", "Megadrive cited free-tier egress on current provider"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("2.2 Livestream vs S3 — important distinction"),
  p(
    "S3 is object storage. It does not natively 'livestream.' Live video requires a separate real-time pipeline:"
  ),
  bullet("bullets", "Broadcaster → RTMP or WebRTC ingest"),
  bullet("bullets", "Encoder/transcoder → HLS or DASH segments (sub-second to few-second latency)"),
  bullet("bullets", "Edge/CDN serves .m3u8 playlist + .ts segments to viewers"),
  bullet("bullets", "After stream ends: recording/segments may be copied to S3 for VOD replay"),

  h3("Blurt Media / PeerTube pattern"),
  p(
    "The public Blurt ecosystem includes Blurt Media (PeerTube-based). PeerTube supports S3 as remote object storage for recorded segments and VOD — not as the live broadcast engine. See PeerTube remote storage documentation."
  ),
  linkPara(
    "PeerTube — Remote storage (S3)",
    "https://docs.joinpeertube.org/maintain/remote-storage"
  ),
  p(
    "Practical interpretation: Blurt's S3 bucket holds finished uploads and archived recordings. Live broadcast (if offered) runs through ingest + HLS elsewhere; S3 stores the replay assets."
  ),

  h2("2.3 Megadrive's 161 MiB screen-share example"),
  p(
    "A 4-minute screen-share at 161 MiB is a completed file upload to S3 — not a live HLS feed. It is served as a static object via HTTPS GET (often with Range support from S3/CDN). This is VOD, not livestream."
  ),

  h1("3. Side-by-Side Comparison"),
  table(
    ["Mode", "S3 bucket (Blurt today)", "Chain Mesh (Bloodstone today)"],
    [
      ["Upload finished file", "PUT → object key → URL in post", "Chunk upload → mesh key → catalog entry"],
      ["Playback / download", "HTTPS GET; Range requests common", "Full reconstruct; no Range; attachment download"],
      ["Live broadcast", "Separate ingest (e.g. PeerTube/RTMP); S3 for replay", "Not supported"],
      ["161 MiB screen share", "Fits in bucket; served as static media", "Blocked at 64 MiB default; fits after limit raise"],
      ["Integrity proof", "ETag / provider checksum", "SHA-256 + Merkle root + optional BSM1 on-chain anchor"],
      ["Replication", "Single provider region", "Content-addressed chunks on mesh peers"],
    ],
    [2200, 3580, 3580]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  new Paragraph({ children: [new PageBreak()] }),

  h1("4. Recommended Architecture for Blurt + Bloodstone"),
  p(
    "Do not try to replace live ingest with Chain Mesh. Use mesh for durable storage and integrity; keep live on a streaming layer."
  ),

  h2("4.1 Target diagram"),
  p("[Live path]"),
  bullet("numbers", "Broadcaster → RTMP/WebRTC ingest → HLS edge (low latency)"),
  bullet("numbers", "Viewers watch via HLS player (PeerTube or existing Blurt live UI)"),
  bullet("numbers", "After stream ends → export MP4 or HLS archive → upload to Chain Mesh (or keep S3 during migration)"),

  p("[Recorded media / posts path]"),
  bullet("numbers", "User uploads in Blurt UI → Blurt backend"),
  bullet("numbers", "Backend publishes to assets/blurt/media/<post_id>/… on mesh"),
  bullet("numbers", "Post embeds Bloodstone download URL or Blurt proxy URL"),
  bullet("numbers", "Optional: byte-range proxy in front of mesh for HTML5 <video> scrubbing (roadmap)"),

  h2("4.2 What to confirm with Blurt backend team"),
  table(
    ["Question", "Why it matters"],
    [
      ["Is live on PeerTube (blurt.media) or another provider?", "Determines ingest stack to keep"],
      ["Does blurt.blog embed direct S3 URLs or only iframes?", "Migration path for post renderer"],
      ["Is a CDN (CloudFront, etc.) in front of the bucket?", "Latency and Range behavior for VOD"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("5. Migration Phases"),
  table(
    ["Phase", "Scope", "Live impact"],
    [
      ["P0", "Raise mesh limits for Blurt tenant; bulk namespace", "None — storage only"],
      ["P1", "Blurt backend upload adapter (S3 → mesh for new posts)", "None"],
      ["P2", "Byte-range proxy for mesh VOD playback", "Improves recorded video UX"],
      ["P3", "Post-stream archive: live ingest → mesh MP4", "Live unchanged; replay on mesh"],
      ["P4", "HLS segment keys on mesh (assets/blurt/hls/…)", "Optional VOD optimization"],
    ],
    [1000, 5160, 3200]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("6. Honest Limits"),
  bullet("bullets", "Bloodstone does not operate Blurt's S3 bucket or livestream ingest today"),
  bullet("bullets", "Chain Mesh is not a drop-in live CDN replacement"),
  bullet("bullets", "S3 excels at static objects + Range; mesh excels at integrity + peer replication"),
  bullet("bullets", "Megadrive's storage economics proposal (STONE ≤ €22.80/1.2 TB) applies to archived bytes, not live egress"),
  bullet("bullets", "Exact Blurt.blog wiring must be confirmed by Blurt operators — this doc states inferred architecture"),

  h1("7. Related Documents"),
  linkPara(
    "Blurt Mesh Storage Partnership White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx"
  ),
  linkPara(
    "Chain Mesh File Upload White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx"
  ),
  linkPara(
    "Chain Mesh Storage White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  linkPara("Network Data Portal", "https://bloodstonewallet.mytunnel.org/mining/network-data"),

  new Paragraph({
    spacing: { before: 400 },
    children: [new TextRun({ text: "Document version: 1.0 · July 2026", italics: true, size: 20 })],
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
                  text: "Blurt S3 Livestream & Chain Mesh — Technical Note",
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
  "/root/bloodstone-docs/Bloodstone-Blurt-S3-Livestream-And-Mesh-Storage.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});