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
    children: [
      new TextRun({
        text: "Bloodstone Infrastructure Independence",
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
        text: "White Paper — Separating the Control Plane from Consensus",
        size: 32,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({
        text: "July 2026 · Response to external infrastructure audit",
        size: 24,
        italics: true,
      }),
    ],
  }),

  h1("Executive Summary"),
  p(
    "External reviewers who inspect the Bloodstone portal, explorer, mining dashboard, wallet, faucet, and seed-node instructions often conclude that the entire network resolves to a small set of centrally hosted endpoints — a single-host control plane with multiple front-facing interfaces. That observation is partly correct for the application and onboarding layer. It is not a complete description of the network architecture."
  ),
  p(
    "Bloodstone operates two distinct layers today: a centralized bootstrap and coordination plane (portal, pool accounting, explorer, faucet, mesh catalog API) and an independently operable chain-validation and edge-mining plane (bloodstoned full and pruned nodes, LAN discovery, mesh peer storage, household gateways). Consensus truth is enforced by proof-of-work nodes running bloodstoned, not by the VPS dashboard. The long-term engineering goal — documented openly as a four-phase roadmap — is to make the convenience layer optional while validation, mining, and archival capacity grow at the edges."
  ),
  p(
    "This white paper answers the audit question directly: yes, independently operated infrastructure exists that is not ultimately dependent on project-hosted VPS services for chain validation, solo mining, LAN mining, peer chunk recovery, or household internet relay. It also acknowledges, without hedging, which services remain VPS-dependent today and what external auditors should test to verify the distinction."
  ),

  h1("1. The Audit Observation"),
  h2("1.1 What reviewers see"),
  p(
    "A thorough review of the public Bloodstone stack surfaces a consistent pattern: the portal, explorer, wallet UI, faucet, mining coordination APIs, download pages, and default seed instructions route users to project-operated infrastructure under a single domain family, with hardcoded seed IPs rather than a federated bootstrap list maintained by independent operators."
  ),
  p("From an outside audit of the web-facing layer, the following conclusions are fair:"),
  bullet(
    "bullets",
    "Onboarding flows default to project VPS endpoints for binaries, pool configuration, and dashboard features."
  ),
  bullet(
    "bullets",
    "Explorer indexing, faucet distribution, and proportional pool accounting are hosted services, not on-chain consensus."
  ),
  bullet(
    "bullets",
    "Chain Mesh manifest and catalog APIs are coordinator-hosted; default internet egress for BSM4 tunnels uses a coordinator mesh-gateway role."
  ),
  bullet(
    "bullets",
    "Seed and relaunch instructions point at known project IPs rather than a community-operated DNS seed network."
  ),
  p(
    "Bloodstone does not dispute these findings. The project's own Decentralized Network White Paper labels the current stage Phase 1 — Centralized Bootstrap. The audit is correctly identifying the bootstrap and application layer."
  ),

  h2("1.2 The category error"),
  p(
    "The audit treats \"everything resolves to the same VPS endpoints\" as proof that the network itself is a single-host control plane. That conflates two architectural layers that Bloodstone deliberately separates:"
  ),
  table(
    ["Layer", "Function", "Depends on project VPS?"],
    [
      ["Chain consensus", "bloodstoned P2P validation, block propagation, UTXO rules", "No — any full node enforces this"],
      ["Mining execution", "Stratum work, share submission, block finding", "Partially — pool mode uses VPS; solo and LAN modes do not"],
      ["Application / UX", "Portal, explorer, faucet, mesh catalog API", "Yes — today"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Bloodstone's security model is proof-of-work on an independently runnable daemon (bloodstoned), not \"whatever the portal says.\" A full node that rejects an invalid block does so from local chain state. The VPS cannot mint valid blocks, rewrite confirmed history, or override node validation logic."
  ),
  p(
    "The correct framing: a centralized bootstrap and coordination plane exists; a separate, independently operable chain-validation and LAN-mining plane also exists. Reviewers who inspect only the portal stack will miss the second layer unless they test node-operated paths."
  ),

  h1("2. Direct Answer"),
  h2("2.1 The audit question"),
  p(
    "Is there any independently operated infrastructure in this network that is not ultimately dependent on the hosted VPS stack (explorer, wallet, mining coordination, faucet, or seed nodes)?"
  ),
  p("Yes. The following infrastructure classes operate without the portal, explorer, faucet, or mesh coordinator:"),

  h3("A. Full Bloodstone nodes (bloodstoned)"),
  p(
    "Anyone may run a full node on Linux, Windows, or Android (full mode). The daemon stores and validates the chain locally, participates in peer-to-peer propagation on port 17333, serves JSON-RPC to wallets and miners on the LAN, and can act as a sync peer for other installations. Each new full node is potential bootstrap infrastructure — not merely a consumer of project seed IPs."
  ),
  p(
    "A wallet or miner pointed at http://<lan-ip>:18340/ does not require the portal to validate balances or serve solo mining work."
  ),

  h3("B. Pruned and mesh Android nodes"),
  p("Phones run bloodstoned locally in pruned (~550 MiB) or mesh federation mode:"),
  bullet("bullets", "LAN RPC and stratum for household miners (Neoscrypt, Yespower, ROD Neoscrypt)"),
  bullet("bullets", "On-device wallet generation — private keys are never transmitted to the VPS"),
  bullet(
    "bullets",
    "mDNS discovery (_bloodstone-rpc._tcp) locates LAN nodes without calling the coordinator"
  ),
  bullet(
    "bullets",
    "Bundled offline UI (Android APK v1.3.8+) — the miner application opens without loading the live portal"
  ),
  p("A household can mine to a phone on Wi-Fi with no browser dashboard session open."),

  h3("C. LAN-only mining paths"),
  bullet(
    "bullets",
    "Solo mining from local node RPC — full block difficulty, payout to the miner's address, no pool accounting layer"
  ),
  bullet(
    "bullets",
    "LAN client mode — devices without a full chain download discover a household full node via mDNS (and optional registry) and mine to its stratum ports"
  ),
  bullet(
    "bullets",
    "LAN stratum relay — one phone with upstream connectivity relays pool traffic to LAN rigs without exposing pool credentials on the local wire"
  ),

  h3("D. Chain Mesh peer storage"),
  p(
    "Mesh storage is not \"files live only on the VPS.\" Chunks are content-addressed, stored on browsers (IndexedDB) and Android filesystems, served peer-to-peer on LAN port 18341, and used for block-file disaster recovery if VPS archives are lost. The coordinator provides catalog and publish pipeline services today; the bytes are replicated on miners' devices."
  ),

  h3("E. Fleet and native Android miners"),
  p(
    "Android devices with native stratum TCP connect directly to stratum endpoints. They are not funneled exclusively through the browser WebSocket bridge. Hashrate and block-finding work are contributed by independently running devices."
  ),

  h3("F. Household internet gateway (BSM4)"),
  p(
    "A device with real internet may register as a peer gateway and perform BSM4 IPv4 egress for LAN miners. Traffic routes to an elected household peer, with coordinator mesh-gateway as fallback — not as the only path. HTTP and HTTPS fetch on the gateway device uses the gateway's own connectivity."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("3. What Remains VPS-Dependent"),
  p(
    "Bloodstone states openly which services depend on project-hosted infrastructure today. Calling this a control plane for mining coordination and user experience is accurate. Calling it the consensus plane is not."
  ),
  table(
    ["Service", "Role", "VPS-dependent today?"],
    [
      ["Proportional pool accounting", "Share weights, payout batching, dashboard stats", "Yes"],
      ["Explorer indexing", "Convenience views of chain history", "Yes"],
      ["Faucet", "Test-coin distribution", "Yes — by design"],
      ["Chain Mesh manifest API", "Authoritative asset catalog", "Yes — chunks replicated on peers"],
      ["Default mesh-gateway egress", "BSM4 internet tunnel fallback", "Yes — peer gateways are the decentralizing path"],
      ["Download distribution", "Binaries and release artifacts", "Yes — default on-ramp"],
      ["LAN registry lookup", "Household node discovery supplement", "Yes — mDNS works without it"],
      ["bloodstoned consensus", "Block validation and P2P", "No"],
      ["LAN stratum on pruned nodes", "Local work generation", "No"],
      ["Mesh chunk LAN serve :18341", "Peer byte recovery", "No"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("4. Seed Nodes and Hardcoded Endpoints"),
  p(
    "Reviewers correctly note that relaunch and seed instructions use fixed endpoints. This is a bootstrap convenience, not a description of the only nodes that exist or will exist."
  ),
  p(
    "Early networks — including Bitcoin — relied on known seed IPs before DNS seeds and diverse peer discovery matured. Bloodstone is earlier in that curve. The engineering roadmap is explicit:"
  ),
  table(
    ["Phase", "Characteristics"],
    [
      ["Phase 1 — Centralized Bootstrap (today)", "VPS hosts stratum, dashboard, initial block archives; mesh peers begin pinning chunks"],
      ["Phase 2 — LAN-first mining", "mDNS fills households with discoverable local nodes; pool relay shares one upstream connection"],
      ["Phase 3 — Regional redundancy", "Mesh federation reconstructs block files; fleet nodes distribute stratum load; full nodes peer on :17333"],
      ["Phase 4 — Infrastructure optional", "New installs sync from peer full nodes and mesh holders; VPS becomes convenience, not liveness"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "Each full node and mesh peer a user operates is independently operated infrastructure. The seed list is the default on-ramp, not the network topology."
  ),
  p(
    "Operations are also not literally a single machine. Production architecture uses separate hosts — for example, primary dashboard and coordination at 64.188.22.190 and CPU stratum and release hosting at 192.119.82.145. Same operator family, but not one box for every service."
  ),

  h1("5. Verification Tests for External Auditors"),
  p(
    "If the claim were \"nothing works without the portal,\" the following tests would falsify it. Auditors may reproduce these procedures without privileged access to project internals."
  ),
  table(
    ["Test", "Procedure", "Expected result without portal"],
    [
      [
        "1. Android LAN node",
        "Install APK, enable full or pruned node mode, do not open portal",
        "LAN RPC and stratum available on Wi-Fi",
      ],
      [
        "2. Local full node RPC",
        "Run bloodstoned on Linux, sync from peer, use bloodstone-cli against local RPC",
        "Balance and chain queries succeed with portal offline",
      ],
      [
        "3. Solo LAN mining",
        "Point LAN miner at local stratum in solo mode",
        "Work sourced from local chain state, not remote dashboard",
      ],
      [
        "4. Mesh LAN chunk fetch",
        "Enable chain mesh on two LAN devices; fetch chunk from http://<lan-ip>:18341/",
        "Chunk retrieval succeeds with coordinator unreachable",
      ],
      [
        "5. Household internet gateway",
        "Register gateway on phone with mobile data; route second miner's BSM4 tunnel through it",
        "HTTP egress via peer gateway without coordinator mesh-gateway",
      ],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "These paths do not require the explorer, faucet, or mining dashboard. They require user-operated nodes."
  ),

  h1("6. VPS-Dependent vs. Node-Independent Matrix"),
  p("Summary reference for auditors, operators, and integrators:"),
  table(
    ["Capability", "Node-independent?", "Notes"],
    [
      ["Reject invalid blocks", "Yes", "Any synced bloodstoned instance"],
      ["Solo mine to local RPC", "Yes", "Full or pruned node with synced tip"],
      ["LAN mine without chain download", "Yes", "LAN client + mDNS household full node"],
      ["Store mesh chunks locally", "Yes", "Browser IndexedDB or Android filesystem"],
      ["Serve chunks to LAN peers", "Yes", "Port 18341 on registered mesh peer"],
      ["Generate wallet on device", "Yes", "Keys never sent to VPS"],
      ["Open miner APK UI offline", "Yes", "Bundled offline-mine.html since v1.3.8"],
      ["Share internet to LAN miners", "Yes", "BSM4 peer gateway election"],
      ["Pool proportional payouts", "No", "Requires pool coordination service"],
      ["Explorer search and labels", "No", "Indexer hosted on VPS"],
      ["Faucet distribution", "No", "Centralized by design"],
      ["Default mesh asset catalog", "No", "Coordinator manifest API"],
      ["Default BSM4 egress", "No", "mesh-gateway fallback; peer path available"],
      ["First-time binary download", "No", "Default via project downloads host"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("7. Conclusion"),
  p(
    "The external audit correctly identifies that onboarding, pool user experience, explorer, faucet, and mesh catalog services are centralized on project infrastructure today. Bloodstone agrees, documents this as Phase 1, and is engineering toward making that layer optional."
  ),
  p(
    "What the audit misses when it stops at the portal is the layer underneath: independently runnable nodes that validate the chain, serve LAN mining, replicate archival data, and peer on P2P — infrastructure that is not ultimately dependent on the VPS for consensus truth or for several production mining and recovery paths."
  ),
  p(
    "Bloodstone is not claiming a fully decentralized web stack today. It is claiming — and shipping — a progressive decentralization model: centralized bootstrap, decentralized validation and storage at the edges, with the explicit goal that liveness and history survive even if the convenience hosts go offline."
  ),
  p(
    "Reviewers seeking precision should evaluate both layers: the coordination plane they see in the browser, and the node plane they will find on household Wi-Fi, Android devices, and operator-run bloodstoned instances. The network is neither purely decentralized nor purely single-host. It is a hybrid in transition, and the transition path is documented, testable, and intentional."
  ),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({ text: "Document version: 1.0 · July 2026", italics: true, size: 20 }),
    ],
  }),
  p("Related documents:"),
  linkPara(
    "Bloodstone Decentralized Network White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Decentralized-Network-White-Paper.docx"
  ),
  linkPara(
    "Bloodstone Chain Mesh Storage White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  linkPara(
    "Bloodstone Mesh Virtual LAN White Paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Mesh-Virtual-LAN-White-Paper.docx"
  ),
  linkPara("Bloodstone downloads", "https://bloodstonewallet.mytunnel.org/downloads/"),
  linkPara("bloodstonewallet.mytunnel.org", "https://bloodstonewallet.mytunnel.org/"),
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
                  text: "Bloodstone Infrastructure Independence — White Paper",
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
  "/root/bloodstone-docs/Bloodstone-Infrastructure-Independence-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outDocx, buffer);
  console.log("Wrote", outDocx, buffer.length, "bytes");
});