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
    children: [new TextRun({ text: "Bloodstone Decentralized Network", size: 52, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [new TextRun({ text: "White Paper — Architecture, Node Roles, and Network Longevity", size: 32 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [new TextRun({ text: "July 2026 · Android Node v1.3.9", size: 24, italics: true })],
  }),

  h1("Executive Summary"),
  p(
    "Bloodstone is building a multi-algorithm proof-of-work network designed to survive beyond any single data center. " +
      "This white paper documents the engineering work completed through July 2026: turning phones, browsers, home PCs, and ASIC hardware into cooperating network participants — each with a distinct role in securing the chain, distributing hashrate, preserving block data, and reducing dependence on a central VPS."
  ),
  p(
    "The central thesis is simple: every new node type adds a layer of resilience. A full node validates truth. A pruned phone node extends validation to the LAN. A mesh federation node archives block-file chunks so chain data can be rebuilt if infrastructure fails. A fleet offload node routes stratum traffic natively. Together, these roles compound over the life of the coin — increasing censorship resistance, geographic distribution, and recovery options as adoption grows."
  ),

  h1("1. Network Overview"),
  h2("1.1 What Bloodstone Is"),
  p(
    "Bloodstone (STONE) is a proof-of-work cryptocurrency in the SpaceXpanse ecosystem. Mining supports multiple algorithms used across the Bloodstone pool and related assets:"
  ),
  bullet("bullets", "Neoscrypt — primary CPU/GPU-friendly algorithm for STONE pool mining"),
  bullet("bullets", "Yespower — memory-hard variant for diversified hashrate"),
  bullet("bullets", "ROD Neoscrypt — auxiliary chain tied to the SpaceXpanse/ROD ecosystem"),
  bullet("bullets", "SHA256d — ASIC-capable algorithm with Stratum v2 (SV2) and auxpow merge-mining support"),
  p(
    "Users interact through Qt wallets, Electron GUIs, Windows CPU miners, Android node+miner apps, and web-based mining dashboards served from the Bloodstone portal."
  ),

  h2("1.2 Infrastructure Today"),
  p("The network currently operates across two complementary tiers:"),
  table(
    ["Host", "Role", "Services"],
    [
      [
        "Primary VPS (64.188.22.190)",
        "Dashboard & SHA256",
        "Mining portal, miner-web UI, SHA256 stratum, pool coordination, download distribution",
      ],
      [
        "Pool Worker (192.119.82.145)",
        "CPU Stratum",
        "Neoscrypt, Yespower, and ROD stratum; APK and release file hosting",
      ],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  p(
    "The long-term goal is not to eliminate these servers immediately, but to make them optional: enough pruned nodes, full nodes, mesh peers, and LAN relays should exist that the chain, pool traffic, and block archives remain functional even if a central host goes offline."
  ),

  h1("2. Node Types and Lifetime Value"),
  p(
    "Each participant type below contributes differently over the decades-long life of a coin. The table summarizes roles; subsequent sections explain how they interact."
  ),
  table(
    ["Node Type", "What It Runs", "Lifetime Contribution"],
    [
      [
        "Full Bloodstone Node",
        "bloodstoned (Qt / headless)",
        "Authoritative chain validation, P2P peering on :17333, RPC for wallets, enables retiring central sync once quorum exists",
      ],
      [
        "Pruned Android Node",
        "bloodstoned pruned (~550 MiB)",
        "LAN RPC + stratum for household miners; validates recent chain; lowest storage bar for phones",
      ],
      [
        "Mesh Federation Node",
        "Pruned tip + chunk federation",
        "Distributes block-file backups across devices; disaster recovery if VPS block data is lost",
      ],
      [
        "Decentralized VPS Pool Node",
        "Android native stratum TCP",
        "Device fleet offload — direct pool TCP bypassing WebSocket bridge; spreads connection load",
      ],
      [
        "Chain Mesh Peer",
        "Browser IndexedDB / Android filesystem",
        "Pins and replicates VPS block-fill chunks; peer-to-peer chunk fetch on LAN",
      ],
      [
        "Windows CPU Miner",
        "cpuminer-opt presets",
        "Desktop hashrate for Neoscrypt/Yespower/ROD without running a full node",
      ],
      [
        "ASIC / SV2 Node",
        "SHA256d hardware + SV2 template provider",
        "High-throughput hashrate; auxpow merge-mining for auxiliary chains",
      ],
    ]
  ),
  new Paragraph({ spacing: { after: 240 }, children: [] }),

  h2("2.1 Full Bloodstone Node"),
  p(
    "A full node stores the complete blockchain, validates every block and transaction, and participates in peer-to-peer propagation. On Android, full mode runs bloodstoned without a wallet, exposes LAN RPC and stratum, and peers outward so other devices can sync."
  ),
  p("Over the life of the coin, full nodes provide:"),
  bullet("numbers", "Consensus enforcement — reject invalid blocks even if a pool or API lies about chain state"),
  bullet("numbers", "Wallet independence — users need not trust a remote RPC for balance or transaction verification"),
  bullet("numbers", "Infrastructure sunset path — when enough full nodes exist globally, the central VPS ceases to be a single point of failure for sync"),
  bullet("numbers", "Seed diversity — each new full node is a potential peer for fresh installations"),

  h2("2.2 Pruned Android Node (Default)"),
  p(
    "The default Android configuration runs a pruned bloodstoned instance (~550 MiB prune target). It maintains the chain tip, serves JSON-RPC over HTTP on the LAN, and hosts local stratum ports for Neoscrypt (:3437), Yespower (:3438), and ROD Neoscrypt (:3440)."
  ),
  p("Lifetime value:"),
  bullet("bullets", "Every household phone running pruned mode is a micro-validation endpoint for LAN miners"),
  bullet("bullets", "Reduces round-trip latency — mining work is sourced from local chain state, not a distant VPS"),
  bullet("bullets", "Battery-aware sync (WorkManager) keeps the tip current without draining battery — dormant checks every 15 minutes, wakes for sync when 20+ blocks behind"),
  bullet("bullets", "Low storage requirement makes mass adoption feasible on mid-range Android hardware"),

  h2("2.3 Mesh Federation Node"),
  p(
    "Mesh mode combines a pruned tip node with federated block-file chunk storage. The Chain Mesh subsystem (browser IndexedDB or Android native filesystem) pins VPS block-fill backups, uploads replicas, and fetches missing chunks from LAN peers."
  ),
  p("Lifetime value:"),
  bullet("bullets", "Archival redundancy — block data is sharded across phones and browsers (up to 128 chunks per mesh-capable Android device)"),
  bullet("bullets", "Disaster recovery — if the VPS loses block files, the mesh can rebuild chain data from collective device storage"),
  bullet("bullets", "Graceful degradation — devices with insufficient storage for full mode automatically fall back to mesh federation"),
  bullet("bullets", "Geographic distribution — chunk holders naturally spread across ISPs and regions"),

  h2("2.4 Decentralized VPS Pool Node (Device Fleet)"),
  p(
    "Android devices with native stratum TCP capability act as decentralized VPS pool nodes (fleet role: decentralized-vps-node). They connect directly to upstream pool stratum, bypassing the WebSocket bridge used by browsers."
  ),
  p("Lifetime value:"),
  bullet("bullets", "Connection scalability — pool load spreads across device fleet instead of concentrating on one bridge"),
  bullet("bullets", "Resilience — loss of the web bridge does not strand native-TCP Android miners"),
  bullet("bullets", "Identity tracking — each device contributes a stable hashed device ID for fleet statistics and pool coordination"),
  bullet("bullets", "Foreground service + keep-awake integration sustains mining sessions on Android"),

  h2("2.5 Chain Mesh Peer (Browser and Android)"),
  p(
    "Even without running bloodstoned, a browser tab or Android app can participate in chain mesh: storing block chunks, serving them to peers on the LAN, and syncing backup jobs from the VPS."
  ),
  p("Lifetime value:"),
  bullet("bullets", "Zero-install archival participation via web dashboard"),
  bullet("bullets", "LAN peer chunk server on port 18341 for fast local recovery"),
  bullet("bullets", "Complements pruned nodes — pruned validates the tip; mesh preserves historical block files"),

  h2("2.6 Windows CPU Miner"),
  p(
    "The Windows CPU miner packages cpuminer-opt with pool presets for Neoscrypt, Yespower, and ROD. It targets users who want hashrate without operating a node."
  ),
  p("Lifetime value: broadens the miner base, tests pool compatibility, and provides desktop-grade hashrate alongside mobile decentralization."),

  h2("2.7 ASIC and SV2 Infrastructure"),
  p(
    "SHA256d mining uses Stratum v2 with a template provider (bloodstone-sv2-tp) supporting auxpow merge-mining. Gamma and other ASIC hardware connect through this layer. Engineering work includes auxpow validation alignment, share difficulty tuning, and template freshness for multi-chain merge mining."
  ),
  p("Lifetime value: ASIC hashrate secures the high-throughput lane of the network; SV2 reduces bandwidth and improves job efficiency for industrial miners over the coin's lifespan."),

  new Paragraph({ children: [new PageBreak()] }),

  h1("3. Android Node + Miner Evolution"),
  p(
    "The Capacitor-based Android app (Bloodstone Fleet Miner) is the primary vehicle for phone-based decentralization. Key releases:"
  ),
  table(
    ["Version", "Milestone"],
    [
      ["1.1.x – 1.2.x", "Initial Android miner, native stratum TCP, fleet node role"],
      ["1.3.3", "Yespower pool share submission fix"],
      ["1.3.4", "LAN mining info panel — displays device LAN IP and stratum ports"],
      ["1.3.5", "Local node sync engine fix (block-behind threshold); improved NodeSyncEngine caught-up detection"],
      ["1.3.6", "Resilient WebView lifecycle; deferred battery exemption dialog; mining resume after reconnect"],
      ["1.3.7", "Charge-only local mining — power guard gates mining to external power"],
      ["1.3.8", "Bundled offline UI; mDNS LAN browse/register; LAN pool stratum relay; mesh + pruned + full node modes"],
      ["1.3.9", "Reliable plug-in detection via BatteryManager API; Capacitor-ready power polling; visibility refresh"],
    ]
  ),
  new Paragraph({ spacing: { after: 240 }, children: [] }),

  h1("4. Technical Architecture (2026)"),
  h2("4.1 Bundled UI — No VPS Required to Open the App"),
  p(
    "Version 1.3.8 removed the hard dependency on loading the mining UI from the live portal. The Capacitor app bundles offline-mine.html locally (capacitor.config.json startPath). Users can open the miner on a LAN without internet; remote portal URL is only injected for development builds (BLOODSTONE_CAPACITOR_REMOTE_UI=1)."
  ),

  h2("4.2 mDNS LAN Discovery"),
  p(
    "LanDiscovery registers and browses _bloodstone-rpc._tcp services via Android NSD. TXT attributes advertise node mode, Neoscrypt stratum port, and Yespower stratum port. Peers appear in the UI before any VPS /api/local-node/nearby call — enabling pure-LAN coordination."
  ),

  h2("4.3 LAN Stratum and Pool Relay"),
  p("LocalStratumTcpServer serves work from the local node's RPC in solo mode. In pool mode, StratumPoolRelay transparently forwards miner traffic to the upstream VPS pool — so LAN devices can pool-mine through a phone without exposing pool credentials on the local wire."),
  p("Android mining policy (1.3.7+): mining is local-node-only while on external power. The app will not fall back to VPS stratum when local node is required — this protects battery and reinforces decentralization."),

  h2("4.4 Node Sync Engine"),
  p(
    "NodeSyncEngine wakes dormant nodes when 20+ blocks behind network height, runs a bounded sync (max 10 minutes), and returns to dormant state. This keeps pruned tips current without running bloodstoned continuously on battery."
  ),

  h2("4.5 Power Guard"),
  p(
    "DevicePoolPlugin.getPowerStatus() reports charging state. The web power-guard module gates the Start button and stops active mining on unplug. Version 1.3.9 uses BatteryManager.isCharging() as primary API when sticky battery broadcasts are unavailable on modern Android."
  ),

  h2("4.6 Web Mining Dashboard"),
  p(
    "The miner-web stack serves browser mining with WebSocket stratum bridge, chain mesh peer sync, fleet statistics, ASIC share display, and Android app parity through shared static/js modules synced into the APK at build time."
  ),

  new Paragraph({ children: [new PageBreak()] }),

  h1("5. How Nodes Compound Over the Life of the Coin"),
  p("The following phases describe how adoption of each node type changes network properties over time:"),

  h3("Phase 1 — Centralized Bootstrap (Today)"),
  bullet("bullets", "VPS hosts stratum, dashboard, and initial block archives"),
  bullet("bullets", "Android pruned nodes and CPU miners connect upstream"),
  bullet("bullets", "Mesh peers begin pinning block-fill chunks"),

  h3("Phase 2 — LAN-First Mining"),
  bullet("bullets", "mDNS fills households with discoverable local nodes"),
  bullet("bullets", "Pool relay lets LAN miners share one phone's upstream connection"),
  bullet("bullets", "Charge-only policy keeps home mining sustainable on phones"),

  h3("Phase 3 — Regional Redundancy"),
  bullet("bullets", "Mesh federation holds enough chunks to reconstruct block files regionally"),
  bullet("bullets", "Fleet nodes distribute stratum load across thousands of Android devices"),
  bullet("bullets", "Full nodes on tablets and PCs begin peering on :17333"),

  h3("Phase 4 — Infrastructure Optional"),
  bullet("bullets", "New installs sync from peer full nodes and mesh chunk holders"),
  bullet("bullets", "Pool jobs can be sourced from local RPC on pruned/full nodes"),
  bullet("bullets", "Central VPS becomes a convenience endpoint, not a liveness requirement"),

  p(
    "The marginal value of each additional node increases as diversity grows: a pruned phone in a new country adds validation geography; a mesh peer adds archival entropy; a full node adds sync capacity; an ASIC adds hashrate security."
  ),

  h1("6. Participation Guide"),
  h2("6.1 Downloads"),
  linkPara(
    "Android Node + Miner v1.3.9 (latest)",
    "https://bloodstonewallet.mytunnel.org/downloads/bloodstone-miner-android-1.3.9.apk"
  ),
  linkPara("All Bloodstone downloads", "https://bloodstonewallet.mytunnel.org/downloads/"),
  linkPara("Mining portal", "https://bloodstonewallet.mytunnel.org/"),

  h2("6.2 Network Data — Upload, Send, Receive"),
  p(
    "Bloodstone Chain Mesh Storage extends block archival into a general-purpose data network. Files are content-addressed, " +
      "sharded into 256 KiB chunks, replicated across miners and browsers, and optionally anchored on-chain with BSM1."
  ),
  linkPara(
    "Network Data Portal (live UI)",
    "https://bloodstonewallet.mytunnel.org/mining/network-data"
  ),
  table(
    ["Flow", "What happens", "Primary API"],
    [
      ["Upload", "Chunk file → register manifest → optional BSM1 anchor", "POST /api/chain-mesh/upload, /publish-asset"],
      ["Send", "Announce held chunks, LAN serve :18341, queue offline shares", "POST /api/chain-mesh/peer, /pending-shares"],
      ["Receive", "Fetch manifest → download chunks → verify hashes → rebuild file", "GET /api/chain-mesh/asset/<key>"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),
  linkPara(
    "Chain Mesh Storage white paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),

  h2("6.3 Recommended Setup"),
  bullet("numbers", "Install Android v1.3.9, grant battery exemption when prompted, plug in to charge"),
  bullet("numbers", "Choose node mode: Pruned (default), Mesh (archival), or Full (if storage allows)"),
  bullet("numbers", "Note LAN IP and stratum ports from the device network panel"),
  bullet("numbers", "Point LAN miners (including the same phone) at local stratum for Neoscrypt or Yespower"),
  bullet("numbers", "Enable chain mesh to contribute block chunk storage in the background"),

  h2("6.4 For Operators"),
  bullet("bullets", "Run a full bloodstoned node on Linux or Windows for authoritative validation"),
  bullet("bullets", "Publish stratum only after local node is synced"),
  bullet("bullets", "Monitor fleet stats at /api/pool/device-fleet on the portal"),

  h1("7. Conclusion"),
  p(
    "Bloodstone's decentralization program treats every device class as a permanent network asset. Pruned phone nodes democratize validation. Mesh federation preserves history. Fleet nodes distribute pool load. Full nodes anchor consensus. ASICs secure high-throughput proof-of-work. None of these roles alone replaces the others — together they form a network that becomes harder to stop, harder to censor, and easier to recover with every new participant."
  ),
  p(
    "Version 1.3.9 of the Android node+miner is the current reference implementation of this vision: bundled UI, LAN discovery, pool relay, charge-aware mining, and reliable power detection. The work continues toward a network where the coin's life does not depend on any single server still being online tomorrow."
  ),

  new Paragraph({
    spacing: { before: 400 },
    children: [
      new TextRun({ text: "Document version: 1.0 · July 2026", italics: true, size: 20 }),
    ],
  }),
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
              children: [new TextRun({ text: "Bloodstone Decentralized Network — White Paper", size: 18, color: "666666" })],
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

const outDocx = "/root/bloodstone-docs/Bloodstone-Decentralized-Network-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outDocx, buffer);
  console.log("Wrote", outDocx, buffer.length, "bytes");
});