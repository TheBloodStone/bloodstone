#!/usr/bin/env node
/** Bloodstone Chain Mesh Storage white paper — sharded redundant assets with on-chain anchors. */
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
function table(headers, rows) {
  const colCount = headers.length;
  const tableWidth = 9360;
  const colWidth = Math.floor(tableWidth / colCount);
  const columnWidths = Array(colCount).fill(colWidth);
  const headerRow = new TableRow({
    children: headers.map(
      (text) =>
        new TableCell({
          borders,
          width: { size: colWidth, type: WidthType.DXA },
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
          (text) =>
            new TableCell({
              borders,
              width: { size: colWidth, type: WidthType.DXA },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun(String(text))] })],
            })
        ),
      })
  );
  return new Table({
    width: { size: tableWidth, type: WidthType.DXA },
    columnWidths,
    rows: [headerRow, ...dataRows],
  });
}

const children = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: "Bloodstone Storage Layer", size: 52, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "White Paper — Chain Mesh, Asset Library, and On-Chain Verification",
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [new TextRun({ text: "July 2026 · Protocol v1.1 (BSM1)", size: 24, italics: true })],
  }),

  h1("Executive Summary"),
  p(
    "Bloodstone Storage Layer is the network's decentralized file system. It combines Chain Mesh (content-addressed 256 KiB chunks " +
      "replicated across miners, browsers, and Android nodes) with a Mesh Asset Library (catalog, preview, download, version history) " +
      "and optional BSM1 on-chain anchors that commit each manifest's Merkle root to the Bloodstone blockchain."
  ),
  p(
    "Complete files never live inside blocks. The chain records what should exist — asset keys, hashes, and Merkle roots — while " +
      "the mesh stores the bytes off-chain. If the central downloads VPS is unreachable, peers reconstruct releases from collective " +
      "storage: Android APKs, white papers, HTML pages, block archives, and pool artifacts alike."
  ),
  p(
    "Operators interact through the Network Data Portal (upload, browse, receive) and HTTP APIs. End users verify integrity at " +
      "chunk, file, and anchor levels before trusting a download."
  ),

  h1("1. Problem Statement"),
  h2("1.1 Why Not Store Files On-Chain?"),
  p(
    "A blockchain is replicated by every full node forever. Putting multi-megabyte files into transactions would:"
  ),
  bullet("bullets", "Explode sync time and disk requirements for all participants"),
  bullet("bullets", "Hit hard payload limits (Bloodstone OP_RETURN relay cap is ~80 bytes per data carrier output)"),
  bullet("bullets", "Make downloads expensive in fees and economically impractical at scale"),
  bullet("bullets", "Conflate consensus data (blocks) with application data (releases, media, archives)"),
  p(
    "Even with SpaceXpanse/Bloodstone extensions allowing multiple OP_RETURN outputs per transaction, storing complete " +
      "files on-chain remains infeasible. A single 8 MB Android APK would require on the order of 100,000 data outputs."
  ),

  h2("1.2 What We Need Instead"),
  p("The network needs properties similar to IPFS and BitTorrent, grounded in Bloodstone's existing node fleet:"),
  bullet("numbers", "Content addressing — chunks identified by cryptographic hash, not server path"),
  bullet("numbers", "Sharding — no single host must hold the entire file"),
  bullet("numbers", "Redundancy — many devices pin overlapping slices so loss of one VPS is survivable"),
  bullet("numbers", "Verifiability — users can confirm a download matches a root hash anchored on-chain"),
  bullet("numbers", "Progressive adoption — browsers and pruned phones participate without running a full node"),

  h1("2. Architecture Overview"),
  p("Chain Mesh Storage uses a hybrid two-layer model:"),
  table(
    ["Layer", "Role", "Stores"],
    [
      ["Bloodstone chain", "Source of truth", "BSM1 anchor txs: asset id, Merkle root, metadata"],
      ["Chain mesh (off-chain)", "Bulk storage", "256 KiB chunks on coordinator + peer devices"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Retrieval flow: a client fetches the asset manifest (chunk list + Merkle root), downloads chunks from the coordinator " +
      "or LAN peers, verifies each chunk hash, rebuilds the file, and optionally checks the Merkle root against an on-chain anchor."
  ),

  h1("3. Existing Foundation"),
  p(
    "Bloodstone already ships Chain Mesh for block-file disaster recovery. The coordinator chunks immutable blocks/*.dat files, " +
      "Android and browser peers pin assigned slices, and chain-mesh-restore.py rebuilds block data from the mesh."
  ),
  table(
    ["Component", "Location", "Function"],
    [
      ["chain_mesh Python package", "/root/chain_mesh/", "Chunking, manifests, peer registry, restore"],
      ["Coordinator API", "miner-web /api/chain-mesh/*", "Manifest, chunk fetch, peer upload"],
      ["Browser mesh", "chain-mesh.js", "IndexedDB chunk cache, LAN peer fetch :18341"],
      ["Android mesh", "BloodstoneChainMesh plugin", "Native filesystem chunk store"],
      ["Assignment", "assignment.py", "Each node backs up ~10% of chunks by node_id hash"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "This white paper extends that foundation from block archives to arbitrary publishable assets (APKs, documentation, pool bundles) " +
      "and adds on-chain BSM1 anchors so manifests are tamper-evident."
  ),

  h1("4. Protocol v1 — Asset Publishing"),
  h2("4.1 Chunking"),
  bullet("bullets", "Chunk size: 256 KiB (configurable via CHAIN_MESH_CHUNK_SIZE)"),
  bullet("bullets", "Chunk ID: SHA-256 of chunk bytes (pure content hash for assets)"),
  bullet("bullets", "Manifest lists: asset key, MIME type, version, file SHA-256, ordered chunk hashes"),
  bullet("bullets", "Merkle root: binary Merkle tree over sorted chunk hashes"),

  h2("4.2 On-Chain Anchor (BSM1)"),
  p("Each published asset may be anchored with a standard data-carrier transaction:"),
  bullet("numbers", "Magic bytes: BSM1 (Bloodstone Storage Mesh version 1)"),
  bullet("numbers", "Asset ID: first 16 bytes of SHA-256(asset_key)"),
  bullet("numbers", "Merkle root: 32 bytes"),
  bullet("numbers", "Total payload: 52 bytes — fits within standard OP_RETURN relay limits"),
  p(
    "The anchor does not embed file bytes. It commits the publisher's claim: at block height H, asset X has Merkle root R. " +
      "Wallets and explorers can index these outputs to build a decentralized catalog."
  ),

  h2("4.3 Redundancy Model"),
  p("Replication follows the same deterministic assignment used for block chunks:"),
  bullet("bullets", "Each peer stores chunks where hash(node_id, chunk_hash) mod 100 < backup_pct (default 10%)"),
  bullet("bullets", "Coordinator always stores a full copy at publish time"),
  bullet("bullets", "With N active mesh peers, expected replica count scales linearly — geographic and ISP diversity emerges naturally"),
  bullet("bullets", "Future work: erasure coding (Reed-Solomon) to reduce per-device storage while maintaining recovery threshold"),

  h2("4.4 Retrieval and Verification"),
  p("Clients verify integrity at three levels:"),
  bullet("numbers", "Chunk level — SHA-256(chunk_bytes) must match manifest entry"),
  bullet("numbers", "File level — rebuilt file SHA-256 matches manifest file_hash"),
  bullet("numbers", "Anchor level — manifest Merkle root matches BSM1 OP_RETURN at expected height (optional but recommended)"),

  new Paragraph({ children: [new PageBreak()] }),

  h1("5. Comparison to IPFS and Central CDN"),
  table(
    ["Property", "IPFS", "Central CDN", "Bloodstone Chain Mesh"],
    [
      ["Content addressing", "CID (multihash)", "URL path", "SHA-256 chunks + Merkle root"],
      ["On-chain truth", "None (external)", "None", "BSM1 anchor on Bloodstone chain"],
      ["Participation", "IPFS daemon", "None", "Existing Bloodstone miners / browsers"],
      ["Incentive", "Filecoin (optional)", "Operator budget", "Mining + mesh node modes"],
      ["LAN recovery", "mDNS / DHT", "No", "Built-in LAN chunk server :18341"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("6. Node Roles in Storage"),
  table(
    ["Role", "Storage duty", "Lifetime value"],
    [
      ["Coordinator VPS", "Full chunk store, manifest API, publish pipeline", "Bootstrap and authoritative catalog"],
      ["Mesh peer (browser)", "Pin assigned chunks in IndexedDB", "Zero-install redundancy"],
      ["Mesh peer (Android)", "Pin chunks on device storage", "Mobile geographic distribution"],
      ["Pruned / mesh node", "Block chunks + optional asset chunks", "Validates tip + preserves archives"],
      ["Full node", "Indexes BSM1 anchors", "Permanent witness of published manifests"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("7. Security Considerations"),
  bullet("bullets", "Content hashes prevent chunk substitution — corrupted downloads fail verification"),
  bullet("bullets", "On-chain anchors bind manifest to a block height; reorgs may invalidate very recent anchors (clients should wait for confirmations)"),
  bullet("bullets", "Availability is not consensus — peers may go offline; redundancy parameters must ensure quorum of replicas"),
  bullet("bullets", "Privacy: chunk payloads are public to anyone with the hash (same as IPFS) — encrypt sensitive assets before publish if needed"),

  h1("8. Limits and Configuration"),
  p(
    "Protocol v1.1 enforces practical bounds so browser and phone peers can participate without exhausting memory or upload quotas."
  ),
  table(
    ["Parameter", "Default", "Purpose"],
    [
      ["Chunk size", "256 KiB", "Balance manifest size vs. HTTP round-trips"],
      ["Max asset size", "64 MiB", "Browser publish limit (CHAIN_MESH_MAX_ASSET_BYTES)"],
      ["Max chunks per asset", "256", "Caps manifest size at ~64 MiB with 256 KiB chunks"],
      ["Max chunk upload", "260 KiB", "Single POST body limit (chunk + small overhead)"],
      ["Backup percentage", "10%", "Each peer pins hash(node_id, chunk) mod 100 < backup_pct"],
      ["Asset key prefix", "downloads/ or assets/", "Namespace for catalog entries"],
      ["Publish token", "Optional env", "CHAIN_MESH_PUBLISH_TOKEN gates publish and metadata PATCH"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Asset keys must be stable paths (e.g. downloads/bloodstone-miner-android-latest.apk). Re-publishing under the same key " +
      "creates a new revision; prior file hashes are retained in the version history table."
  ),
  p(
    "Reverse proxies in front of the coordinator should allow at least 16 MiB per request for batched chunk uploads. " +
      "Android v1.3.15+ and the browser uploader split large files into single-chunk POSTs to avoid HTTP 413 errors."
  ),

  h1("9. Mesh Asset Library"),
  p(
    "Beyond raw chunk storage, Bloodstone ships a first-class asset library integrated into the Network Data Portal " +
      "(/mining/network-data). Operators and users browse published files, preview supported types, edit labels, download " +
      "verified copies, and replace files without changing the asset key."
  ),
  table(
    ["Endpoint", "Method", "Function"],
    [
      ["/api/chain-mesh/assets", "GET", "Catalog of published assets (limit parameter)"],
      ["/api/chain-mesh/asset/<key>", "GET", "Manifest: chunks, Merkle root, anchor txid, peer counts"],
      ["/api/chain-mesh/asset/<key>", "PATCH", "Update display_name and version (publish token if configured)"],
      ["/api/chain-mesh/asset/<key>/download", "GET", "Server-side reconstruct + attachment download"],
      ["/api/chain-mesh/asset/<key>/preview", "GET", "Inline text (≤256 KiB) or image (≤2 MiB) preview"],
      ["/api/chain-mesh/asset/<key>/versions", "GET", "Revision history for a stable asset key"],
      ["/api/chain-mesh/publish-asset", "POST", "Register manifest from pre-uploaded chunks + optional anchor"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  h2("9.1 Preview and Web Content"),
  p(
    "Text previews support text/plain, text/html, text/css, text/markdown, application/json, application/javascript, and XML. " +
      "Images support PNG, JPEG, GIF, WebP, and SVG up to 2 MiB. HTML and other text files publish like any asset — the mesh " +
      "is content distribution, not live web hosting. Multi-file websites require separate publishes per path or a zip archive; " +
      "there is no server-side routing or custom domain binding."
  ),
  h2("9.2 Android APK Mesh Fallback"),
  p(
    "The Android miner update manifest (GET /api/downloads/android-miner-update) includes mesh_asset_key, merkle_root, " +
      "file_sha256, and anchor_txid when the APK is also published to downloads/<filename>.apk. If the CDN URL fails, " +
      "the app reconstructs the APK from mesh chunks and verifies hashes before install — the same verification path as white papers."
  ),
  h2("9.3 Publish Token"),
  p(
    "When CHAIN_MESH_PUBLISH_TOKEN is set on the coordinator, publish-asset and metadata PATCH requests must include the token " +
      "in the JSON body or X-Chain-Mesh-Publish-Token header. Read endpoints (catalog, manifest, download, preview) remain public " +
      "so anyone can verify and receive files without operator credentials."
  ),

  h1("10. BSM1 Anchor Index"),
  p(
    "chain_mesh.anchor_index scans Bloodstone blocks for BSM1 OP_RETURN outputs and maintains a SQLite catalog " +
      "(anchor_index.db) linking txid, block height, Merkle root, and enriched asset_key from the mesh registry."
  ),
  bullet("bullets", "refresh_index() — incremental scan from last height or 500-block lookback"),
  bullet("bullets", "index_txid() — index a single mempool or confirmed transaction"),
  bullet("bullets", "_sync_mesh_db_anchors() — backfill anchor_txid and confirmations into chain_assets"),
  bullet("bullets", "list_anchors() / get_anchor() — programmatic catalog for explorers and dashboards"),
  p(
    "Anchors are optional at publish time but recommended for releases users must trust independently of the coordinator. " +
      "Clients should wait for several confirmations before treating an anchor as final, since shallow reorgs can invalidate recent commits."
  ),

  h1("11. Implementation Roadmap"),
  h2("11.1 Delivered (July 2026)"),
  bullet("numbers", "chain_mesh package — chunking, manifests, peer registry, block restore"),
  bullet("numbers", "chain_mesh.assets — publish, reconstruct, preview, version history"),
  bullet("numbers", "chain_mesh.anchor — BSM1 OP_RETURN via bloodstone-cli"),
  bullet("numbers", "chain_mesh.anchor_index — on-chain BSM1 scanner and mesh registry sync"),
  bullet("numbers", "Network Data Portal — upload form, asset library, receive with verification"),
  bullet("numbers", "mesh-asset-library.js — browse, view, edit, replace, LAN-aware download fallback"),
  bullet("numbers", "Android mesh-backed APK update when CDN unavailable"),
  bullet("numbers", "CLI: chain-mesh-publish-asset.py, chain-mesh-restore.py"),

  h2("11.2 Planned"),
  bullet("bullets", "Public HTTP API for anchor index (GET /api/chain-mesh/anchors)"),
  bullet("bullets", "Erasure-coded shards for ~3× storage efficiency"),
  bullet("bullets", "Storage proof rewards tied to sustained chunk availability"),
  bullet("bullets", "IPFS bridge — export same chunks as IPFS CIDs for external tooling"),

  new Paragraph({ children: [new PageBreak()] }),

  h1("12. Uploading, Sending, and Receiving Data"),
  p(
    "Operators and developers interact with Chain Mesh through three flows: upload (publish bytes to the network), " +
      "send (push replicas, peer announcements, and offline queues), and receive (fetch manifests, download chunks, verify integrity). " +
      "A live portal documents these flows for end users."
  ),
  linkPara(
    "Network Data Portal",
    "https://bloodstonewallet.mytunnel.org/mining/network-data"
  ),

  h2("12.1 Upload — Publish a File"),
  p("Uploading stores file bytes off-chain and commits metadata to the mesh catalog (and optionally the chain):"),
  bullet("numbers", "Client splits the file into 256 KiB chunks; each chunk ID is SHA-256(chunk_bytes)"),
  bullet("numbers", "Chunks are POSTed to /api/chain-mesh/upload (batch JSON with data_b64)"),
  bullet("numbers", "Manifest is POSTed to /api/chain-mesh/publish-asset with ordered chunk list + Merkle root"),
  bullet("numbers", "Optional BSM1 anchor transaction records Merkle root on Bloodstone mainnet"),
  bullet("numbers", "Coordinator retains a full copy; mesh peers pin assigned slices by node_id hash"),
  table(
    ["Step", "HTTP", "Purpose"],
    [
      ["1", "POST /api/chain-mesh/upload", "Store chunk replicas on coordinator"],
      ["2", "POST /api/chain-mesh/publish-asset", "Register asset manifest + anchor"],
      ["3", "POST /api/chain-mesh/peer", "Announce which chunk hashes this device holds"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("12.2 Send — Participate as a Network Peer"),
  p("Sending data is not limited to publishing new files. Active nodes continuously push network state:"),
  bullet("bullets", "Storage peers — POST /api/chain-mesh/peer with chunk_hashes after sync or upload"),
  bullet("bullets", "LAN chunk service — Android BloodstoneChainMesh serves :18341 on Wi‑Fi for household peers"),
  bullet("bullets", "Block archive sync — browsers and phones upload assigned block chunks from /api/chain-mesh/manifest"),
  bullet("bullets", "Local VPS nodes — POST /api/chain-mesh/local-node and /api/local-node/lan-register for RPC/stratum"),
  bullet("bullets", "Offline mining — POST /api/chain-mesh/pending-shares queues shares until pool reconnects"),
  bullet("bullets", "Stratum job cache — POST /api/chain-mesh/job-cache shares last job for offline miners"),
  p(
    "Discovery: GET /api/chain-mesh/peers-for/<chunk_hash> returns LAN endpoints; GET /api/local-node/nearby lists nodes behind the same public IP."
  ),

  h2("12.3 Receive — Download and Verify"),
  p("Receiving reconstructs the original file from content-addressed chunks:"),
  bullet("numbers", "GET /api/chain-mesh/assets — browse published catalog"),
  bullet("numbers", "GET /api/chain-mesh/asset/<key> — manifest with chunk hashes, sizes, Merkle root, anchor txid"),
  bullet("numbers", "GET /api/chain-mesh/chunk/<hash> — fetch chunk from coordinator (or LAN peer via mesh JS)"),
  bullet("numbers", "Client verifies SHA-256 per chunk, rebuilds file, checks file SHA-256 and Merkle root"),
  bullet("numbers", "Optional: compare Merkle root to BSM1 OP_RETURN at anchor height"),
  p(
    "The Network Data Portal provides a browser UI for upload and one-click receive with automatic verification. " +
      "CLI operators may use chain-mesh-publish-asset.py and chain-mesh-restore.py for the same protocol."
  ),

  h2("12.4 Network Visibility"),
  p("Connected infrastructure is summarized for dashboards:"),
  bullet("bullets", "GET /api/network/nodes — P2P connections + mesh peers + local VPS + fleet offload counts"),
  bullet("bullets", "GET /api/chain-mesh/status — coordinator coverage, active storage peers, local node stats"),

  h1("13. Conclusion"),
  p(
    "Bloodstone Storage Layer separates consensus data from application data. The blockchain witnesses manifests; the mesh " +
      "stores bytes. Chain Mesh provides content-addressed sharding and peer redundancy; the Asset Library makes publishing " +
      "and retrieval usable for operators and end users; BSM1 anchors bind releases to block height for independent verification."
  ),
  p(
    "Every new mesh peer increases archival resilience. Every anchored release is independently verifiable. Android APK fallback, " +
      "white paper distribution, and block archive recovery all share one protocol. Over the lifetime of the coin, storage " +
      "decentralizes the same way hashrate and validation already do — not by eliminating servers overnight, but by making them replaceable."
  ),

  h2("References"),
  linkPara("Bloodstone portal", "https://bloodstonewallet.mytunnel.org/"),
  linkPara("Network Data Portal", "https://bloodstonewallet.mytunnel.org/mining/network-data"),
  linkPara("Chain mesh asset catalog", "https://bloodstonewallet.mytunnel.org/api/chain-mesh/assets"),
  linkPara("Economic model white paper", "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Economic-Model-White-Paper.docx"),
  linkPara("Network decentralization white paper", "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Decentralized-Network-White-Paper.docx"),
  p("Protocol magic: BSM1 · Chunk size: 256 KiB · Max asset: 64 MiB · Assignment: node_id_hash_v1 · Backup default: 10%"),
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
                  text: "Bloodstone Storage Layer — White Paper",
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

const outDocx =
  "/root/bloodstone-docs/Bloodstone-Chain-Mesh-Storage-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outDocx, buffer);
  console.log("Wrote", outDocx, buffer.length, "bytes");
});