#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  HeadingLevel,
  AlignmentType,
  BorderStyle,
  WidthType,
  ShadingType,
  LevelFormat,
  PageBreak,
} = require("docx");

const OUT = path.join(__dirname, "..", "Blurt-Bloodstone-Waves-A-to-Z-Capstone-Summary.docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120 },
    ...opts,
    children: [new TextRun({ text, size: 22 })],
  });
}

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}

function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}

function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
}

function bullet(ref, text) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80 },
    children: [new TextRun({ text, size: 22 })],
  });
}

function table(headers, rows, colWidths) {
  const total = colWidths.reduce((a, b) => a + b, 0);
  const headerCells = headers.map((h, i) =>
    new TableCell({
      borders,
      width: { size: colWidths[i], type: WidthType.DXA },
      shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, size: 20 })] })],
    })
  );
  const dataRows = rows.map(
    (row) =>
      new TableRow({
        children: row.map(
          (cell, i) =>
            new TableCell({
              borders,
              width: { size: colWidths[i], type: WidthType.DXA },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: String(cell), size: 20 })] })],
            })
        ),
      })
  );
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [new TableRow({ children: headerCells }), ...dataRows],
  });
}

const foundationWaves = [
  ["v0.9.0-beta", "A — Trust", "Digital provenance anchor (bloodstone_provenance/v1)"],
  ["v0.10.0-beta", "B — Agents", "Machine/AI agent identity manifests (bloodstone_agent/v1)"],
  ["v0.11.0-beta", "C — DTN", "Delay-tolerant networking bundles for offline Pi sync"],
  ["v0.12.0-beta", "D — Spatial", "Spatial WebXR manifests and AR overlays"],
  ["v0.13.0-beta", "C+", "DTN hardening: dedup, retry, flush windows"],
  ["v0.14.0-beta", "mDNS", "LAN peer discovery via _bloodstone-dtn._tcp"],
  ["v0.15.0-beta", "E — TLS", "Encrypted HTTPS peer sync + forward-queue alerts"],
  ["v0.16.0-beta", "F — Scale", "Compute job manifests + replication auto-heal"],
  ["v0.17.0-beta", "G — Pi fleet", "Memo rail enforcement + Pi Fleet Playbook"],
];

const scaleWaves = [
  ["v0.18.0-beta", "H — Gossip", "DTN gossip protocol for peer rumor exchange"],
  ["v0.19.0-beta", "I — Starlink", "Satellite/LTE opportunistic bundle handoff"],
  ["v0.20.0-beta", "J — Offline Condenser", "Offline-first social reader"],
  ["v0.21.0-beta", "K — Planetary", "Multi-region DTN quorum rollup + heal"],
  ["v0.22.0-beta", "L — Bridge", "BLURT ↔ STONE atomic swap intents"],
];

const aiWaves = [
  ["v0.23.0-beta", "M — AI routing", "On-device AI routing scaffold"],
  ["v0.24.0-beta", "N — Coordinator", "HTTP coordinator dispatch + callback"],
];

const tenantWaves1 = [
  ["v0.25.0-beta", "O — Signed gossip", "HMAC-signed AI gossip + NPU detect"],
  ["v0.26.0-beta", "P — Compute tenant", "Per-author FLOPS caps"],
  ["v0.27.0-beta", "Q — Inference shim", "llama.cpp shim + bandwidth tenant"],
  ["v0.28.0-beta", "R — Storage tenant", "Storage quota + AI DTN route export"],
  ["v0.29.0-beta", "S — Dashboard", "Unified tenant dashboard + ONNX/TFLite"],
  ["v0.30.0-beta", "T — Fleet sync", "Tenant binding sync via DTN + gossip"],
];

const tenantWaves2 = [
  ["v0.31.0-beta", "U — Signed fleet", "HMAC tenant snapshots + dashboard UI"],
  ["v0.32.0-beta", "V — Quorum", "Fleet quorum + Blurt tenant manifest broadcast"],
  ["v0.33.0-beta", "W — Submit gate", "Quorum-gated submit + NPU model bindings"],
  ["v0.34.0-beta", "X — AI routing", "Tenant AI scoring + manifest gossip"],
  ["v0.35.0-beta", "Y — Route ledger", "Route ledger + coordinator tenant dispatch"],
  ["v0.36.0-beta", "Z — Capstone", "Tenant planetary quorum + sovereign mesh reconcile"],
];

