const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
  WidthType, ShadingType, PageNumber, PageBreak, ExternalHyperlink,
} = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const contentW = 9360;

function cell(text, opts = {}) {
  const fill = opts.fill || "FFFFFF";
  const bold = !!opts.bold;
  const w = opts.w || contentW;
  return new TableCell({
    borders,
    width: { size: w, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, bold, size: opts.size || 22 })] })],
  });
}

function heading(text, level) {
  const map = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3 };
  return new Paragraph({ heading: map[level], children: [new TextRun(text)] });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text, bold: !!opts.bold, italics: !!opts.italics, size: opts.size || 24 })],
  });
}

function bullets(items) {
  return items.map((t) => new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 60 },
    children: [new TextRun(t)],
  }));
}

function table(headers, rows, widths) {
  const wsum = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: wsum, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        children: headers.map((h, i) => cell(h, { fill: "028090", bold: true, w: widths[i], size: 20 })),
      }),
      ...rows.map((row) => new TableRow({
        children: row.map((c, i) => cell(c, { w: widths[i], size: 20 })),
      })),
    ],
  });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, color: "028090", font: "Arial" },
        paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, color: "21295C", font: "Arial" },
        paragraph: { spacing: { before: 200, after: 140 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 140, after: 100 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          children: [new TextRun({ text: "Blurt \u00d7 Bloodstone \u2014 Symbiotic Vision", size: 18, color: "666666" })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Bloodstone LLC \u00b7 July 2026 \u00b7 Page ", size: 18, color: "666666" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "666666" }),
          ],
        })],
      }),
    },
    children: [
      new Paragraph({ spacing: { before: 1200, after: 200 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Blurt \u00d7 Bloodstone", size: 52, bold: true, color: "028090" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
        children: [new TextRun({ text: "The Symbiotic Vision", size: 40, bold: true, color: "21295C" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
        children: [new TextRun({ text: "A Sovereign Internet Awakens (2027\u20132035)", size: 28, italics: true })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
        children: [new TextRun({ text: "White Paper v1.0 \u00b7 July 2026 \u00b7 v0.15.0-beta", size: 22, color: "666666" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new ExternalHyperlink({
          children: [new TextRun({ text: "bloodstonewallet.mytunnel.org", style: "Hyperlink", size: 22 })],
          link: "https://bloodstonewallet.mytunnel.org",
        })],
      }),

      heading("Executive Summary: The Living Stack", 1),
      para("Imagine a world where every Raspberry Pi is a sovereign nation, every published thought becomes an eternal digital monument, and every community owns its culture, infrastructure, and economy."),
      para("This is the convergence of Blurt\u2019s censorship-resistant social layer and Bloodstone\u2019s decentralized storage mesh \u2014 a self-healing, self-funding nervous system for human civilization."),
      para("Welcome to the Symbiotic Stack.", { bold: true }),

      heading("What Is Live Today", 2),
      table(
        ["Milestone", "Status"],
        [
          ["Convergence Layers 0\u20135", "Beta \u2014 all layers shipping APIs"],
          ["Waves A\u2013E", "Complete \u2014 provenance through DTN TLS + alerts"],
          ["QUASAR defense", "Phase 5 \u2014 braid validation in core"],
          ["DTN mesh", "Hardened \u2014 mDNS, TLS, alerting"],
          ["Economic rails", "Designed \u2014 enforcement toggles pending"],
        ],
        [4680, 4680],
      ),

      new Paragraph({ children: [new PageBreak()] }),
      heading("The Living Stack Architecture", 1),

      ...[
        ["Layer 0: Sovereign Digital Souls", "LIVE BETA", "bloodstone_agent/v1 \u00b7 Blurt keys + AI agent identity"],
        ["Layer 1: Eternal Publishing", "LIVE BETA", "bloodstone_provenance/v1 \u00b7 blog manifests \u00b7 Post-Truth Engine"],
        ["Layer 2: Planetary Chain Mesh", "LIVE BETA", "BSM1 chunks \u00b7 DTN bundles \u00b7 quorum \u00b7 mDNS \u00b7 TLS"],
        ["Layer 3: Edge Intelligence Fleet", "LIVE BETA", "Pi/Android providers \u00b7 LAN registry \u00b7 Bitaxe merge-mining"],
        ["Layer 4: Economic Singularity", "LIVE BETA", "storage/compute/bandwidth memo rails \u00b7 STONE credits"],
        ["Layer 5: Sovereign Interfaces", "LIVE BETA", "Condenser embed \u00b7 spatial WebXR \u00b7 AR overlays"],
        ["Layer 6: Autonomous Expansion", "PLANNED", "AI curation \u00b7 DAO bounties \u00b7 viral node replication"],
      ].flatMap(([name, status, detail]) => [
        heading(name, 2),
        para(`${status}: ${detail}`),
      ]),

      new Paragraph({ children: [new PageBreak()] }),
      heading("Use Cases", 1),

      heading("1. The Eternal Dissident Journalist", 2),
      para("Content sharded across nodes; accessible via local meshes, DTN, and sneakernet. Audience pays in BLURT/STONE; node operators earn hosting fees."),
      para("Fit today: STRONG \u2014 provenance + mesh anchors + DTN forward.", { bold: true }),

      heading("2. Creator-Owned Global Media Empire", 2),
      para("Zero platform rent. HTTP Range streaming from neighborhood Pis. Fans seed content; creators keep 95%+ revenue."),
      para("Fit today: MODERATE \u2014 streaming + embed + storage credits live.", { bold: true }),

      heading("3. Resilient Offline-First Disaster Mesh", 2),
      para("After blackout, Pis form local mesh. DTN syncs when uplink returns."),
      para("Fit today: STRONGEST \u2014 DTN, mDNS, TLS proxy, quorum heal.", { bold: true }),

      heading("4. Post-Fediverse Social Universe", 2),
      para("Transparent feeds, forkable moderation, on-chain provenance against deep fakes."),
      para("Fit today: MODERATE \u2014 manifests + provenance verify live.", { bold: true }),

      heading("5. Creative & Scientific Commons (2030+)", 2),
      para("Datasets, papers, and 3D models in the mesh. AI synthesis across the living archive."),
      para("Fit today: EARLY \u2014 spatial manifests + chunk storage.", { bold: true }),

      new Paragraph({ children: [new PageBreak()] }),
      heading("Economic Hyper-Flywheel", 1),
      ...bullets([
        "Creation \u2192 valuable content floods the network",
        "Demand \u2192 storage and bandwidth needs drive STONE value",
        "Infrastructure \u2192 millions run nodes, earning while strengthening the mesh",
        "Innovation \u2192 developers and AIs build new applications",
        "Adoption \u2192 billions of humans and AI agents participate",
        "Compounding \u2192 stronger network \u2192 more content \u2192 higher token value",
      ]),

      heading("Tokenomics Synergy", 2),
      table(
        ["Metric", "Blurt Alone", "Blurt + Bloodstone"],
        [
          ["Utility", "Social rewards", "Social + infrastructure"],
          ["Censorship resistance", "High", "Multi-path resilience"],
          ["Scalability", "Good", "Planetary edge computing"],
          ["Market potential", "Significant", "New internet layer"],
        ],
        [2800, 3280, 3280],
      ),

      heading("Roadmap Phases", 2),
      table(
        ["Phase", "Years", "Focus"],
        [
          ["Spine", "2027 \u2713", "Layers 0\u20135 beta, Waves A\u2013E"],
          ["Scale", "2028\u201329", "Enforce rails, compute jobs, Pi fleet"],
          ["Mesh", "2030\u201332", "Gossip, satellite handoff, offline Condenser"],
          ["Symbiosis", "2033\u201335", "L6 AI, DAO bounties, closed flywheel"],
        ],
        [2200, 2200, 4960],
      ),

      heading("Manifesto", 1),
      new Paragraph({
        spacing: { before: 200, after: 200 },
        alignment: AlignmentType.CENTER,
        children: [new TextRun({
          text: "Blurt + Bloodstone = the permanent, self-owning, AI-augmented nervous system of a free and creative humanity \u2014 running on devices you control and paying you to participate in civilization\u2019s next chapter.",
          italics: true, size: 26, color: "028090",
        })],
      }),

      heading("Call to Action", 2),
      para("We have the keys. We have the partnership. We have the technical foundation."),
      para("Every node spun up, every piece of content published, every developer who joins accelerates this future."),
      para("Let\u2019s build the Symbiotic Stack. Let\u2019s make the internet ours again.", { bold: true }),

      para("Verify live stack: GET /api/convergence/status", { italics: true, size: 20 }),
      new Paragraph({
        children: [new ExternalHyperlink({
          children: [new TextRun({ text: "https://bloodstonewallet.mytunnel.org/api/convergence/status", style: "Hyperlink", size: 20 })],
          link: "https://bloodstonewallet.mytunnel.org/api/convergence/status",
        })],
      }),
    ],
  }],
});

const out = "/root/bloodstone-docs/symbiotic-vision/Bloodstone-Symbiotic-Vision-White-Paper.docx";
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(out, buf);
  console.log("wrote", out, buf.length, "bytes");
});