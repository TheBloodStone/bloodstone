#!/usr/bin/env node
/** Bloodstone — Why No GitHub / Development Velocity white paper (DOCX). */
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
function bullet(ref, text) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80 },
    children: [new TextRun(text)],
  });
}
function quote(text) {
  return new Paragraph({
    spacing: { after: 160, before: 80 },
    indent: { left: 720 },
    children: [new TextRun({ text, italics: true })],
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
    children: [
      new TextRun({
        text: "Bloodstone Development Velocity & Source Distribution",
        bold: true,
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [
      new TextRun({
        text: "Why We Do Not Maintain a Public GitHub",
        size: 24,
      }),
    ],
  }),
  p("Document version: 1.0 · July 2026", { italics: true }),
  p("Audience: Partners, exchanges, integrators, contributors", { italics: true }),
  linkPara("Coordinator portal", COORDINATOR),

  h1("Executive summary"),
  p(
    "Bloodstone does not maintain a single public GitHub repository tracking every production change. That is deliberate: we ship across Core node, Qt wallet, Android APK, web OTA bundles, pool VPS, portal APIs, chain mesh assets, and partner documents — often multiple versioned artifacts per day."
  ),
  p(
    "Forcing each change through public Git workflow (commit, push, PR, CI, release tag) would slow delivery from hours to days without improving what users download. We publish verifiable artifacts instead: SHA-256 checksums, BSM1 mesh anchors, OTA bundles, and API listing packs."
  ),

  h1("1. The question partners ask"),
  quote('"Where is your GitHub? How do we audit the code?"'),
  table(
    ["Expectation", "Bloodstone today"],
    [
      ["One git clone builds everything", "No — spans C++, Java, Python, Electron, nginx"],
      ["Every fix has a public commit hash", "Partial — Core heritage is public; relaunch ships as binaries"],
      ["Releases lag development by one PR", "No — we optimize time-to-downloadable-artifact"],
    ],
    [3120, 6240]
  ),

  h1("2. What we maintain"),
  table(
    ["Layer", "Examples", "Versioning"],
    [
      ["Core node", "bloodstoned, bloodstone-cli, Qt", "Semver 0.7.x"],
      ["Android", "Full node, LAN pool, stratum", "APK 1.3.84+"],
      ["Web miner UI", "Capacitor OTA", "1.3.129-web+ (independent)"],
      ["Pool / portal", "Stratum VPS, exchange API", "Env deploy"],
      ["Mesh / docs", "White papers, packages", "BSM1 anchors"],
    ],
    [2200, 3580, 3580]
  ),
  p(
    "A single GitHub repo cannot represent this without monorepo chaos or multi-repo overhead — both assume pull-request speed. Bloodstone moves at OTA speed."
  ),

  h1("3. Development at operational velocity"),
  h2("3.1 Parallel version streams"),
  bullet(
    "bullets",
    "Android APK, web OTA, and Core can advance on the same day without blocking each other."
  ),
  bullet(
    "bullets",
    "LAN pool fixes ship in Java while Windows Qt cross-compile continues independently."
  ),
  bullet("bullets", "Partner documents publish to mesh within hours of technical decisions."),

  h2("3.2 Hidden cost of pushing to GitHub"),
  table(
    ["Step", "Time cost", "Impact"],
    [
      ["Clean commit + push", "5–15 min", "Context-switch from live testing"],
      ["Wait for CI", "10–60 min", "Blocks next experiment"],
      ["PR / review hygiene", "30 min – hours", "Unacceptable when pool is down"],
      ["Changelog + version sync", "15–45 min", "Multiple packages must align"],
      ["GitHub Release upload", "15–30 min", "Duplicates /downloads/ + mesh work"],
    ],
    [2800, 2200, 4360]
  ),
  quote(
    "We develop at the speed the network needs, not at the speed GitHub etiquette prefers."
  ),

  h2("3.3 Upload-between-versions stall"),
  p(
    "If every fix required full GitHub sync across Android, miner-web, portal, ops scripts, and docs — then GitHub Release uploads for each artifact — that is release theatre. Users already get checksum-verified files from /downloads/ and mesh."
  ),

  h1("4. What we publish instead"),
  h3("Downloads portal"),
  p("Binaries and documents with SHA-256 sidecars at bloodstonewallet.mytunnel.org/downloads/"),
  h3("Chain mesh (BSM1)"),
  p("Content-addressed chunks, Merkle root, on-chain anchor, stable asset_key."),
  h3("OTA web bundles"),
  p("Android miner UI updates without APK reinstall — path GitHub Releases cannot replicate."),
  h3("API listing packs"),
  p("/api/exchange and related endpoints — the machine-readable contract for integrators."),
  h3("Upstream C++ heritage"),
  p("SpaceXpanse rod-core-wallet remains the public consensus architecture reference."),

  h1("5. Trade-offs"),
  h2("What we gain"),
  bullet("gain", "Velocity — pool fix, OTA, and doc same day."),
  bullet("gain", "Operational focus — test on live seeds/VPS/devices."),
  bullet("gain", "Simpler partner story — download, verify SHA-256, call API."),
  bullet("gain", "Reduced secret-leak and fork-confusion risk."),
  h2("What we give up"),
  bullet("lose", "No single git clone of full stack."),
  bullet("lose", "No standard community PR workflow."),
  bullet("lose", "Partners audit binaries + docs, not every diff."),
  bullet("lose", "Some listings penalize missing public repos."),

  h1("6. How hard would a GitHub mirror be?"),
  p("Technically feasible. Operationally expensive."),
  table(
    ["Activity", "Hours / week"],
    [
      ["Commit + push across repos", "8–15"],
      ["CI (Linux, Windows, Android)", "5–10"],
      ["Release tags vs downloads", "3–5"],
      ["Issue / PR triage on stale code", "2–8"],
      ["Secret scrubbing", "2–5"],
      ["Total", "20–43"],
    ],
    [6240, 3120]
  ),
  p(
    "That is half to full time of one engineer — solely to keep GitHub as current as our downloads page already is. Quarterly snapshot dumps mislead users (stale, non-building) while adding maintenance."
  ),

  h1("7. Integrator checklist today"),
  bullet("numbers", "Verify SHA-256 from /downloads/*.sha256"),
  bullet("numbers", "Read /api/exchange listing pack"),
  bullet("numbers", "Check BSM1 mesh anchors for critical packages"),
  bullet("numbers", "Study upstream rod-core-wallet for consensus context"),
  bullet("numbers", "Read white papers; contact us for partner packs"),

  h1("8. Future options (not commitments)"),
  bullet("future", "Tagged Core snapshot repo at semver releases only"),
  bullet("future", "Open docs + API specs repo without VPS scripts"),
  bullet("future", "Reproducible build guide for Core verification"),
  p("We will not promise real-time GitHub parity with VPS iteration."),

  h1("9. Conclusion"),
  p(
    "Bloodstone chooses artifact velocity over repository theatre. Maintaining a public GitHub mirroring our work would cost 20–40+ engineer-hours per week and slow the delivery path users rely on — without replacing downloads, mesh anchors, or API packs."
  ),
  p(
    "The portal GitHub link points to upstream heritage (SpaceXpanse rod-core-wallet). Bloodstone's relaunch layer ships as built, verified, documented releases — because that keeps STONE infrastructure moving at operational speed.",
    { italics: true }
  ),

  new Paragraph({ children: [new PageBreak()] }),
  h1("Related documents"),
  linkPara(
    "Development Journey White Paper",
    `${COORDINATOR}/downloads/Bloodstone-Development-Journey-White-Paper.docx`
  ),
  linkPara(
    "Infrastructure Independence White Paper",
    `${COORDINATOR}/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx`
  ),
  linkPara(
    "Chain Mesh Storage White Paper",
    `${COORDINATOR}/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx`
  ),
  linkPara(
    "LAN Pool Coordinator Guide",
    `${COORDINATOR}/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md`
  ),
  p("Bloodstone · Development velocity & source distribution · July 2026", { italics: true, size: 20 }),
];

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT }],
      },
      {
        reference: "gain",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "+", alignment: AlignmentType.LEFT }],
      },
      {
        reference: "lose",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "−", alignment: AlignmentType.LEFT }],
      },
      {
        reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT }],
      },
      {
        reference: "future",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "○", alignment: AlignmentType.LEFT }],
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
                new TextRun({
                  text: "Bloodstone · Development velocity",
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
  "/root/bloodstone-docs/Bloodstone-Why-No-GitHub-Development-Velocity-White-Paper.docx";
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath, buffer.length, "bytes");
});