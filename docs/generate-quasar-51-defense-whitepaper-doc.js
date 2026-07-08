#!/usr/bin/env node
/** Bloodstone QUASAR 51% Defense — DOCX generator. */
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
function quote(text) {
  return new Paragraph({
    spacing: { after: 160, before: 80 },
    indent: { left: 720 },
    children: [new TextRun({ text, italics: true, color: "444444" })],
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
          shading: { fill: "E8D5F0", type: ShadingType.CLEAR },
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
      new TextRun({ text: "Bloodstone QUASAR Defense", bold: true, size: 32 }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "A Software Stack Against 51% Attacks",
        size: 24,
        color: "5B21B6",
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [
      new TextRun({
        text: "QUorum Adaptive Security Against Reorgs · v1.0 · July 2026",
        size: 20,
        color: "666666",
      }),
    ],
  }),

  h1("Executive summary"),
  p(
    "A 51% attack is a budget problem: produce a private fork with more valid work than the public chain, outrun honest propagation, and double-spend. Bloodstone answers with QUASAR — seven software layers that multiply attacker cost."
  ),
  quote(
    "Bloodstone treats 51% resistance as a distributed immune system. The chain does not ask 'do you have 51% of one number?' It asks 'can you forge an alternate universe where three clocks, thousands of phones, mesh anchors, and exchange policy all agree you won?'"
  ),
  p("Layers L1–L2 are live in Core. L3–L7 are the QUASAR envelope — deployable without replacing PoW.", { bold: true }),

  h1("The hydra — seven layers"),
  table(
    ["Layer", "Name", "Status"],
    [
      ["L1", "Triple-Purpose PoW (SHA256d + Neoscrypt + Yespower)", "Live"],
      ["L2", "Tri-Algo Work Tensor (weighted nChainWork)", "Live"],
      ["L3", "Epoch Braid Finality (E-BF)", "Phase 1"],
      ["L4", "Mesh Witness Capsules (BSM1)", "Phase 2"],
      ["L5", "LAN Echo Quorum (mDNS fleet)", "Phase 2"],
      ["L6", "Exchange Witness Policy", "Phase 1"],
      ["L7", "Anomaly Tripwire (pool telemetry)", "Phase 2"],
    ],
    [800, 6560, 2000]
  ),

  new PageBreak(),

  h1("Layer 1–2 — Consensus physics (live)"),
  p(
    "Three independent PoW algorithms with separate Dark Gravity retargeting. Chain tip uses weighted cumulative work — powAlgoLog2Weight: SHA256d = 6, Neoscrypt = 10, Yespower = 22. SHA256d dominance does not translate 1:1 into chain decision power."
  ),
  table(
    ["Algorithm", "Attacker profile", "Weight"],
    [
      ["SHA256d", "Rented ASIC / Bitaxe", "Low (2^6)"],
      ["Neoscrypt", "GPU / LAN miners", "Medium (2^10)"],
      ["Yespower", "Phones, laptops, Pi", "High (2^22)"],
    ],
    [2800, 4560, 2000]
  ),

  h1("Layer 3 — Epoch Braid Finality"),
  p(
    "Finality as a braid across algorithms, not a single height. Each epoch (~15 min) tracks blocks per algo. Settlement-grade state requires braid balance — skewed SHA256d-only epochs trigger DEFERRED_FINALITY in wallets and exchanges without a hard fork."
  ),
  bullet("bullets", "Node policy flags braid skew before deep confirmations"),
  bullet("bullets", "/api/exchange can expose confirmation multipliers"),

  h1("Layer 4 — Mesh Witness Capsules"),
  p(
    "Android, LAN, and exchange nodes publish signed witness capsules (tip hash, per-algo work, peer count) to chain mesh with optional BSM1 anchors. Exchanges add witness_quorum_depth to effective confirmations."
  ),
  p("Sybil-resistant: capsules cost real sync + mesh publish + anchor fees, not anonymous HTTP votes."),

  h1("Layer 5 — LAN Echo Quorum"),
  p(
    "Household pruned/full nodes on Wi-Fi cross-attest tips via mDNS. Split-brain between pool VPS and LAN fleet surfaces in miner UI before exchanges credit deposits. Physical locality — not global VPS Sybils."
  ),

  new PageBreak(),

  h1("Layer 6–7 — Exchange policy + tripwire"),
  table(
    ["Signal", "Response"],
    [
      ["Braid healthy + witness quorum ≥ 3", "Standard 6 confirmations"],
      ["Braid skewed (SHA256d-heavy)", "12–20 confirmations"],
      ["Witness split", "Halt deposits"],
      ["SHA256d share surge (tripwire)", "Alert + auto-bump confirmations"],
    ],
    [4680, 4680]
  ),

  h1("Attack scenarios — five humiliations"),
  h3("Rent SHA256 and reorg 6 blocks"),
  p(
    "Attacker wins SHA256d lane → braid skew defers finality → mesh + LAN witnesses disagree → exchange policy blocks shallow credit → tripwire already fired. Expensive, loud, slow."
  ),
  h3("Sybil fake nodes"),
  p("HTTP Sybils are cheap. BSM1 mesh capsules + LAN radio locality are not."),
  h3("Pool 51%, not chain 51%"),
  p("Pool dominance affects payouts, not canonical tip on full nodes. QUASAR separates pool economics from consensus."),

  h1("What QUASAR is not"),
  bullet("bullets", "Does not replace PoW — amplifies multi-algo PoW"),
  bullet("bullets", "Phones do not vote on consensus — they observe and attest"),
  bullet("bullets", "Not zero risk — raises cost, time, and detectability"),

  h1("Roadmap"),
  table(
    ["Phase", "Deliverable"],
    [
      ["Now", "L1–L2 live in Core 0.7.x"],
      ["Phase 1", "Braid status in explorer + exchange API"],
      ["Phase 2", "Witness capsules, LAN Echo, pool tripwire"],
      ["Phase 3", "Optional consensus-enforced braid (research)"],
    ],
    [2200, 7160]
  ),

  new Paragraph({ spacing: { before: 320 } }),
  quote("You don't need 51% of one hash. You need 51% of reality."),
  linkPara("Markdown edition", `${COORDINATOR}/downloads/Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md`),
  linkPara("Economic white paper", `${COORDINATOR}/downloads/Bloodstone-Economic-Model-White-Paper.docx`),
  linkPara("Blurt 51% response", `${COORDINATOR}/downloads/Bloodstone-Blurt-Partnership-Response.md`),
  p("Bloodstone · QUASAR 51% Defense · July 2026", { italics: true, color: "666666" }),
];

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT }],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              alignment: AlignmentType.RIGHT,
              children: [
                new TextRun({ text: "Bloodstone · QUASAR Defense", size: 18, color: "666666" }),
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

const outPath = "/root/bloodstone-docs/Bloodstone-QUASAR-51-Percent-Defense-White-Paper.docx";
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath, buffer.length, "bytes");
});