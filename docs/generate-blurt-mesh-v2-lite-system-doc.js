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
const RFC_URL =
  "https://blurt.blog/rfc/@megadrive/rfc-bloodstone-chain-mesh-v2-0-lite-trustless-storage-layer-for-blurt";

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
    children: [new TextRun({ text: "Bloodstone × Blurt", size: 52, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "Chain Mesh v2.0-Lite — System Overview",
        size: 32,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Implementation guide (Megadrive RFC response)",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "This document describes Bloodstone's implementation of Blurt RFC v2.0-Lite — a trustless storage layer that runs alongside the existing v1 coordinator. The mesh remains chunk plumbing; Blurt owns the manifest registry on Layer 1 (Blurt blockchain)."
  ),
  linkPara("Megadrive RFC (source)", RFC_URL),
  p("Coordinator: " + COORDINATOR),
  linkPara("v2 operator UI", COORDINATOR + "/mining/network/blurt-mesh-v2"),

  h1("RFC Requirements → Implementation"),
  table(
    ["RFC requirement", "Bloodstone implementation"],
    [
      [
        "Blurt Layer 1 registry (custom_json chain_mesh_anchor)",
        "chain_mesh/blurt_registry_v2.py",
      ],
      [
        "DHT + on-chain discovery (no coordinator SPOF)",
        "Blurt registry first; coordinator fallback; provider registry as DHT placeholder",
      ],
      ["Independent storage providers", "chain_mesh/mesh_providers.py"],
      ["Trustless retrieval", "chain_mesh/trustless_retrieval.py"],
      ["Bloodstone = software + optional provider", "v1 coordinator + default provider; libp2p planned"],
      ["Hybrid with v1", "Partner publish uses v1 catalog; v2 artifacts on publish response"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("Two-Layer Architecture (RFC §10)"),
  h2("Layer 2 — Tenant registries"),
  p(
    "Blurt uses Blurt custom_json (chain_mesh_anchor) — permanent, public, decentralized. Other tenants may use central DB, S3 JSON, or private ledgers. The mesh is agnostic to registry choice."
  ),
  h2("Layer 1 — Chunk plane (shared)"),
  bullet("bullets", "256 KiB content-addressed chunks"),
  bullet("bullets", "Coordinator chunk store (today)"),
  bullet("bullets", "Provider registry + chunk-to-provider map"),
  bullet("bullets", "Planned: libp2p/Kademlia bootstrap (read-only) + storage daemons"),
  p(
    "resolve_manifest() checks Blurt registry first, then coordinator catalog. trustless_retrieval verifies chunk SHA-256, Merkle root, and file SHA-256 without trusting any provider."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("Blurt Anchor Format (RFC §3.1)"),
  p("Blurt backend broadcasts custom_json with id chain_mesh_anchor and body version 2.0-lite:"),
  mono('{ "v": "2.0-lite", "asset_key": "assets/blurt/media/…",'),
  mono('  "manifest_merkle_root": "<64-hex>", "file_sha256": "<64-hex>",'),
  mono('  "provider_ids": ["bloodstone-coordinator-v1", "12D3KooW…"],'),
  mono('  "chunk_hashes": ["<sha256>", "…"], "timestamp": … }'),
  p(
    "Properties: permanent in Blurt blocks, replicated to full nodes, publicly queryable, signed by uploader posting authority."
  ),

  h1("Publish Flow (RFC §5)"),
  table(
    ["Step", "Action"],
    [
      ["1", "Blurt backend splits file into 256 KiB chunks"],
      ["2", "POST /api/chain-mesh/partner/upload (batches of 2)"],
      ["3", "POST /api/chain-mesh/partner/publish-asset — validates Merkle + file SHA-256"],
      ["4", "Bloodstone announces chunk_hashes to provider registry"],
      ["5", "Response includes v2_lite.blurt_custom_json for Blurt to broadcast"],
      ["6", "Bloodstone indexes anchor locally for fast lookup"],
    ],
    [800, 8560]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  h3("Trustless guarantee"),
  bullet("bullets", "Verify each chunk hash against manifest"),
  bullet("bullets", "Verify manifest anchored on Blurt and signed by uploader"),
  bullet("bullets", "Re-hash reassembled file; compare to file_sha256"),

  h1("Retrieval Flow (RFC §6)"),
  bullet("numbers", "GET /mining/api/chain-mesh/v2/manifest?asset_key=… — Blurt registry → coordinator fallback"),
  bullet("numbers", "Lookup provider_ids from manifest + chunk provider map"),
  bullet("numbers", "Download chunks (coordinator today; direct provider when DHT ships)"),
  bullet("numbers", "GET /mining/api/chain-mesh/v2/verify?asset_key=… — trustless verification"),
  table(
    ["Threat", "Mitigation"],
    [
      ["Corrupted chunk data", "Chunk hash verification"],
      ["Wrong chunk order", "Ordered chunk_hashes in manifest"],
      ["Tampered manifest", "Blurt on-chain anchor + uploader signature"],
      ["Provider offline", "Fallback to next provider_id in manifest"],
      ["All providers offline", "Manifest on Blurt persists; re-upload possible"],
    ],
    [3120, 6240]
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("API Reference"),
  table(
    ["Endpoint", "Purpose"],
    [
      ["GET /mining/api/chain-mesh/v2/system", "Architecture status"],
      ["GET /mining/api/chain-mesh/v2/manifest", "Resolve manifest by asset_key"],
      ["GET /mining/api/chain-mesh/v2/verify", "Trustless chunk + file verification"],
      ["GET /mining/api/chain-mesh/v2/flow", "Publish/retrieve phases"],
      ["GET/POST /mining/api/chain-mesh/v2/providers", "List/register provider nodes"],
      ["POST /mining/api/chain-mesh/v2/blurt/sync", "Admin: index Blurt anchors"],
      ["POST /mining/api/chain-mesh/partner/publish-asset", "Publish + v2 custom_json payload"],
    ],
    [4160, 5200]
  ),

  h1("Code Modules"),
  table(
    ["Module", "Role"],
    [
      ["blurt_registry_v2.py", "Build/parse/index chain_mesh_anchor custom_json"],
      ["mesh_providers.py", "Provider registry; chunk announcements"],
      ["trustless_retrieval.py", "Manifest validation; chunk + file verify"],
      ["mesh_v2_lite.py", "Orchestration: resolve, publish hooks, status"],
      ["api.py", "HTTP payloads; partner publish extended with v2"],
    ],
    [3120, 6240]
  ),

  h1("Phased Rollout (RFC §11)"),
  table(
    ["Phase", "Description", "Status"],
    [
      ["Phase 1", "Bloodstone provider + Blurt on-chain anchors", "Live"],
      ["Phase 2", "Blurt runs own storage provider VPS", "Ready via POST /v2/providers"],
      ["Phase 3", "Community provider program", "Same provider API"],
      ["DHT/libp2p", "Witness bootstrap + storage daemons", "Scaffolded; libp2p next"],
    ],
    [1200, 5360, 2800]
  ),

  h1("What Blurt Backend Does Next"),
  bullet("bullets", "Extract v2_lite.blurt_custom_json from partner/publish-asset response"),
  bullet("bullets", "Sign and broadcast custom_json with posting authority"),
  bullet("bullets", "Store asset_key in post metadata; serve via manifest + verified chunks"),
  bullet("bullets", "Optionally run read-only DHT bootstrap nodes (RFC §4.1)"),
  bullet("bullets", "Optionally run Blurt-operated storage provider (RFC §4.2)"),

  h1("v1 vs v2.0-Lite (RFC §9)"),
  table(
    ["Criteria", "v1.0", "v2.0-Lite"],
    [
      ["Coordinator", "Single server SPOF", "Optional; Blurt registry authoritative"],
      ["Manifest registry", "Centralized API", "Blurt custom_json + index"],
      ["Trust model", "Trust coordinator", "Trustless hash verification"],
      ["Bloodstone dependency", "Required", "Optional provider only"],
      ["Blurt hardfork", "No", "No"],
    ],
    [2400, 3480, 3480]
  ),

  h1("Related Documents"),
  linkPara("Megadrive RFC", RFC_URL),
  linkPara(
    "Blurt send & use guide",
    COORDINATOR + "/downloads/Bloodstone-Blurt-Mesh-Send-And-Use.md"
  ),
  linkPara(
    "Mesh storage partnership",
    COORDINATOR + "/downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx"
  ),
  linkPara(
    "Chain Mesh storage white paper",
    COORDINATOR + "/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({ text: "Document version: 1.0 · July 2026", italics: true, size: 20 }),
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
                  text: "Bloodstone Chain Mesh v2.0-Lite — System Overview",
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
  "/root/bloodstone-docs/Bloodstone-Blurt-Mesh-v2-Lite-System.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote " + outPath);
});