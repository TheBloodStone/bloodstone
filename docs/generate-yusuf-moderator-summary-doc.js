#!/usr/bin/env node
/** Yusuf moderator brief — Bloodstone × Blurt system summary for X articles. */
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

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}
function p(text) {
  return new Paragraph({ spacing: { after: 160 }, children: [new TextRun(text)] });
}
function italic(text) {
  return new Paragraph({
    spacing: { after: 160 },
    children: [new TextRun({ text, italics: true })],
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
  h1("Bloodstone × Blurt — Moderator Brief for Yusuf"),
  p("Prepared for: Yusuf (moderator & X writer)"),
  p("From: Bloodstone team"),
  p("Date: July 8, 2026"),
  linkPara("Live coordinator", "https://bloodstonewallet.mytunnel.org"),
  p("Latest release: v0.24.0-beta (Wave N)"),

  h2("One-liner (pin this)"),
  p(
    "Blurt owns truth. Bloodstone owns memory. Together they form a censorship-resistant stack where posts are proven on-chain, files live on a mesh of edge nodes (including Raspberry Pis), and everything syncs back—even when the internet only comes back for a minute."
  ),

  h2("What the system is"),
  p("Think of it as two layers built to work together:"),
  table(
    ["Piece", "Role", "Plain English"],
    [
      ["Blurt", "Trust & social layer", "Public ledger for posts, identity, and verifiable publishing"],
      ["Bloodstone", "Memory & mesh layer", "Stores video, chunks, compute jobs, and AR assets across edge machines"],
      ["Convergence stack", "The glue", "APIs, Pi fleet, payments, offline sync, and the live coordinator"],
    ]
  ),
  italic("Official vision: Sovereign Mesh 2030 — Blurt trust anchor + Bloodstone memory fabric"),
  italic(
    "Tagline: Autonomous, self-healing nervous system — identity owns truth, hardware owns the network."
  ),
  p(
    "Who it's for: Bloggers, creators, off-grid operators, Pi hobbyists, and anyone who doesn't want one company's server to be the single point of failure for their content."
  ),

  h2("The six layers (simple map)"),
  bullet("layers", "Identity — Human and AI agents register on the mesh"),
  bullet("layers", "Trust / publishing — Provenance anchors tie Blurt posts to mesh files"),
  bullet("layers", "Memory fabric + DTN — Offline bundles, gossip, satellite handoff, planetary quorum"),
  bullet("layers", "Edge DePIN — Storage, compute, bandwidth, and on-device AI routing"),
  bullet("layers", "Economy — BLURT/STONE memo rails plus atomic swaps"),
  bullet("layers", "Ambient UI — Condenser embeds, offline reader, spatial WebXR"),
  p("All of this is beta and live on the coordinator—not a white paper only."),

  h2("What we shipped in ~two days (July 7–8, 2026)"),
  p(
    "This was fourteen convergence waves and sixteen beta releases (v0.9 → v0.24), plus docs, fixes, and partner materials."
  ),

  h2("Day 1 — Align the blueprint"),
  bullet("day1", "Matched the Symbiotic Vision white paper to production reality"),
  bullet("day1", "Audited gaps: Pi fleet, payments, gossip, satellite uplink, AI routing"),
  bullet("day1", "Synced public GitLab releases with the live coordinator"),

  h2("Day 2 — Ship in waves"),
  p("Trust & mesh foundation (Waves A–G):"),
  table(
    ["Release", "Wave", "What it does"],
    [
      ["v0.9.0-beta", "A — Trust", "Digital provenance: prove where content came from"],
      ["v0.10.0-beta", "B — Agents", "Machine/AI agent identities on the mesh"],
      ["v0.11.0-beta", "C — DTN", "Offline bundles—zip up state, sync later"],
      ["v0.12.0-beta", "D — Spatial", "AR/3D scenes tied to Blurt posts"],
      ["v0.17.0-beta", "G — Pi fleet", "Real payment enforcement + Pi Fleet Playbook"],
    ]
  ),
  p("Scale & uplink (Waves H–I):"),
  table(
    ["Release", "Wave", "What it does"],
    [
      ["v0.18.0-beta", "H — Gossip", "Nodes discover each other beyond LAN"],
      ["v0.19.0-beta", "I — Starlink handoff", "Brief uplink triggers automatic bundle flush"],
    ]
  ),
  p("Advanced convergence (Waves J–N):"),
  table(
    ["Release", "Wave", "What it does"],
    [
      ["v0.21.0-beta", "K", "Planetary DTN quorum (multi-region rollup)"],
      ["v0.22.0-beta", "L", "BLURT↔STONE bridge + atomic HTLC swaps"],
      ["v0.23.0-beta", "M", "On-device AI routing (Pi, Android, LAN llama.cpp)"],
      ["v0.24.0-beta", "N", "Coordinator AI HTTP dispatch + callback delivery"],
    ]
  ),
  p("Live roadmap string: Wave A–M ✓ · Wave N: coordinator AI dispatch ✓"),

  h2("Standout stories Yusuf can write about"),
  h2("1. Starlink isn't the product—handoff is"),
  p(
    'We wrote a partner document for Blurt answering: "Starlink is just broadband—why is that groundbreaking?"'
  ),
  p(
    "Answer: Starlink is only the wire. The innovation is DTN store-and-forward + opportunistic handoff—the mesh queues work offline and pushes it upstream when any brief uplink appears."
  ),
  linkPara(
    "Starlink handoff doc (MD)",
    "https://bloodstonewallet.mytunnel.org/downloads/Blurt-Starlink-Handoff-Response.md"
  ),

  h2("2. On-device AI on a Pi mesh (Waves M → N)"),
  bullet("ai", "Pi + llama.cpp"),
  bullet("ai", "Android (TFLite) via LAN heartbeat"),
  bullet("ai", "Coordinator fallback with HTTP callback when uplink is up"),
  linkPara("AI routing status", "https://bloodstonewallet.mytunnel.org/api/convergence/ai/status"),

  h2("3. QUASAR page fixed same day"),
  p("/quasar/ returned 404 because nginx wasn't proxying it. Added proxy rules; verified 200 on the public URL."),

  h2("4. We dogfood reliability"),
  p(
    "AI dispatch endpoints initially caused worker saturation. Fixed same session: fast validation, more workers, lightweight /health probes, uplink cache. Status now responds in ~0.13s."
  ),

  h2("Soundbites for X (copy-paste ready)"),
  bullet(
    "quotes",
    "Blurt proves the post. Bloodstone keeps the file alive. The mesh does the rest."
  ),
  bullet(
    "quotes",
    "We didn't build 'Starlink integration.' We built: queue while offline, flush when the sky opens."
  ),
  bullet(
    "quotes",
    "Fourteen waves in two days. From provenance anchors to on-device AI routing on Raspberry Pis."
  ),
  bullet(
    "quotes",
    "Your inference job doesn't need AWS. It can run on the Pi in your shed, your Android on LAN, or queue until Starlink blinks on."
  ),
  bullet(
    "quotes",
    "v0.24.0-beta: coordinator AI dispatch is live. Edge nodes submit; coordinator executes; callback delivers the result."
  ),

  h2("Suggested X thread (7 posts)"),
  bullet("thread", "Hook: We shipped 14 convergence waves in ~48 hours. Here's what Blurt × Bloodstone actually is."),
  bullet("thread", "The split: Blurt = trust. Bloodstone = memory. Convergence = APIs + Pi fleet."),
  bullet("thread", "Offline-first: DTN bundles queue locally; handoff flushes on brief uplink."),
  bullet("thread", "Economics: storage, compute, bandwidth via BLURT→STONE memo rails."),
  bullet("thread", "AI at the edge: Wave M/N routes inference to local hardware or coordinator callback."),
  bullet("thread", "Proof it's real: bloodstonewallet.mytunnel.org — beta, not vapor."),
  bullet("thread", "CTA: Pi Fleet Playbook + GitLab docs. Questions welcome."),

  h2("Key links"),
  linkPara("Coordinator status", "https://bloodstonewallet.mytunnel.org/api/convergence/status"),
  linkPara("AI routing status", "https://bloodstonewallet.mytunnel.org/api/convergence/ai/status"),
  linkPara("QUASAR", "https://bloodstonewallet.mytunnel.org/quasar/"),
  linkPara(
    "This brief (MD)",
    "https://bloodstonewallet.mytunnel.org/downloads/Yusuf-Moderator-System-Summary.md"
  ),
  linkPara(
    "This brief (DOCX)",
    "https://bloodstonewallet.mytunnel.org/downloads/Yusuf-Moderator-System-Summary.docx"
  ),

  h2("Tone guidance for Yusuf"),
  p("Do say: offline-first, provenance, edge mesh, Pi fleet, creator sovereignty, BLURT+STONE economy"),
  p("Don't say: we invented Starlink or blockchain solves everything"),
  p(
    "Angle: Practical infrastructure for people who publish where networks are flaky and trust is earned, not assumed."
  ),

  h2("Closing line for articles"),
  italic(
    "In two days we went from aligned blueprint to fourteen live waves—including planetary quorum, atomic bridge swaps, and on-device AI routing on edge hardware. Blurt holds the truth; Bloodstone holds the memory; the mesh holds the line when the uplink doesn't."
  ),
  p("Bloodstone LLC · Convergence coordinator · July 8, 2026"),
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
        run: { size: 26, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 180, after: 180 }, outlineLevel: 1 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "layers",
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
      {
        reference: "day1",
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
        reference: "ai",
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
        reference: "quotes",
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
        reference: "thread",
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
              children: [new TextRun({ text: "Bloodstone × Blurt — Brief for Yusuf", size: 18 })],
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
                new TextRun("Page "),
                new TextRun({ children: [PageNumber.CURRENT] }),
              ],
            }),
          ],
        }),
      },
      children,
    },
  ],
});

const out = path.join(__dirname, "Yusuf-Moderator-System-Summary.docx");
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(out, buffer);
  console.log("Wrote", out);
});