const layers = [
  ["0", "Sovereign Identity", "B", "Beta"],
  ["1", "Trust Anchor", "A", "Beta"],
  ["2", "Memory Fabric + DTN", "C, C+, E, H, I, K", "Beta"],
  ["3", "Edge DePIN + AI", "F, G, M–Z", "Beta"],
  ["4", "Circulatory Economy", "G, L", "Beta (enforced)"],
  ["5", "Ambient UI", "D, J", "Beta"],
];

const capstoneApis = [
  ["/api/convergence/tenant/planetary/status", "GET", "Cross-region tenant quorum rollup"],
  ["/api/convergence/tenant/planetary/snapshots", "GET", "Planetary gossip snapshots"],
  ["/api/convergence/tenant/sovereign/status", "GET", "Capstone sovereign mesh summary"],
  ["/api/convergence/tenant/sovereign/reconcile", "POST", "Run sovereign reconcile cycle"],
];

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
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
        run: { size: 24, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 120, after: 120 }, outlineLevel: 2 },
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
            text: "\u2022",
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
      children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [
            new TextRun({ text: "Blurt \u00d7 Bloodstone Convergence Stack", bold: true, size: 36 }),
          ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 400 },
          children: [
            new TextRun({
              text: "Complete Work Summary \u2014 Wave A through Capstone Z",
              size: 28,
              color: "444444",
            }),
          ],
        }),
        p("Document version: 1.0  |  Date: July 8, 2026  |  Latest release: v0.36.0-beta (Wave Z)"),
        p("Live coordinator: https://bloodstonewallet.mytunnel.org"),
        p("Stack status: https://bloodstonewallet.mytunnel.org/api/convergence/status"),

        h1("Executive Summary"),
        p(
          "The Blurt\u2013Bloodstone convergence program shipped 26 named waves (A\u2013Z) across 28 beta releases (v0.9.0-beta through v0.36.0-beta). The stack connects Blurt\u2019s censorship-resistant social layer with Bloodstone\u2019s memory fabric, edge DePIN economics, and on-device AI routing."
        ),
        p(
          "Capstone Z completes the tenant sovereign mesh: cross-region fleet quorum rollup, unified reconcile cycles, coordinator dispatch with tenant route hints, and a single dashboard view of the entire tenant fleet."
        ),
        p(
          "Vision: Sovereign Mesh 2030 \u2014 Blurt trust anchor + Bloodstone memory fabric. Autonomous, self-healing nervous system \u2014 identity owns truth, hardware owns the network."
        ),

        h1("Six Convergence Layers"),
        table(["Layer", "Name", "Waves", "Status"], layers, [800, 3200, 2560, 2800]),

        new Paragraph({ children: [new PageBreak()] }),

        h1("Wave-by-Wave Release History"),

        h2("Foundation \u2014 Trust, Identity, and Offline Mesh (A\u2013G)"),
        table(["Release", "Wave", "Summary"], foundationWaves, [1800, 1400, 6160]),

        h2("Scale, Uplink, and Planetary Mesh (H\u2013L)"),
        table(["Release", "Wave", "Summary"], scaleWaves, [1800, 1400, 6160]),

        h2("On-Device AI Routing (M\u2013N)"),
        table(["Release", "Wave", "Summary"], aiWaves, [1800, 1400, 6160]),

        h2("Fleet Hardening and Multi-Tenant Quotas (O\u2013R)"),
        table(["Release", "Wave", "Summary"], tenantWaves1.slice(0, 4), [1800, 1400, 6160]),

        h2("Tenant Dashboard and Fleet Sync (S\u2013T)"),
        table(["Release", "Wave", "Summary"], tenantWaves1.slice(4), [1800, 1400, 6160]),

        h2("Signed Fleet, Quorum, and NPU Execution (U\u2013W)"),
        table(["Release", "Wave", "Summary"], tenantWaves2.slice(0, 3), [1800, 1400, 6160]),

        h2("AI Routing, Gossip, and Route Ledger (X\u2013Y)"),
        table(["Release", "Wave", "Summary"], tenantWaves2.slice(3, 5), [1800, 1400, 6160]),

        h2("Capstone \u2014 Sovereign Tenant Mesh (Z)"),
        table(["Release", "Wave", "Summary"], [tenantWaves2[5]], [1800, 1400, 6160]),
        p(
          "Live roadmap: Wave A\u2013Y \u2713 \u00b7 Wave Z: tenant planetary quorum + sovereign mesh reconcile \u2713"
        ),

        new Paragraph({ children: [new PageBreak()] }),

        h1("Capstone Z \u2014 Technical Detail"),

        h3("New Modules"),
        bullet("bullets", "tenant_planetary_quorum.py \u2014 bloodstone_tenant_planetary/v1 cross-region fleet quorum rollup"),
        bullet("bullets", "tenant_sovereign.py \u2014 bloodstone_tenant_sovereign/v1 capstone status + reconcile_sovereign_mesh()"),

        h3("Coordinator Dispatch Enhancements"),
        bullet("bullets", "Uses inbound tenant_route from dispatch payload"),
        bullet("bullets", "Runs submit-gate check before accepting inference jobs"),
        bullet("bullets", "Records route ledger assignment on coordinator success"),
        bullet("bullets", "Passes tenant_spec to dispatch_inference_job for NPU-aware execution"),

        h3("Unified Upkeep (Extended)"),
        bullet("bullets", "Fleet quorum update + satisfied binding apply"),
        bullet("bullets", "Broadcast queue + registry sync"),
        bullet("bullets", "Manifest and route ledger gossip snapshots"),
        bullet("bullets", "Planetary tenant quorum rollup"),
        bullet("bullets", "sync-blurt-convergence.py calls reconcile_sovereign_mesh()"),

        h3("New APIs (Wave Z)"),
        table(["Endpoint", "Method", "Description"], capstoneApis, [4200, 1000, 4160]),

        h1("Payment Rails (Layer 4)"),
        p("Enforced since Wave G (v0.17.0-beta):"),
        table(
          ["Rail", "Memo format", "Since"],
          [
            ["Storage", "storage:<STONE>:<bytes>", "v0.17 (Wave G)"],
            ["Compute", "compute:<STONE>:<job_id>", "v0.17 (Wave G)"],
            ["Bandwidth", "bandwidth:<STONE>:<bytes>", "v0.17 (Wave G)"],
          ],
          [2200, 4160, 3000]
        ),

        h1("End-to-End Content Flow"),
        bullet("bullets", "Blurt post \u2192 Provenance anchor (A) \u2192 Mesh chunks (C)"),
        bullet("bullets", "Condenser embed / offline reader (D, J) \u2192 Memo payment (G)"),
        bullet("bullets", "DTN bundle queue (C, E) \u2192 Gossip discovery (H)"),
        bullet("bullets", "Planetary heal (K) \u2192 Starlink handoff (I)"),
        bullet("bullets", "Inference submit (F) \u2192 AI routing (M) \u2192 Coordinator dispatch (N)"),
        bullet("bullets", "Tenant fleet sync + quorum (T, V) \u2192 AI route + ledger (X, Y)"),
        bullet("bullets", "Sovereign mesh reconcile (Z)"),

        h1("Pi Fleet Operator Checklist"),
        bullet("bullets", "Install portal + mesh (Wave G playbook)"),
        bullet("bullets", "Enable mDNS, TLS gossip, memo enforcement"),
        bullet("bullets", "Run inference shim on :8081 (Wave Q)"),
        bullet("bullets", "Bind per-author tenant quotas (P, Q, R)"),
        bullet("bullets", "Configure fleet quorum N-of-M (Wave V)"),
        bullet("bullets", "Set AI_GOSSIP_SIGNING_KEY (Waves O, U)"),
        bullet("bullets", "Monitor /api/convergence/tenant/sovereign/status (Wave Z)"),

        h1("Metrics at Capstone Z"),
        table(
          ["Metric", "Value"],
          [
            ["Beta releases", "v0.9.0 through v0.36.0-beta (28 tags)"],
            ["Waves complete", "A through Z (+ C+ and mDNS)"],
            ["Memo enforcement", "On (storage, compute, bandwidth)"],
            ["AI/DTN wave label", "Z"],
            ["Sovereign format", "bloodstone_tenant_sovereign/v1"],
            ["GitLab tag", "v0.36.0-beta @ d58a803"],
          ],
          [4000, 5360]
        ),

        new Paragraph({
          spacing: { before: 400 },
          children: [
            new TextRun({
              text: "Prepared July 8, 2026 \u00b7 Bloodstone LLC \u00b7 Blurt \u00d7 Bloodstone Convergence Stack",
              italics: true,
              size: 20,
              color: "666666",
            }),
          ],
        }),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(OUT, buffer);
  console.log("Wrote", OUT);
});