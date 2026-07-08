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

// Partner token is issued out-of-band only — never embed in public downloads or mesh docs.
const TOKEN_PLACEHOLDER = "<your-partner-token-from-bloodstone-ops>";
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
        text: "Blurt S3 + Chain Mesh Integration",
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
        text: "Operations Guide — Storage, Hash Rate Rental, ETH Escrow, Overflow",
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Internal / partner distribution (NOT chain-mesh anchored)",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "This guide documents the complete Blurt + Bloodstone hybrid storage integration built in July 2026. Blurt keeps its existing S3 bucket as the primary upload and serve path while Chain Mesh receives mirrored copies for integrity, peer replication, and optional BSM1 on-chain anchors."
  ),
  p(
    "Three components are now live on the Bloodstone coordinator: (1) an S3→mesh mirror script for Blurt cron jobs, (2) partner HTTP APIs that accept a publish token without admin login, and (3) a byte-range proxy on the mesh download endpoint so mirrored video plays like normal S3 VOD in HTML5 players."
  ),
  p(
    "This document is hosted on the public downloads server only. It is intentionally NOT published to Chain Mesh."
  ),

  h1("1. Architecture Overview"),
  h2("1.1 What each layer does"),
  table(
    ["Layer", "Role", "Live broadcast?", "Range / scrub?"],
    [
      ["Blurt S3 bucket", "Primary object storage for uploads and VOD", "No (object storage only)", "Yes (via S3/CDN)"],
      ["Blurt live ingest", "RTMP/WebRTC → HLS for real-time streams", "Yes", "Yes (HLS segments)"],
      ["Chain Mesh", "Content-addressed file storage + BSM1 anchors", "No", "Yes (byte-range proxy, July 2026)"],
    ],
    [2200, 4160, 1800, 1200]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("1.2 Hybrid flow (recommended phase 1)"),
  bullet("numbers", "User uploads in Blurt UI → Blurt backend PUTs to S3 (unchanged)"),
  bullet("numbers", "Cron runs blurt-s3-mesh-mirror.py → copies new/changed S3 objects to mesh"),
  bullet("numbers", "Mesh key: assets/blurt/s3/<original-s3-key>"),
  bullet("numbers", "Post can embed mesh VOD URL for playback with Range support, or keep S3 URL during migration"),
  bullet("numbers", "Live streams stay on existing ingest; post-stream MP4 can be mirrored to mesh"),

  h2("1.3 S3 vs mesh comparison"),
  table(
    ["Capability", "S3 (Blurt today)", "Chain Mesh (Bloodstone)"],
    [
      ["Finished file upload", "PUT → object key → HTTPS URL", "Chunk upload → manifest → download API"],
      ["161 MiB screen share", "Fits in bucket; static GET", "Blocked at 64 MiB default; fits after limit raise"],
      ["Integrity proof", "ETag / provider checksum", "SHA-256 + Merkle root + optional BSM1 anchor"],
      ["Replication", "Single provider region", "Content-addressed chunks on mesh peers"],
      ["VOD scrubbing", "HTTP Range native", "HTTP Range via coordinator proxy (built July 2026)"],
    ],
    [2800, 3280, 3280]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  new Paragraph({ children: [new PageBreak()] }),

  h1("2. Mesh Publish Token"),
  p(
    "The coordinator issues one partner publish token for Blurt bulk operations. Bloodstone delivers it out-of-band (not in this public operations guide). Treat it as a password — it allows chunk upload and manifest publish on keys under assets/blurt/."
  ),
  h3("Token placeholder (replace with your issued secret)"),
  mono(TOKEN_PLACEHOLDER),
  h3("How to send it"),
  bullet("bullets", "HTTP header: X-Chain-Mesh-Publish-Token: <token>"),
  bullet("bullets", 'JSON body field: "publish_token": "<token>"'),
  bullet("bullets", "Environment variable for mirror script: CHAIN_MESH_PUBLISH_TOKEN"),
  p(
    "Scope: partner APIs accept this token without an admin browser session. Manifest publish is restricted to asset keys starting with assets/blurt/."
  ),

  h1("3. Partner HTTP APIs"),
  p("Base URL: " + COORDINATOR),
  table(
    ["Endpoint", "Method", "Auth", "Purpose"],
    [
      ["/api/chain-mesh/partner/upload", "POST", "Publish token", "Upload content-addressed chunks (batch JSON)"],
      ["/api/chain-mesh/partner/publish-asset", "POST", "Publish token", "Register manifest + optional BSM1 anchor"],
      ["/api/chain-mesh/asset/<key>/download", "GET, HEAD", "Public", "Download or stream file (Range-aware)"],
      ["/api/chain-mesh/asset/<key>", "GET", "Public", "Asset manifest metadata"],
    ],
    [3600, 900, 1800, 3060]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("3.1 Chunk upload payload (partner/upload)"),
  mono('POST /api/chain-mesh/partner/upload'),
  mono("Headers: Content-Type: application/json"),
  mono("         X-Chain-Mesh-Publish-Token: <token>"),
  mono('Body: { "device_id": "blurt-s3-mirror", "peer_kind": "partner",'),
  mono('       "chunks": [{ "chunk_hash": "<sha256>", "data_b64": "<base64>" }] }'),
  p("Chunks are 256 KiB content-addressed pieces. Upload in batches of 2 to stay under proxy size limits."),

  h2("3.2 Manifest publish payload (partner/publish-asset)"),
  mono('POST /api/chain-mesh/partner/publish-asset'),
  mono('Body: { "publish_token": "<token>", "asset_key": "assets/blurt/s3/...",'),
  mono('       "display_name": "screen.mp4", "mime_type": "video/mp4",'),
  mono('       "file_size": 168820736, "file_sha256": "<hex>", "merkle_root": "<hex>",'),
  mono('       "anchor": true, "chunks": [{ "chunk_hash": "...", "file_offset": 0, "size": 262144 }] }'),

  new Paragraph({ children: [new PageBreak()] }),

  h1("4. S3 → Mesh Mirror Script"),
  h2("4.1 Script location"),
  mono("/root/blurt-s3-mesh-mirror.py"),
  p(
    "Standalone Python script (no boto3 dependency). Uses requests + AWS Signature V4 for S3 ListObjectsV2 and GetObject. Tracks ETags in a state file to skip unchanged objects."
  ),

  h2("4.2 Environment variables"),
  table(
    ["Variable", "Required", "Description"],
    [
      ["AWS_ACCESS_KEY_ID", "Yes", "S3 read credentials"],
      ["AWS_SECRET_ACCESS_KEY", "Yes", "S3 read credentials"],
      ["AWS_REGION", "Yes", "Bucket region (e.g. eu-central-1)"],
      ["CHAIN_MESH_PUBLISH_TOKEN", "Yes (remote)", "Partner token (see §2)"],
      ["BLOODSTONE_COORDINATOR", "Remote", "Default: " + COORDINATOR],
      ["AWS_ENDPOINT_URL", "Optional", "S3-compatible endpoint (MinIO, etc.)"],
      ["CHAIN_MESH_MAX_ASSET_BYTES", "Optional", "Skip threshold (default 64 MiB)"],
      ["BLURT_S3_MESH_STATE", "Optional", "State file path override"],
    ],
    [2800, 1200, 5360]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("4.3 Example cron (remote mode on Blurt infrastructure)"),
  mono("export AWS_ACCESS_KEY_ID=…"),
  mono("export AWS_SECRET_ACCESS_KEY=…"),
  mono("export AWS_REGION=eu-central-1"),
  mono("export CHAIN_MESH_PUBLISH_TOKEN=" + TOKEN_PLACEHOLDER),
  mono("export BLOODSTONE_COORDINATOR=" + COORDINATOR),
  mono(""),
  mono("python3 blurt-s3-mesh-mirror.py \\"),
  mono("  --bucket YOUR_BUCKET \\"),
  mono("  --prefix uploads/ \\"),
  mono("  --mode remote \\"),
  mono("  --state-file /var/lib/blurt/s3-mesh-mirror.json"),

  h2("4.4 Useful flags"),
  table(
    ["Flag", "Effect"],
    [
      ["--dry-run --key uploads/foo.mp4", "Simulate one object without AWS creds"],
      ["--force", "Re-mirror even if S3 ETag unchanged"],
      ["--no-anchor", "Skip BSM1 on-chain anchor (faster bulk backfill)"],
      ["--limit 50", "Cap objects processed per run"],
      ["--json", "Machine-readable summary on stdout"],
      ["--max-bytes N", "Skip files larger than N bytes"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("4.5 S3 key → mesh key mapping"),
  p("Default mapping:"),
  mono("S3:  uploads/user123/screen.mp4"),
  mono("Mesh: assets/blurt/s3/uploads/user123/screen.mp4"),
  p(
    "Override namespace with --mesh-prefix (default assets/blurt/s3/). State file records s3://bucket/key → mesh_key + ETag for incremental sync."
  ),

  h2("4.6 File size limit"),
  p(
    "Default coordinator policy: CHAIN_MESH_MAX_ASSET_BYTES = 64 MiB. A 161 MiB screen-share recording is skipped until Bloodstone raises limits for the Blurt tenant, e.g.:"
  ),
  mono("CHAIN_MESH_MAX_ASSET_BYTES=268435456   # 256 MiB"),
  mono("CHAIN_MESH_MAX_ASSET_CHUNKS=1024       # up to ~1 GiB at 256 KiB chunks"),

  new Paragraph({ children: [new PageBreak()] }),

  h1("5. Byte-Range VOD Proxy"),
  p(
    "As of July 2026 the mesh download endpoint supports HTTP Range requests. Browsers send Range headers for HTML5 <video> scrubbing and buffering — the coordinator loads only the chunk slices covering the requested byte range instead of reconstructing the entire file."
  ),

  h2("5.1 Endpoint"),
  mono("GET|HEAD /api/chain-mesh/asset/<asset_key>/download"),
  linkPara("Example (public)", COORDINATOR + "/api/chain-mesh/asset/assets/blurt/s3/uploads/demo.mp4/download"),

  h2("5.2 Response behavior"),
  table(
    ["Request", "Response"],
    [
      ["No Range header", "200 OK — full file, Accept-Ranges: bytes"],
      ["Range: bytes=0-1048575", "206 Partial Content + Content-Range header"],
      ["Invalid / unsatisfiable range", "416 Range Not Satisfiable"],
      ["HEAD", "Headers only (Content-Length or Content-Range)"],
    ],
    [3600, 5760]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("5.3 Inline vs attachment"),
  table(
    ["Condition", "Content-Disposition"],
    [
      ["video/* or audio/* MIME (default)", "inline — HTML5 player works"],
      ["?inline=1", "inline for any file type"],
      ["?attachment=1", "attachment — force download"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("5.4 Blurt HTML embed"),
  mono('<video controls src="' + COORDINATOR + '/api/chain-mesh/asset/assets/blurt/s3/uploads/screen.mp4/download">'),
  mono("</video>"),
  p(
    "After the mirror cron copies a recording from S3, swap the post embed URL from the S3 HTTPS link to the mesh download URL above. Playback behavior matches S3 VOD Range streaming."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("6. Hash Rate Rental Program"),
  p(
    "Bloodstone operates live Stratum pools (neoscrypt, yespower, sha256d) on the VPS coordinator. The Hash Rate Rental Program lets miners with spare capacity sell proven work to buyers who need temporary PoW — for chain security, burst mining, render-adjacent workloads, or partner integrations (e.g. Blurt infrastructure)."
  ),
  h2("6.1 Roles"),
  table(
    ["Role", "Action", "Payment"],
    [
      ["Seller (lessor)", "Points rig at rental stratum; delivers shares to buyer job", "Receives ETH from escrow on delivery"],
      ["Buyer (lessee)", "Posts rental order: algo, target hashrate, duration, max price", "Locks ETH in non-custodial escrow (see §7)"],
      ["Pool coordinator", "Validates shares, meters delivered work, triggers escrow release", "Platform fee (e.g. 2%) in ETH"],
    ],
    [1600, 4960, 2800]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("6.2 Rental order fields"),
  bullet("bullets", "algorithm — neoscrypt | yespower | sha256d"),
  bullet("bullets", "target_hashrate — requested H/s (e.g. 500 MH/s neoscrypt)"),
  bullet("bullets", "duration — wall-clock window (hours) or share quota"),
  bullet("bullets", "max_price_eth — buyer's ETH budget cap"),
  bullet("bullets", "payout_address — seller STONE address (share accounting) + seller ETH address (escrow recipient)"),
  bullet("bullets", "worker_prefix — stratum worker name scoped to rental ID"),

  h2("6.3 Stratum routing"),
  p("Existing VPS pool ports (July 2026):"),
  mono("neoscrypt  → stratum+tcp://<host>:3437"),
  mono("yespower   → stratum+tcp://<host>:3438"),
  mono("sha256d    → stratum+tcp://<host>:3429"),
  p(
    "Rental mode adds a virtual pool namespace: worker name rental/<order_id>.<seller_stone_address>. Seller points hardware at the coordinator; the pool attributes shares to the rental order instead of solo/pool mining. Buyer is billed only for accepted shares in the rental window."
  ),

  h2("6.4 Settlement flow"),
  bullet("numbers", "Buyer creates rental order on marketplace UI → locks ETH in escrow contract"),
  bullet("numbers", "Seller accepts order → receives stratum credentials + rental worker prefix"),
  bullet("numbers", "Pool meters accepted shares each interval (e.g. 15 min)"),
  bullet("numbers", "Escrow contract releases ETH pro-rata: (delivered_hashrate / ordered_hashrate) × tranche"),
  bullet("numbers", "On completion or timeout: remaining escrow returned to buyer; seller paid for delivered work"),
  bullet("numbers", "Disputes: escrow holds until share log attestation from pool coordinator is confirmed on-chain or via signed pool receipt"),

  h2("6.5 Pricing model (indicative)"),
  table(
    ["Component", "Basis", "Notes"],
    [
      ["Seller rate", "ETH per GH/s-hour", "Market-set; floor from electricity + rig depreciation"],
      ["Platform fee", "2% of escrow release", "Funds pool ops + metering infrastructure"],
      ["Minimum order", "1 hour · 100 MH/s", "Prevents dust rentals"],
      ["Payout asset", "ETH (primary)", "STONE settlement optional via DEX swap (roadmap)"],
    ],
    [2200, 2800, 4360]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  new Paragraph({ children: [new PageBreak()] }),

  h1("7. DEX-Style Non-Custodial ETH Wallet"),
  p(
    "Payments for hash rate rentals use the same trust model as Bloodstone DEX name trades: the platform never custodies buyer funds. ETH is locked in an escrow smart contract (EVM) or hash-time-locked contract (HTLC) pair; release is conditional on pool-attested delivery."
  ),
  h2("7.1 Wallet architecture"),
  table(
    ["Layer", "Technology", "Custody"],
    [
      ["Buyer wallet", "MetaMask / WalletConnect / injected EIP-1193 provider", "User holds keys — non-custodial"],
      ["Seller wallet", "Any ETH address (hardware or browser)", "User holds keys — non-custodial"],
      ["Escrow", "Smart contract on Ethereum L1 or L2 (e.g. Base, Arbitrum)", "Contract holds ETH until conditions met"],
      ["Bloodstone UI", "bloodstone-dex pattern — session links STONE web wallet + ETH address", "No private keys stored server-side"],
    ],
    [2200, 4160, 3000]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("7.2 Escrow states"),
  bullet("bullets", "Created — buyer approves ETH transfer into escrow; order visible to sellers"),
  bullet("bullets", "Active — seller mining; pool streams share receipts to coordinator"),
  bullet("bullets", "Release — contract pays seller ETH tranche; logs tx hash on rental order"),
  bullet("bullets", "Completed — full duration delivered or buyer cancels unfilled remainder"),
  bullet("bullets", "Refunded — dispute timeout or insufficient delivery; unspent ETH returned to buyer"),

  h2("7.3 Integration with existing DEX"),
  p(
    "Bloodstone DEX today handles atomic STONE name trades via bloodstone-dex/atomic_trade.py. The rental marketplace extends this pattern:"
  ),
  bullet("numbers", "Order book DB (dex_db) gains rental order type hashrate_rental"),
  bullet("numbers", "ETH escrow contract address + release tx hashes stored per order"),
  bullet("numbers", "User links ETH address in wallet profile (alongside STONE web wallet login)"),
  bullet("numbers", "UI hosted at /dex/rentals or /mining/rentals with shared wallet session"),
  linkPara("Bloodstone DEX (live)", COORDINATOR + "/dex/"),

  h2("7.4 Security properties"),
  bullet("bullets", "Non-custodial: Bloodstone cannot move escrowed ETH without contract rules"),
  bullet("bullets", "Pool receipts signed by coordinator key; contract verifies signature or oracle attestation"),
  bullet("bullets", "Buyer sees live hashrate meter before each escrow tranche releases"),
  bullet("bullets", "ETH gas for escrow deploy/release paid by platform on first release (fee recovery via 2% take)"),

  new Paragraph({ children: [new PageBreak()] }),

  h1("8. Mesh Overflow Server & Cover Cost"),
  p(
    "Chain Mesh is the primary durable store, but coordinator policy limits (default 64 MiB per asset), replication lag, or hot VOD edge requirements can exceed what mesh peers serve comfortably. An overflow server provides centralized object storage as a safety net — similar to Blurt's S3 tier — while mesh retains the integrity catalog."
  ),

  h2("8.1 Three-tier storage model"),
  table(
    ["Tier", "When used", "Serve path"],
    [
      ["1 — Chain Mesh", "Default; files within policy limits; replicated chunks", "/api/chain-mesh/asset/<key>/download (Range-aware)"],
      ["2 — Overflow server", "File exceeds mesh limits; mesh chunks missing; hot edge cache", "/api/overflow/asset/<key> or CDN in front"],
      ["3 — Partner S3 (Blurt)", "Blurt's existing bucket during hybrid migration", "Blurt S3 HTTPS URL (unchanged)"],
    ],
    [1800, 4560, 3000]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("8.2 Overflow trigger conditions"),
  bullet("bullets", "file_size > CHAIN_MESH_MAX_ASSET_BYTES for tenant"),
  bullet("bullets", "mesh replication incomplete — fewer than MIN_PEER_CHUNKS available"),
  bullet("bullets", "operator flags asset as overflow_only (live stream archive awaiting mesh backfill)"),
  bullet("bullets", "tenant quota exceeded on mesh — spill to overflow until STONE/ETH cover paid"),

  h2("8.3 Cover cost (data hosting fee)"),
  p(
    "When data lands on the overflow server, the tenant pays a cover cost — a per-GB-month charge that funds VPS disk, bandwidth, and Range-proxy infrastructure. This is separate from mesh STONE storage quotes and applies only to overflow bytes."
  ),
  table(
    ["Item", "Indicative rate", "Purpose"],
    [
      ["Overflow storage", "€0.025 / GiB-month (or ETH equivalent)", "Disk + backup on coordinator VPS"],
      ["Overflow egress", "€0.01 / GiB served (after free tier)", "Bandwidth for VOD Range responses"],
      ["Mesh-primary storage", "≤ €0.019 / GiB-month STONE", "Peer-replicated tier (partnership rate)"],
      ["Cover minimum", "€1.00 / month per active overflow tenant", "Account maintenance"],
    ],
    [2800, 3280, 3280]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Cover cost is debited from the tenant's linked ETH wallet (same non-custodial profile as §7) or STONE quota via outpost memo storage:<address>:<bytes>. If cover payment lapses, overflow objects become read-only; mesh manifest remains for integrity audit."
  ),

  h2("8.4 Manifest extension (overflow pointer)"),
  p("Mesh catalog records integrity even when bytes live on overflow:"),
  mono('manifest.overflow = {'),
  mono('  "backend": "bloodstone-overflow",'),
  mono('  "url": "https://overflow.bloodstonewallet.mytunnel.org/objects/<key>",'),
  mono('  "file_sha256": "<same as mesh manifest>",'),
  mono('  "cover_cost_eth_month": "0.025",'),
  mono('  "replicate_to_mesh": true   // background job when limits rise'),
  mono("}"),
  p(
    "Download API checks overflow pointer when mesh chunks are absent or when Range hot-path is configured to prefer overflow edge. Byte-range proxy logic is shared between mesh reconstruct and overflow passthrough."
  ),

  h2("8.5 Blurt hybrid with overflow"),
  bullet("numbers", "New upload → S3 (primary) + mesh mirror cron (integrity)"),
  bullet("numbers", "File > mesh limit → overflow server + cover cost invoice in ETH"),
  bullet("numbers", "VOD embed prefers mesh URL; falls back to overflow URL with same Range semantics"),
  bullet("numbers", "Hash rate rental revenue (ETH) can auto-pay overflow cover for same tenant wallet"),

  h1("9. Migration Phases"),
  table(
    ["Phase", "Action", "Live impact"],
    [
      ["P0", "Issue publish token; raise mesh limits for Blurt tenant", "None"],
      ["P1", "Deploy mirror cron (S3 → mesh for new uploads)", "None — S3 still primary"],
      ["P2", "Byte-range proxy live (done)", "Mesh VOD scrubbing works"],
      ["P3", "Blurt post renderer: mesh URL for mirrored media", "Improved integrity path"],
      ["P4", "Bulk backfill existing S3 objects; optional S3 retirement", "Planned cutover"],
      ["P5", "Hash rate rental marketplace + ETH escrow (§6–7)", "New revenue stream for miners"],
      ["P6", "Overflow server + cover cost billing (§8)", "Large media + mesh gap coverage"],
    ],
    [800, 5560, 3000]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("10. Economics (reminder)"),
  p("Blurt baseline (Megadrive): ~€22.80/month for 1.2 TB S3."),
  p("Bloodstone target: ≤ €0.019/GiB-month in STONE equivalent for bulk Blurt tenant storage."),
  p("BLURT → STONE payment memo format:"),
  mono("MEMO: storage:<STONE_ADDRESS>:<bytes>"),
  p("Example: storage:STNabc123…:1073741824 credits 1 GiB to that wallet's storage quota."),

  h1("11. Related Public Documents (on mesh)"),
  linkPara(
    "Blurt S3 Livestream & Chain Mesh Technical Note",
    COORDINATOR + "/downloads/Bloodstone-Blurt-S3-Livestream-And-Mesh-Storage.docx"
  ),
  linkPara(
    "Blurt Mesh Storage Partnership White Paper",
    COORDINATOR + "/downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx"
  ),
  linkPara(
    "Mesh File Upload White Paper",
    COORDINATOR + "/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx"
  ),
  p("This operations guide is downloads-only and is not chain-mesh anchored."),

  h1("12. Security Notes"),
  bullet("bullets", "Rotate the publish token if compromised — update secrets.conf and Blurt cron env"),
  bullet("bullets", "S3 credentials for mirror script need read-only (ListBucket + GetObject) scope"),
  bullet("bullets", "Partner publish cannot write outside assets/blurt/ namespace"),
  bullet("bullets", "Do not commit the publish token to public git repositories"),
  bullet("bullets", "ETH escrow contracts must be audited before mainnet rental launch"),
  bullet("bullets", "Overflow server holds plaintext bytes — encrypt at rest for sensitive tenant data"),

  new Paragraph({
    spacing: { before: 400 },
    children: [new TextRun({ text: "Document version: 1.1 · July 2026 · Downloads only", italics: true, size: 20 })],
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
                  text: "Blurt S3 + Mesh Integration — Operations Guide (confidential)",
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
  "/root/bloodstone-docs/Bloodstone-Blurt-S3-Mesh-Integration-Operations-Guide.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});