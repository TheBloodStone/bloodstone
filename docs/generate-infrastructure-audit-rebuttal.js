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

function pointBlock(title, response) {
  return [
    h3(title),
    p(response),
  ];
}

const children = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [
      new TextRun({
        text: "Bloodstone Infrastructure Audit",
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
        text: "Point-by-Point Technical Rebuttal",
        size: 36,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Response to external infrastructure review and follow-up",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Purpose"),
  p(
    "This document answers the external infrastructure review posted on Blurt (including the follow-up on governance and verification interactions). Corrections are technical and verifiable — not rhetorical appeals to trust."
  ),
  p(
    "Bloodstone agrees with much of the audit as a description of the application and onboarding layer. We disagree with the conclusion that nothing in the network operates independently of the hosted coordination plane."
  ),

  h1("Part 1 — Original Review"),
  ...pointBlock(
    "Participation is not the same as independence",
    "Agreed for the application and coordination layer (portal, pool dashboard, explorer, faucet, mesh catalog API). Incomplete as a blanket statement: bloodstoned full and pruned nodes validate chain state locally on P2P (port 17333). That is independence at the consensus layer regardless of pool UI participation."
  ),
  ...pointBlock(
    "Explorer, wallet, faucet, and mining coordination rely on central endpoints",
    "Correct for default onboarding and UX. Incorrect to infer that chain validation, solo mining, or LAN mining require those endpoints. Independently verifiable without the portal: local RPC (bloodstoned, default port 18340), LAN stratum from a local node, and the Android APK bundled offline UI."
  ),
  ...pointBlock(
    "Onboarding and bootstrap resolve to limited entry points",
    "Correct today — Phase 1 bootstrap is operator-mediated and documented in the Decentralized Network White Paper. Does not mean the only nodes that exist are those seeds. Each new full node becomes P2P infrastructure other installations can peer with."
  ),
  ...pointBlock(
    "Seed distribution appears narrow or centrally mediated",
    "Correct observation. Default relaunch instructions use known operator endpoints, not a mature multi-operator DNS seed ecosystem. Wrong implication: narrow seeds prove there is no decentralized validation layer. Seeds are the default on-ramp, not the full network topology."
  ),
  ...pointBlock(
    "Decentralized VPS distributes execution, not control",
    "Half right. Pool proportional accounting, dashboard stats, explorer indexing, and faucet are coordinated today. Also distributed today: hashrate from fleet devices, native Android stratum TCP offload, local bloodstoned on phones/PCs, mesh chunk storage on user devices, LAN mining with mDNS discovery. The label describes capacity distribution plus edge nodes — not a claim that every device is sovereign infrastructure."
  ),
  ...pointBlock(
    "No third-party explorers, independent repos, or distributed bootstrap list",
    "Fair as a maturity comparison to Bitcoin-era ecosystems. Incomplete as proof nothing independent exists: node binaries and APKs at the public downloads host; independently runnable bloodstoned daemon; Chain Mesh replication of chunks and release artifacts with on-chain BSM1 anchors. We do not claim third-party explorer parity today."
  ),
  ...pointBlock(
    "Not alleging fraud — only what is publicly verifiable",
    "Accepted framing. This response uses the same standard."
  ),
  ...pointBlock(
    "What operates independently of the hosted control layer?",
    "Yes — independently of portal, explorer, faucet, and pool UX: full nodes (sync, validate, propagate on P2P); pruned/full Android nodes (local chain tip, LAN RPC/stratum, on-device wallet keys); solo LAN mining; LAN client mode via mDNS; Chain Mesh peers (LAN serve port 18341); BSM4 peer gateway egress. Still VPS-dependent today: proportional pool payouts, explorer, faucet, default mesh catalog API, default first-time binary download path."
  ),
  ...pointBlock(
    "If independent infrastructure exists, point to it without the same domain cluster",
    "Point to behavior, not a domain. See verification tests in Section 3. Any correction should name which test failed and what was observed."
  ),
  ...pointBlock(
    "Decentralization language needs a narrower technical sense than presentation",
    "Agreed. Precise claim: centralized bootstrap and UX today; decentralized validation and edge capacity shipping now; roadmap to make the convenience layer optional."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("Part 2 — Follow-Up (Blurt and Discord)"),
  ...pointBlock(
    "Structured verification request — response did not address technical questions",
    "Acknowledged. Technical questions deserve technical answers. This document is that answer. Redirecting to authority or status is not a rebuttal."
  ),
  ...pointBlock(
    "Discord dismissals instead of architectural clarification",
    "Agreed — that was wrong. Dismissive responses do not refute the audit; they fail the standard both sides claim to want. Poor community conduct is not proof the audit is wrong. Architecture should be settled in writing with reproducible tests."
  ),
  ...pointBlock(
    "Whitepaper alignment — centralized bootstrap, decentralized validation, roadmap",
    "No contradiction between the whitepaper and the audit. Agreement: project-controlled seeds and VPS onboarding today (Phase 1). Disagreement with the audit conclusion: nothing independent exists — contradicted by shipped node, LAN, and mesh paths."
  ),
  table(
    ["Term", "Definition (reviewer)", "Bloodstone position"],
    [
      [
        "Bootstrap independence",
        "Join without project seeds, APIs, or onboarding",
        "Not achieved today — acknowledged",
      ],
      [
        "Consensus independence",
        "Validate and propagate blocks without centralized authority after sync",
        "Achieved today — any synced bloodstoned instance",
      ],
    ],
    [2800, 3280, 3280]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "The audit inspected bootstrap and UX layers and concluded the network lacks independence. That conflates bootstrap dependence with consensus dependence."
  ),

  h1("Section 3 — Verification Tests"),
  p(
    "If the claim were nothing works without the portal, these procedures falsify it. Auditors may reproduce them without privileged access."
  ),
  table(
    ["#", "Test", "Procedure", "Expected (portal offline)"],
    [
      ["1", "Android LAN node", "Install miner APK, start pruned/full node", "LAN RPC and stratum on Wi-Fi"],
      ["2", "Local full node RPC", "Run bloodstoned; query via bloodstone-cli", "Chain queries succeed"],
      ["3", "Solo LAN mining", "Point LAN miner at local stratum in solo mode", "Work from local chain state"],
      ["4", "Mesh LAN chunk fetch", "Fetch from http://<lan-ip>:18341/", "Bytes served by peer"],
      ["5", "Peer internet gateway", "Phone on mobile data as BSM4 gateway for LAN miner", "Egress via peer device"],
    ],
    [400, 1800, 3580, 3580]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("Section 4 — Summary Matrix"),
  table(
    ["Reviewer point", "Our answer"],
    [
      ["Participation ≠ independence", "True for UX; false as blanket statement"],
      ["Everything hits central endpoints", "True for default onboarding"],
      ["Seeds are narrow", "True; roadmap and peer growth acknowledged"],
      ["Decentralized VPS = execution not control", "True for pool; incomplete for nodes, mesh, LAN"],
      ["No third-party explorers/repos", "Fair gap; does not negate runnable nodes"],
      ["Not alleging fraud", "Same standard we use here"],
      ["What runs without control layer?", "Section 3 tests"],
      ["Blurt/Discord avoided tech answers", "Agreed — answered here"],
      ["Whitepaper admits central bootstrap", "Agreed — Phase 1 by design"],
      ["Bootstrap ≠ consensus independence", "Correct distinction; audit blurred it"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("Closing"),
  p(
    "Bloodstone is not claiming a fully decentralized application stack today. We are claiming — and shipping — a hybrid model: centralized bootstrap and UX now; independently operable validation, LAN mining, and mesh replication at the edges; explicit engineering path (Phases 1–4) to make convenience hosts optional for liveness and history."
  ),
  p(
    "If any statement in this document is incorrect, the correction should name which verification test failed, which layer (consensus vs. coordination vs. UX), and what observable behavior contradicted it. We will respond in kind."
  ),

  new Paragraph({
    spacing: { before: 400 },
    children: [new TextRun({ text: "Document version: 1.0 · July 2026", italics: true, size: 20 })],
  }),
  p("Related documents:"),
  linkPara(
    "Infrastructure Independence White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx"
  ),
  linkPara(
    "Decentralized Network White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Decentralized-Network-White-Paper.docx"
  ),
  linkPara(
    "Chain Mesh Storage White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  linkPara("Bloodstone downloads", "https://bloodstonewallet.mytunnel.org/downloads/"),
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
                  text: "Bloodstone Infrastructure Audit — Point-by-Point Rebuttal",
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
  "/root/bloodstone-docs/Bloodstone-Infrastructure-Audit-Point-by-Point-Rebuttal.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});