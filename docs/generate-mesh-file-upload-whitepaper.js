#!/usr/bin/env node
/** Bloodstone white paper — mesh file uploads, posting, and keyed overwrites. */
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
function mono(text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text, font: "Courier New", size: 20 })],
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
    children: [new TextRun({ text: "Bloodstone Chain Mesh", size: 52, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "White Paper — File Uploads, Posting, and Keyed Overwrites",
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [new TextRun({ text: "July 2026 · Operator Guide v1.0", size: 24, italics: true })],
  }),

  h1("Executive Summary"),
  p(
    "Bloodstone stores files off-chain on the Chain Mesh: content-addressed 256 KiB chunks replicated across coordinators, " +
      "browsers, and Android nodes. The blockchain records manifests — asset keys, file hashes, and Merkle roots — not the raw bytes. " +
      "This document explains how to upload files, post them to the network catalog, and overwrite existing data by reusing the same asset key."
  ),
  p(
    "Three publish paths exist: (1) user submission with admin review for assets/ keys; (2) immediate admin publish with a publish token; " +
      "and (3) BSM2 mesh transfers that optionally bind delivery to a recipient STONE address while updating a mesh key. " +
      "All paths share the same chunking, verification, and overwrite semantics."
  ),
  p(
    "Operators use the Network Data Portal for browser-based upload. Developers integrate via HTTP APIs documented below. " +
      "Every published file has a stable asset key; publishing again under that key creates a new revision without changing the download path."
  ),

  h1("1. Core Concepts"),
  h2("1.1 Asset Keys"),
  p(
    "An asset key is the stable path that identifies a file in the mesh catalog. Keys are not filenames on a single server — " +
      "they are logical names every peer uses to find manifests and chunks."
  ),
  table(
    ["Prefix", "Who may write", "Typical use"],
    [
      ["assets/", "Any user (review) or admin (immediate)", "Community uploads, shared documents, custom builds"],
      ["downloads/", "Admin publish token only", "Official APKs, white papers, release bundles"],
      ["transfers/", "BSM2 transfer protocol (automatic)", "Ephemeral peer-to-peer deliveries"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Rules enforced by the coordinator: keys must start with assets/ or downloads/; no .. path segments; maximum length 240 characters. " +
      "The asset ID is SHA-256(asset_key) and is used in BSM1 on-chain anchors."
  ),

  h2("1.2 Chunking and Manifests"),
  bullet("bullets", "Chunk size: 256 KiB (CHAIN_MESH_CHUNK_SIZE)"),
  bullet("bullets", "Chunk ID: SHA-256 of chunk bytes"),
  bullet("bullets", "Manifest: ordered list of chunk_hash, file_offset, size"),
  bullet("bullets", "Merkle root: binary Merkle tree over chunk hashes"),
  bullet("bullets", "File hash: SHA-256 of the complete reconstructed file"),
  p(
    "The coordinator verifies every chunk at publish time: hash match, contiguous offsets, and sum of sizes equals file_size. " +
      "Clients repeat the same checks on download."
  ),

  h2("1.3 Overwrite by Key"),
  p(
    "Mesh storage is revision-based, not destructive. When you publish under an existing asset key, the coordinator registers a new " +
      "current revision. Prior revisions remain in the version history table (GET /api/chain-mesh/asset/<key>/versions). " +
      "Download endpoints always serve the current revision."
  ),
  bullet("numbers", "Same asset key + new file bytes = new Merkle root, new chunk set, new revision"),
  bullet("numbers", "Old chunks may remain on disk (content-addressed deduplication) but are no longer referenced by the catalog"),
  bullet("numbers", "BSM1 anchor (optional) commits the new Merkle root on-chain"),
  p(
    "Before overwriting, list writable keys via GET /api/chain-mesh/writable-keys. The Network Data Portal shows these keys in an " +
      "autocomplete datalist and a clickable catalog."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("2. Publish Paths"),
  h2("2.1 User Submission (assets/ only)"),
  p(
    "Public contributors upload files for admin review. Chunks are stored immediately, but the manifest is not registered in the " +
      "public catalog until an administrator approves the submission."
  ),
  table(
    ["Step", "Endpoint", "Action"],
    [
      ["1", "POST /api/chain-mesh/upload", "Upload chunks (base64 in JSON batches)"],
      ["2", "POST /api/chain-mesh/submit-asset", "Queue manifest for review"],
      ["3", "Admin: POST .../pending-submissions/<id>/approve", "Publish to mesh + optional BSM1 anchor"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "User submissions cannot use downloads/ keys. Selecting an existing assets/ key in the submit form queues an overwrite — " +
      "the portal prompts for confirmation when the key already exists."
  ),

  h2("2.2 Admin Immediate Publish"),
  p(
    "Operators with CHAIN_MESH_PUBLISH_TOKEN set on the coordinator may publish or overwrite immediately. The token is sent in the " +
      "JSON body (publish_token) or X-Chain-Mesh-Publish-Token header."
  ),
  table(
    ["Step", "Endpoint", "Action"],
    [
      ["1", "POST /api/chain-mesh/publish-upload", "Upload chunks (token required)"],
      ["2", "POST /api/chain-mesh/publish-asset", "Register manifest + optional BSM1 anchor"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Admin publish supports both assets/ and downloads/ keys. This is how official APKs and white papers are mirrored to the mesh."
  ),

  h2("2.3 BSM2 Mesh Transfer (optional asset_key)"),
  p(
    "BSM2 transfers deliver files to a recipient STONE address with miner-attested chunk relay. When asset_key is included in the " +
      "transfer create payload, the coordinator also publishes a mesh revision at that key — combining peer-to-peer delivery with " +
      "catalog overwrite."
  ),
  bullet("bullets", "POST /api/chain-mesh/upload — chunks first"),
  bullet("bullets", "POST /api/chain-mesh/transfer — register transfer; pass asset_key to overwrite mesh storage"),
  bullet("bullets", "Optional BSM2 on-chain anchor binds transfer_id + Merkle root + recipient"),
  bullet("bullets", "Miners attest relay work via POST /api/chain-mesh/transfer/attest after accepted shares"),

  h1("3. Network Data Portal (Browser UI)"),
  linkPara(
    "Open Network Data Portal",
    "https://bloodstonewallet.mytunnel.org/mining/network-data"
  ),

  h2("3.1 Submit for Review"),
  bullet("numbers", "Choose a file and an asset key (autocomplete lists existing assets/ keys)"),
  bullet("numbers", "Optional: display name, version label, STONE address, reviewer note"),
  bullet("numbers", "Check Request BSM1 anchor to ask for on-chain commit after approval"),
  bullet("numbers", "Submit — chunks upload, then manifest queues as pending submission"),

  h2("3.2 Send / Update on Mesh"),
  bullet("numbers", "Pick a file and select a mesh key from the writable-keys list"),
  bullet("numbers", "Leave recipient blank to publish or overwrite directly (admin token) or submit for review (public)"),
  bullet("numbers", "Fill sender + recipient STONE addresses to run a BSM2 transfer that also updates the mesh key"),
  bullet("numbers", "Confirm overwrite when replacing an existing key"),

  h2("3.3 Receive and Verify"),
  bullet("bullets", "Quick receive: enter asset key, click Download & verify"),
  bullet("bullets", "Library table: browse published files, view metadata, download verified copies"),
  bullet("bullets", "Admin Replace file: upload new bytes under the same key from the asset detail modal"),

  new Paragraph({ children: [new PageBreak()] }),

  h1("4. HTTP API Reference"),
  h2("4.1 Discover Writable Keys"),
  mono("GET /api/chain-mesh/writable-keys?limit=200&prefix=assets/"),
  p("Returns every current mesh key that can be overwritten, with display_name, version, file_size, and admin_only flag."),
  p("Also included in GET /api/chain-mesh/transfer/protocol as writable_keys for BSM2 clients."),

  h2("4.2 Upload Chunks"),
  mono("POST /api/chain-mesh/upload"),
  p("Public chunk ingest. Body (JSON):"),
  mono(
    '{ "device_id": "browser-abc", "peer_kind": "browser", "chunks": [ { "chunk_hash": "<64 hex>", "data_b64": "<base64>" } ] }'
  ),
  p("Admin publish uploads use POST /api/chain-mesh/publish-upload with X-Chain-Mesh-Publish-Token header."),

  h2("4.3 Submit for Review"),
  mono("POST /api/chain-mesh/submit-asset"),
  p("Required fields: asset_key (assets/…), display_name, mime_type, file_size, file_sha256, merkle_root, chunks[]."),
  p("Optional: version, anchor (default true), submitter_address, device_id, note."),

  h2("4.4 Publish Immediately (admin)"),
  mono("POST /api/chain-mesh/publish-asset"),
  p("Same manifest fields as submit-asset, plus publish_token. Overwrites when asset_key already exists."),

  h2("4.5 BSM2 Transfer with Overwrite"),
  mono("POST /api/chain-mesh/transfer"),
  p("Required: sender, recipient, display_name, file_size, file_sha256, merkle_root, chunks[]."),
  p("Optional: asset_key — if set, publishes mesh revision at that key; anchor (default true) for BSM2 OP_RETURN."),

  h2("4.6 Read and Download"),
  table(
    ["Endpoint", "Purpose"],
    [
      ["GET /api/chain-mesh/assets", "Published catalog"],
      ["GET /api/chain-mesh/asset/<key>", "Manifest + chunk list"],
      ["GET /api/chain-mesh/asset/<key>/download", "Verified file download"],
      ["GET /api/chain-mesh/asset/<key>/versions", "Revision history for a key"],
      ["GET /api/chain-mesh/chunk/<hash>", "Single chunk (base64)"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("5. Step-by-Step: Overwrite an Existing File"),
  h2("5.1 Browser (admin)"),
  bullet("numbers", "Log in as admin so publish token is available"),
  bullet("numbers", "Open Network Data Portal → Published files library → View on target asset"),
  bullet("numbers", "Click Replace file, choose new file, confirm upload"),
  bullet("numbers", "Coordinator registers new revision; optional BSM1 anchor records new Merkle root"),

  h2("5.2 Browser (public user)"),
  bullet("numbers", "Open Submit files form"),
  bullet("numbers", "Pick existing key from autocomplete (or type assets/my-file.zip)"),
  bullet("numbers", "Confirm overwrite prompt"),
  bullet("numbers", "Submit — awaits admin approval before catalog updates"),

  h2("5.3 curl (admin publish)"),
  p("After chunks are uploaded, register the manifest:"),
  mono(
    'curl -X POST https://bloodstonewallet.mytunnel.org/api/chain-mesh/publish-asset \\\n' +
      '  -H "Content-Type: application/json" \\\n' +
      '  -H "X-Chain-Mesh-Publish-Token: $TOKEN" \\\n' +
      '  -d \'{"asset_key":"downloads/My-Release.zip","display_name":"My Release 2.0",\'\n' +
      '       \'"file_size":1048576,"file_sha256":"<hash>","merkle_root":"<root>",\'\n' +
      '       \'"chunks":[{"chunk_hash":"<h>","file_offset":0,"size":262144},...],\'\n' +
      '       \'"anchor":true}\''
  ),
  p(
    "Use the browser SDK (mesh-asset-publish.js publishMeshAssetFromFile) or Android mesh-transfer.js sendMeshToKey " +
      "to handle chunking, batched upload, and manifest registration automatically."
  ),

  h1("6. Limits and Errors"),
  table(
    ["Limit", "Default", "Error if exceeded"],
    [
      ["Max file size", "64 MiB", "file_size must be 1..67108864"],
      ["Max chunks", "256", "too many chunks"],
      ["Chunk size", "256 KiB", "invalid chunk size"],
      ["Asset key length", "240 chars", "asset_key too long"],
      ["User downloads/ key", "Forbidden", "user uploads must use assets/ keys"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p("Common failures:"),
  bullet("bullets", "missing chunk on coordinator — upload chunks before manifest POST"),
  bullet("bullets", "merkle_root does not match — recompute from chunk hashes client-side"),
  bullet("bullets", "invalid publish token — admin login or set CHAIN_MESH_PUBLISH_TOKEN"),
  bullet("bullets", "HTTP 413 — batch fewer chunks per POST (browser uploader uses 2 chunks per request)"),

  h1("7. Verification Checklist"),
  p("Recipients should verify before trusting a download:"),
  bullet("numbers", "Each chunk SHA-256 matches manifest entry"),
  bullet("numbers", "Rebuilt file SHA-256 matches manifest file_sha256"),
  bullet("numbers", "Merkle root matches manifest merkle_root"),
  bullet("numbers", "Optional: BSM1 anchor tx commits same Merkle root at sufficient confirmations"),

  h1("8. Security Model"),
  bullet("bullets", "Publish token gates immediate write to catalog; read endpoints stay public"),
  bullet("bullets", "User submissions require admin approval — prevents spam in downloads/ namespace"),
  bullet("bullets", "Content is public to anyone with chunk hashes (encrypt sensitive files before upload)"),
  bullet("bullets", "Overwrite does not delete history — auditors can inspect prior revisions via /versions"),

  h1("9. Relationship to Other Protocols"),
  p(
    "BSM1 anchors (52-byte OP_RETURN) commit asset Merkle roots for catalog integrity. BSM2 anchors (68-byte OP_RETURN) commit " +
      "transfer deliveries to recipients. Chunk assignment and LAN peer fetch (:18341) are identical across block archives, APKs, " +
      "and user uploads. See the Chain Mesh Storage white paper for architecture depth."
  ),
  linkPara(
    "Chain Mesh Storage white paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),

  h1("10. Conclusion"),
  p(
    "Posting a file to Bloodstone means chunking it, uploading hashes to the mesh, and registering a manifest under a stable asset key. " +
      "Overwriting means publishing again with the same key — a new revision, not a silent edit. Writable keys are listed publicly so " +
      "senders know exactly which paths they can update."
  ),
  p(
    "Use the Network Data Portal for guided upload, the writable-keys API for automation, and admin publish or BSM2 transfer when " +
      "immediate delivery and catalog update must happen in one step."
  ),

  h2("References"),
  linkPara("Bloodstone portal", "https://bloodstonewallet.mytunnel.org/"),
  linkPara("Network Data Portal", "https://bloodstonewallet.mytunnel.org/mining/network-data"),
  linkPara("Writable keys API", "https://bloodstonewallet.mytunnel.org/api/chain-mesh/writable-keys"),
  linkPara("Asset catalog API", "https://bloodstonewallet.mytunnel.org/api/chain-mesh/assets"),
  linkPara("Economic model white paper", "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Economic-Model-White-Paper.docx"),
  p("Document version: 1.0 · July 2026 · Bloodstone Chain Mesh operator guide"),
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
                  text: "Bloodstone Chain Mesh — File Uploads & Overwrites",
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
  "/root/bloodstone-docs/Bloodstone-Mesh-File-Upload-White-Paper.docx";
const outDownloads =
  "/var/www/bloodstone/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outDocx, buffer);
  fs.copyFileSync(outDocx, outDownloads);
  console.log("Wrote", outDocx, buffer.length, "bytes");
  console.log("Copied to", outDownloads);
});