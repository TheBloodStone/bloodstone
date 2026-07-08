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

// Partner token is issued out-of-band only — never embed in public or mesh-hosted docs.
const TOKEN_PLACEHOLDER = "<your-partner-token-from-bloodstone-ops>";
const COORDINATOR = "https://bloodstonewallet.mytunnel.org";
const PORTAL = COORDINATOR + "/mining/network-data";

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
        text: "How to Send and Use Chain Mesh — Partner White Paper",
        size: 32,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · For Blurt backend operators and integrators",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "Bloodstone has issued Blurt a partner publish token for the Chain Mesh storage layer. With this token, Blurt can upload files, register manifests, and serve verified downloads to Blurt users — without an admin browser session and without exposing Bloodstone operator credentials."
  ),
  p(
    "This white paper is the practical guide: what the token does, how to send bytes into the mesh, how to read them back out in Blurt posts and players, and how the hybrid S3 + mesh path works if you keep your existing bucket."
  ),
  p(
    "Downloads and playback are public. Only writes under the assets/blurt/ namespace require the partner token."
  ),

  h1("1. The Partner Publish Token"),
  p(
    "The coordinator stores one shared secret (CHAIN_MESH_PUBLISH_TOKEN). Bloodstone issues Blurt's copy out-of-band — encrypted email, password manager share, or admin panel handoff. This public guide intentionally does not contain the token value."
  ),
  p(
    "Treat the token like an API password: store only in server-side secrets (environment variables, vault, or CI secrets). Rotate immediately if leaked. Never commit it to git, embed it in frontend JavaScript, or publish it to Chain Mesh or public downloads."
  ),
  h3("Token placeholder (replace with your issued secret)"),
  mono(TOKEN_PLACEHOLDER),
  h3("How to send the token on each request"),
  bullet("bullets", "HTTP header (recommended): X-Chain-Mesh-Publish-Token: <token>"),
  bullet("bullets", 'JSON body field: "publish_token": "<token>"'),
  bullet("bullets", "Environment variable for cron scripts: CHAIN_MESH_PUBLISH_TOKEN"),
  h3("What the token allows"),
  table(
    ["Allowed", "Not allowed"],
    [
      [
        "Upload chunks via POST /api/chain-mesh/partner/upload",
        "Write keys outside assets/blurt/ (e.g. downloads/, arbitrary assets/)",
      ],
      [
        "Publish manifests via POST /api/chain-mesh/partner/publish-asset",
        "Bypass admin review queue for non-Blurt community uploads",
      ],
      [
        "Overwrite an existing assets/blurt/… key with a new file revision",
        "Access Bloodstone miner admin panel or wallet keys",
      ],
      [
        "Optional BSM1 on-chain anchor per file (integrity proof)",
        "Unlimited file size without coordinator limit configuration",
      ],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("2. Chain Mesh in One Page"),
  p(
    "Files are split into 256 KiB content-addressed chunks. Each chunk is identified by SHA-256. A manifest records chunk order, whole-file SHA-256, Merkle root, MIME type, and display name. The coordinator catalogs manifests; mesh peers (phones, PCs, VPS) replicate chunks and can serve them on LAN port 18341."
  ),
  bullet("bullets", "Send = upload chunks + publish manifest at a stable asset key"),
  bullet("bullets", "Use = GET manifest metadata or GET download URL (public, no token)"),
  bullet("bullets", "Replace = publish again at the same asset key (new revision, same URL path)"),
  p("Coordinator base URL: " + COORDINATOR),
  p("Network Data Portal (human UI for testing): " + PORTAL),

  new Paragraph({ children: [new PageBreak()] }),

  h1("3. Asset Key Naming (Blurt Namespace)"),
  p(
    "Every Blurt file must live under assets/blurt/. Pick a layout and keep it consistent so posts can embed predictable URLs."
  ),
  table(
    ["Pattern", "Example", "Use case"],
    [
      ["assets/blurt/s3/<s3-key>", "assets/blurt/s3/uploads/user42/clip.mp4", "S3 mirror cron (default)"],
      ["assets/blurt/media/<post_id>/<file>", "assets/blurt/media/99182/screen.mp4", "Direct backend upload"],
      ["assets/blurt/users/<account>/<file>", "assets/blurt/users/alice/avatar.png", "Per-user namespace"],
      ["assets/blurt/hls/<id>/seg000.ts", "assets/blurt/hls/live42/seg000.ts", "Optional HLS segments (roadmap)"],
    ],
    [2800, 4160, 2400]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Rule: asset_key must start with assets/blurt/. The partner API rejects any other prefix even with a valid token."
  ),

  h1("4. How to Send Files to the Mesh"),
  h2("4.1 Option A — S3 → Mesh mirror cron (recommended if you already use S3)"),
  p(
    "Keep Blurt's S3 bucket as the primary upload path. A cron job copies new or changed objects into the mesh for integrity, replication, and optional on-chain anchors."
  ),
  bullet("numbers", "User uploads in Blurt UI → Blurt backend PUTs to S3 (unchanged)"),
  bullet("numbers", "Cron runs blurt-s3-mesh-mirror.py on Blurt or Bloodstone infrastructure"),
  bullet("numbers", "Script reads S3 object, chunks it, uploads via partner APIs, publishes manifest"),
  bullet("numbers", "Mesh key defaults to assets/blurt/s3/<original-s3-key>"),
  bullet("numbers", "State file tracks S3 ETag — skips unchanged objects on the next run"),
  h3("Environment"),
  mono("export AWS_ACCESS_KEY_ID=…"),
  mono("export AWS_SECRET_ACCESS_KEY=…"),
  mono("export AWS_REGION=eu-central-1"),
  mono("export CHAIN_MESH_PUBLISH_TOKEN=" + TOKEN_PLACEHOLDER),
  mono("export BLOODSTONE_COORDINATOR=" + COORDINATOR),
  h3("Example cron"),
  mono("python3 blurt-s3-mesh-mirror.py \\"),
  mono("  --bucket YOUR_BUCKET \\"),
  mono("  --prefix uploads/ \\"),
  mono("  --mode remote \\"),
  mono("  --state-file /var/lib/blurt/s3-mesh-mirror.json"),
  p(
    "Script source: request a copy from Bloodstone or use the path documented in the S3 + Mesh Integration Operations Guide. Flags: --dry-run, --force, --no-anchor, --limit N, --max-bytes N."
  ),

  h2("4.2 Option B — Direct partner HTTP API (Blurt backend)"),
  p("Two-step flow: upload all chunks, then register the manifest."),
  h3("Step 1 — Upload chunks"),
  mono("POST " + COORDINATOR + "/api/chain-mesh/partner/upload"),
  mono("Headers: Content-Type: application/json"),
  mono("         X-Chain-Mesh-Publish-Token: <token>"),
  mono('Body: { "device_id": "blurt-backend", "peer_kind": "partner",'),
  mono('       "chunks": [{ "chunk_hash": "<sha256-hex>", "data_b64": "<base64>" }] }'),
  p("Upload in batches of 2 chunks per request (~1 MiB JSON limit on strict proxies). Chunk size is 256 KiB except the last piece."),
  h3("Step 2 — Publish manifest"),
  mono("POST " + COORDINATOR + "/api/chain-mesh/partner/publish-asset"),
  mono('Body: { "publish_token": "<token>",'),
  mono('       "asset_key": "assets/blurt/media/99182/screen.mp4",'),
  mono('       "display_name": "screen.mp4", "mime_type": "video/mp4",'),
  mono('       "file_size": 168820736, "file_sha256": "<hex>", "merkle_root": "<hex>",'),
  mono('       "anchor": true,'),
  mono('       "chunks": [{ "chunk_hash": "...", "file_offset": 0, "size": 262144 }, ...] }'),
  p(
    "Your backend can compute chunk hashes and Merkle root with the same algorithm as the mirror script, or call Bloodstone for a reference implementation."
  ),

  h2("4.3 Option C — Network Data Portal (manual test)"),
  p(
    "For one-off tests, open the public portal, submit a file under assets/… (community queue) or use admin tools. Production Blurt traffic should use Option A or B with the partner token — not the public review queue."
  ),
  linkPara("Open Network Data Portal", PORTAL),

  new Paragraph({ children: [new PageBreak()] }),

  h1("5. How to Use Mesh Files in Blurt"),
  h2("5.1 Public download URL (primary integration point)"),
  mono("GET " + COORDINATOR + "/api/chain-mesh/asset/<asset_key>/download"),
  p("Example:"),
  linkPara(
    "Demo download",
    COORDINATOR + "/api/chain-mesh/asset/assets/blurt/s3/uploads/demo.mp4/download"
  ),
  p(
    "Store asset_key in Blurt post metadata when the upload completes. Render posts with this HTTPS URL instead of (or alongside) the S3 URL during migration."
  ),

  h2("5.2 Video and audio embed (HTTP Range)"),
  p(
    "The download endpoint supports Range requests (206 Partial Content). HTML5 <video> and <audio> scrub and buffer the same way as S3 VOD."
  ),
  mono('<video controls src="' + COORDINATOR + '/api/chain-mesh/asset/assets/blurt/s3/uploads/screen.mp4/download">'),
  mono("</video>"),
  table(
    ["Query / header", "Effect"],
    [
      ["Range: bytes=0-1048575", "206 Partial Content — first 1 MiB"],
      ["No Range", "200 OK full file, Accept-Ranges: bytes"],
      ["?inline=1", "Content-Disposition: inline for any MIME"],
      ["?attachment=1", "Force download attachment"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("5.3 Metadata and search (no token)"),
  mono("GET " + COORDINATOR + "/api/chain-mesh/asset/<asset_key>"),
  mono("GET " + COORDINATOR + "/api/chain-mesh/search?q=blurt&limit=50"),
  mono("GET " + COORDINATOR + "/api/chain-mesh/asset/<asset_key>/preview"),
  p(
    "Use metadata for file size, SHA-256, version label, chunk count, and optional on-chain anchor txid. Preview returns text snippet or image thumbnail when supported."
  ),

  h2("5.4 Blurt traffic dashboard (public JSON)"),
  mono("GET " + COORDINATOR + "/api/chain-mesh/partner/blurt/traffic"),
  linkPara("Blurt mesh traffic page", COORDINATOR + "/mining/blurt-mesh-traffic"),
  p(
    "Weekly, monthly, and yearly stats for assets/blurt/ downloads — useful for capacity planning and partner reporting."
  ),

  h2("5.5 Optional — users keep full files on device"),
  p(
    "Bloodstone miners and the Network Data Portal let end users pin a complete file plus all chunks on their phone or PC for offline backup and LAN sharing. This helps Blurt media survive coordinator rotation and improves peer recovery. No Blurt backend change is required; it is a client-side feature."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("6. Updating and Replacing Files"),
  p(
    "To ship a new version of the same post attachment, publish again at the same asset_key. The coordinator registers a new revision (new file_sha256, new chunk list). The download URL path stays the same; caches should key on ETag or file_sha256."
  ),
  bullet("bullets", "S3 mirror: object ETag change triggers re-mirror on next cron run"),
  bullet("bullets", "Direct API: call partner/publish-asset with the same asset_key and new manifest"),
  bullet("bullets", "Optional version field in manifest helps Blurt show revision history in admin UI"),

  h1("7. File Size Limits"),
  p(
    "Default coordinator policy is 64 MiB per file (256 chunks × 256 KiB). Blurt tenant limits are raised for partner media — typically 256 MiB to 1 GiB per file. Contact Bloodstone if a screen-share or recording exceeds your configured cap."
  ),
  mono("CHAIN_MESH_MAX_ASSET_BYTES=268435456   # 256 MiB (example)"),
  mono("CHAIN_MESH_MAX_ASSET_CHUNKS=1024       # up to ~1 GiB at 256 KiB chunks"),

  h1("8. Security Checklist"),
  bullet("bullets", "Store CHAIN_MESH_PUBLISH_TOKEN only in server-side secrets — never in Blurt frontend JavaScript"),
  bullet("bullets", "Rotate the token if compromised; Bloodstone updates secrets.conf and sends a new value"),
  bullet("bullets", "Partner token cannot write outside assets/blurt/ — community assets/ still uses admin review"),
  bullet("bullets", "Downloads are public by design; do not put private keys or unencrypted credentials in mesh objects"),
  bullet("bullets", "Use HTTPS only; coordinator URL is " + COORDINATOR),

  h1("9. Quick Start Checklist"),
  table(
    ["Step", "Action", "Owner"],
    [
      ["1", "Save publish token in Blurt secrets (see §1)", "Blurt ops"],
      ["2", "Choose key layout (§3) and test one file via partner API or mirror --dry-run", "Blurt backend"],
      ["3", "Confirm download URL plays in HTML5 player (§5.2)", "Blurt frontend"],
      ["4", "Deploy S3 mirror cron or wire backend upload adapter", "Blurt backend"],
      ["5", "Swap post embeds from S3 URL to mesh download URL", "Blurt frontend"],
      ["6", "Monitor /api/chain-mesh/partner/blurt/traffic", "Both teams"],
    ],
    [800, 6160, 2400]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("10. Support and Related Documents"),
  p(
    "For limit raises, token rotation, or integration review, contact the Bloodstone operator team via your existing Blurt partnership channel."
  ),
  linkPara(
    "Blurt Mesh Storage Partnership White Paper (economics & architecture)",
    COORDINATOR + "/downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx"
  ),
  linkPara(
    "S3 + Mesh Integration Operations Guide (mirror script, Range proxy, cron)",
    COORDINATOR + "/downloads/Bloodstone-Blurt-S3-Mesh-Integration-Operations-Guide.docx"
  ),
  linkPara(
    "Chain Mesh Storage White Paper (protocol & peer model)",
    COORDINATOR + "/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  linkPara(
    "Mesh File Upload White Paper (chunking, manifests, anchors)",
    COORDINATOR + "/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx"
  ),

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
                  text: "Blurt × Bloodstone — Mesh Send & Use (partner distribution)",
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
  "/root/bloodstone-docs/Bloodstone-Blurt-Mesh-Send-And-Use-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});