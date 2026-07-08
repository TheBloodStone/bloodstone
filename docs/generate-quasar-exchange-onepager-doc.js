#!/usr/bin/env node
/** Bloodstone QUASAR Exchange One-Pager — DOCX generator. */
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
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  PageNumber,
  ExternalHyperlink,
} = require("docx");

const COORDINATOR = "https://bloodstonewallet.mytunnel.org";
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function h1(t) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
}
function h2(t) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
}
function p(t, bold = false) {
  return new Paragraph({
    spacing: { after: 140 },
    children: [new TextRun({ text: t, bold })],
  });
}
function link(text, url) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [
      new ExternalHyperlink({
        children: [new TextRun({ text, style: "Hyperlink", color: "5B21B6" })],
        link: url,
      }),
    ],
  });
}
function cell(text, header = false) {
  return new TableCell({
    borders,
    width: { size: 4680, type: WidthType.DXA },
    shading: header ? { fill: "F4F4F5", type: ShadingType.CLEAR } : undefined,
    children: [new Paragraph({ children: [new TextRun({ text, bold: header })] })],
  });
}

const children = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [
      new TextRun({ text: "Bloodstone QUASAR", bold: true, size: 32, color: "5B21B6" }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 280 },
    children: [
      new TextRun({
        text: "Exchange Integrator One-Pager · 51% Defense · v1.0 · July 2026",
        size: 22,
        color: "666666",
      }),
    ],
  }),
  p("TL;DR: Bloodstone is triple-PoW (SHA256d + Neoscrypt + Yespower). Rented SHA256 does not equal chain takeover. Run your own exchange node. Use dynamic confirmations when QUASAR signals braid skew or witness split.", true),
  p('Tagline: "You don\'t need 51% of one hash. You need 51% of reality."'),
  h2("Listing quick facts"),
  new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({ children: [cell("Item", true), cell("Value", true)] }),
      new TableRow({ children: [cell("Ticker"), cell("STONE")] }),
      new TableRow({ children: [cell("PoW algorithms"), cell("SHA256d, Neoscrypt, Yespower")] }),
      new TableRow({ children: [cell("Default deposit confirms"), cell("6 (increase per QUASAR signals)")] }),
      new TableRow({ children: [cell("Listing JSON"), cell("/api/exchange")] }),
      new TableRow({ children: [cell("ElectrumX SSL"), cell("ssl://bloodstonewallet.mytunnel.org:50002")] }),
      new TableRow({ children: [cell("Never use"), cell("Pool VPS RPC for deposit detection")] }),
    ],
  }),
  h2("QUASAR layers (exchange relevance)"),
  new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({
        children: [cell("Layer", true), cell("Status", true), cell("Action", true)],
      }),
      new TableRow({
        children: [cell("L1–L2 Multi-algo + weighted work"), cell("Live"), cell("Understand three attack markets")],
      }),
      new TableRow({
        children: [cell("L3 Epoch braid finality"), cell("Phase 1"), cell("Bump confirms if SHA256-heavy epoch")],
      }),
      new TableRow({
        children: [cell("L4–L5 Mesh + LAN witnesses"), cell("Phase 2"), cell("Halt on witness split")],
      }),
      new TableRow({
        children: [cell("L6 Exchange witness policy"), cell("Phase 1"), cell("Poll with /api/exchange")],
      }),
      new TableRow({
        children: [cell("L7 Pool tripwires"), cell("Phase 2"), cell("Alert on rental spike / orphan shadow")],
      }),
    ],
  }),
  h2("Recommended confirmation policy"),
  p("• Normal braid + stable node tip → 6 confirmations"),
  p("• SHA256d-heavy epoch (>85% one algo) → 12–20 confirmations"),
  p("• Witness disagreement (when live) → halt deposits, manual review"),
  p("• Pool tripwire: possible private fork → halt + alert"),
  h2("Integrator checklist"),
  p("1. Deploy bloodstone-exchange-node package (txindex=1, own hot wallet)"),
  p("2. Poll /api/exchange + (when live) /api/quasar/status"),
  p("3. Compare getblockchaininfo / getchaintips before large credits"),
  p("4. Read full white paper: Bloodstone-QUASAR-51-Percent-Defense-White-Paper"),
  h2("Links"),
  link("Exchange listing pack", `${COORDINATOR}/exchange/`),
  link("QUASAR landing", `${COORDINATOR}/quasar/`),
  link("Downloads / RPC reference", `${COORDINATOR}/downloads/`),
  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({
        text: "Bloodstone · STONE mainnet · Built with Grok Build",
        italics: true,
        size: 20,
        color: "888888",
      }),
    ],
  }),
];

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
  },
  sections: [
    {
      properties: {
        page: { margin: { top: 1200, right: 1200, bottom: 1200, left: 1200 } },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              alignment: AlignmentType.RIGHT,
              children: [new TextRun({ text: "QUASAR · Exchange One-Pager", size: 18, color: "888888" })],
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

const outPath = "/root/bloodstone-docs/Bloodstone-QUASAR-Exchange-One-Pager.docx";
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath, buffer.length, "bytes");
});