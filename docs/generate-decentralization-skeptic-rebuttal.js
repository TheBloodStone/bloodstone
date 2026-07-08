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

function quote(text) {
  return new Paragraph({
    spacing: { before: 120, after: 120 },
    indent: { left: 720 },
    children: [new TextRun({ text, italics: true, color: "444444" })],
  });
}

function bullet(ref, text, opts = {}) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80 },
    children: [new TextRun({ text, ...opts })],
  });
}

function roastBlock(title, body) {
  return [h3(title), p(body)];
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
          shading: { fill: "FDE8E8", type: ShadingType.CLEAR },
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
        text: "Bloodstone Is Not Decentralized",
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
        text: "And Other Lazy Takes That Fail a Five-Minute Technical Audit",
        size: 34,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · v1.0 · A deliberately impolite rebuttal",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Disclaimer (read this, critics — it is the only part you will skim)"),
  p(
    "This white paper is rude on purpose. If you opened it hoping for corporate diplomacy, close the tab and go post another drive-by thread titled “not decentralized” without running a node. Bloodstone already publishes sober audit responses. This document exists for the people who keep confusing a website with consensus."
  ),
  p(
    "Nothing here asks you to trust us. Everything here asks you to stop embarrassing yourself in public by using decentralization as a vibes word."
  ),

  h1("Executive summary for people who argue in headlines"),
  bullet(
    "bullets",
    "Bloodstone has a portal. Congratulations — you can see DNS. That does not mean the chain validates on our VPS."
  ),
  bullet(
    "bullets",
    "Thousands of projects ship a default download page. That is onboarding, not topology."
  ),
  bullet(
    "bullets",
    "If your decentralization test is “does it have a .com I dislike,” you are not doing engineering. You are doing performance art."
  ),
  bullet(
    "bullets",
    "Run bloodstoned on your LAN, pull blocks from P2P, mine against your own stratum port, and come back with a failure mode. Otherwise you are noise."
  ),

  h1("What “not decentralized” actually means (for adults)"),
  p(
    "Decentralization is not a sticker you earn by using gray fonts and saying “community” three times. At minimum it means: no single party can unilaterally rewrite history everyone else already validated, and participants can verify the ledger without begging a branded API."
  ),
  p(
    "Bloodstone ships that layer today in open-source bloodstoned: full nodes, pruned nodes, Android full/pruned nodes, LAN stratum, P2P on port 17333, local RPC, wallets that stay on your device, and mesh chunk replication with on-chain anchors. You can hate our landing page and still be wrong about consensus."
  ),
  quote(
    "“It is centralized because I saw a domain name.” — the intellectual equivalent of calling a restaurant a farm because menus exist."
  ),

  h1("The five dumbest arguments, ranked"),
  ...roastBlock(
    "1. “The explorer is on one domain, therefore the chain is fake”",
    "Explorers are indexes. They are allowed to be convenient. Bitcoin has block explorers too; nobody serious claims Bitcoin consensus lives inside mempool.space. If you cannot separate indexing from validation, please stop reviewing infrastructure — you are reviewing CSS."
  ),
  ...roastBlock(
    "2. “Default seeds are operator IPs, therefore nobody else runs nodes”",
    "Seeds are hints for first boot, not a census of the network. Every new full node becomes a peer other installations can learn from. Saying narrow seeds prove centralization is like saying Google Maps proves only Google employees drive cars."
  ),
  ...roastBlock(
    "3. “The pool dashboard is hosted, therefore hashrate is imaginary”",
    "Pool accounting is a coordination layer. Shares still come from real workers — phones, browsers, desktops, ASICs, LAN forwarders. You can solo mine on your LAN without the dashboard open. Confusing payout UX with proof-of-work is how you end up confidently wrong on a public forum."
  ),
  ...roastBlock(
    "4. “Android APK downloads from a URL, therefore keys are custodial”",
    "The APK bundles offline UI and can run a local node with on-device keys. Downloading software from a URL is how software has worked since the 1990s. If that is your decentralization bar, uninstall everything except whatever you compiled after reading every line of kernel source — and enjoy your very lonely utopia."
  ),
  ...roastBlock(
    "5. “They admit Phase 1 is centralized, checkmate”",
    "Admitting bootstrap reality is honesty, not surrender. Mature networks also had early operator-mediated phases. The question is whether independent validation exists underneath the convenience layer. It does. Read the other white papers or, radical idea, run the binaries."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("Things that are decentralized enough to hurt your narrative"),
  p("Independent of portal, explorer, faucet, or pool UI:"),
  bullet("bullets", "Full bloodstoned sync and validation on Linux, Windows, Raspberry Pi ARM64, and Android full mode."),
  bullet("bullets", "Pruned nodes that keep a local tip without re-downloading the entire history every Tuesday."),
  bullet("bullets", "LAN mining: mDNS discovery, local stratum ports, household ASIC forwarding without exposing 192.168.x.x to the public internet."),
  bullet("bullets", "Chain Mesh peers storing chunks on user hardware; BSM1 anchors tie published assets to chain state."),
  bullet("bullets", "Desktop and Android miners that bundle the same UI and can operate against a local node you control."),
  bullet("bullets", "Solo paths that do not require signing into our web wallet to prove work happened."),

  h2("Things that are centralized today (we already said this — try listening)"),
  p(
    "Bloodstone does not claim the web stack is fully federated yet. Default onboarding, proportional pool payouts, explorer indexing, faucet, and mesh catalog APIs are operator-hosted convenience. That is Phase 1. Pretending we deny it makes you look like you never read the docs you claim to audit."
  ),

  h2("The two-layer model (for critics who hate nuance)"),
  table(
    ["Layer", "What it is", "Decentralized?", "What critics do instead"],
    [
      [
        "Coordination plane",
        "Portal, downloads page, pool dashboard, explorer UI, faucet",
        "Mostly no — by design in Phase 1",
        "Point at it and declare victory without testing nodes",
      ],
      [
        "Validation plane",
        "bloodstoned P2P, local RPC, LAN stratum, mesh chunk peers",
        "Yes — independently runnable",
        "Ignore it because it is not a screenshot",
      ],
      [
        "Edge capacity",
        "Phones, PCs, Pi nodes, LAN forwarders, mesh storage",
        "Distributed across users",
        "Call it “VPS fleet” because counting is hard",
      ],
    ],
    [2200, 2800, 2200, 2160]
  ),

  h1("A minimal test suite for people who want to be taken seriously"),
  p("If you still say “not decentralized,” name which step failed:"),
  bullet(
    "tests",
    "Install bloodstoned from the public downloads host. Disconnect the portal in your firewall. Does the node still sync from P2P peers?"
  ),
  bullet(
    "tests",
    "Start the Android miner APK in full-node mode on Wi‑Fi. Does LAN stratum respond without loading the live portal?"
  ),
  bullet(
    "tests",
    "Point a Bitaxe or cpuminer at your LAN IP and local stratum port. Do shares arrive while the public dashboard is closed?"
  ),
  bullet(
    "tests",
    "Fetch a mesh-anchored release artifact by chunk key and verify the hash against the anchor metadata."
  ),
  bullet(
    "tests",
    "Run two nodes on different ISPs. Do they propagate blocks to each other without our SSH password?"
  ),
  p(
    "If you will not run any of these, your opinion is a mood board. Post it on social media between cat photos where it belongs."
  ),

  h1("Why the hot take persists anyway"),
  ...roastBlock(
    "Incentive alignment for critics",
    "Calling everything centralized is low effort and high engagement. You do not need receipts. You need a frown emoji and the word “scam” in the replies. Bloodstone ships binaries; critics ship vibes."
  ),
  ...roastBlock(
    "Category error",
    "Many critics evaluate a young network using the maturity checklist of a forty-year-old chain with hundreds of independent explorers and decades of DNS seeds — then act shocked when a relaunched project still has a default download page. That is not analysis. That is moving the goalposts with a forklift."
  ),
  ...roastBlock(
    "Bad-faith equivalence",
    "Pointing at hosted UX and ignoring user-run validators is like reviewing email and concluding SMTP cannot work because Gmail has a login screen."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("What we are actually building (since you will misquote this)"),
  p(
    "Bloodstone’s stated model is progressive decentralization: centralized bootstrap and operator-mediated UX early, with validation, storage, and LAN mining at the edges now, and a roadmap to make the convenience layer optional. That is a engineering plan, not a marketing prayer."
  ),
  p(
    "Every household full node, every Android device keeping a pruned tip, every mesh peer holding chunks, every LAN forwarder reporting real terahashes — that is decentralization in the only sense that matters for a chain: more copies of the truth, more places work is done, less single-point fragility for history and liveness."
  ),

  h1("Closing remarks (the rude part, condensed)"),
  p(
    "If you say Bloodstone is not decentralized because we have a website, you are not making a technical argument. You are telling the world you do not know what a node is."
  ),
  p(
    "If you say it because you tried none of the independent paths, you are not skeptical. You are lazy."
  ),
  p(
    "If you say it because nuance does not fit in a quote-tweet, that is fair — just do not pretend you audited anything."
  ),
  quote(
    "Decentralization is measured in running software, not in posting software."
  ),
  p(
    "Run a node. Mine on your LAN. Break something. File a real bug. Until then, keep your “not decentralized” take in the same folder as “Bitcoin is centralized because Coinbase has an app” — next to other masterpieces you never tested."
  ),

  h1("Further reading (for people who can read)"),
  bullet("refs", "Bloodstone Decentralized Network White Paper — node types and architecture."),
  bullet("refs", "Bloodstone Infrastructure Independence White Paper — control plane vs validation plane."),
  bullet("refs", "Bloodstone Infrastructure Audit Point-by-Point Rebuttal — sober version of this document."),
  bullet("refs", "Bloodstone How The Network Works — plain-language guide for humans who are not trying to win an argument in twelve words."),
];

const doc = new Document({
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
        reference: "tests",
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
        reference: "refs",
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
    ],
  },
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
                  text: "Bloodstone — Decentralization Skeptic Rebuttal (v1.0)",
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
  "/root/bloodstone-docs/Bloodstone-Decentralization-Skeptic-Rebuttal.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath);
});