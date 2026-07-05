#!/usr/bin/env node
/** Bloodstone white paper — BSM3 virtual LAN and BSM4 mesh internet tunnel. */
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
function p(text) {
  return new Paragraph({ spacing: { after: 160 }, children: [new TextRun(text)] });
}
function mono(text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text, font: "Courier New", size: 20 })],
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
    children: [new TextRun({ text: "Bloodstone Chain Mesh", size: 52, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [
      new TextRun({
        text: "White Paper — BSM3 Virtual LAN & BSM4 Mesh Internet Tunnel",
        size: 30,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [new TextRun({ text: "Version 1.2 · July 2026", size: 22, italics: true })],
  }),

  h1("Abstract"),
  p(
    "Bloodstone miners already replicate immutable 256 KiB chunks and attest file transfers with hash power. " +
      "BSM3 (Bloodstone Mesh Packet Protocol v1) adds a virtual LAN: small datagrams (≤ 1.4 KiB) exchanged over " +
      "coordinator channels, relayed by miners, and decoded in the browser like a household network link. " +
      "BSM4 (Bloodstone Mesh IP Tunnel v1) stacks raw IPv4 frames inside BSM3 packets so userspace tunnel endpoints " +
      "can ping, resolve DNS, and fetch HTTP over the mesh. A coordinator-hosted mesh-gateway node performs controlled " +
      "egress to the public internet and injects replies back into tunnel inboxes. Version 1.2 adds multi-round TLS " +
      "passthrough: the gateway relays raw TLS bytes on a persistent upstream TCP socket (ClientHello, then client " +
      "flight 2) without terminating TLS, enabling end-to-end handshake experiments toward true HTTPS over the mesh. " +
      "Mining attestation binds relay work to accepted shares without embedding payload bytes in stratum jobs."
  ),

  h1("1. Motivation"),
  p(
    "Phones and browsers cannot open raw sockets, yet operators still need LAN-style messaging, discovery, and " +
      "occasional internet reachability when centralized APIs are unavailable. Rather than inventing yet another " +
      "proprietary chat protocol, Bloodstone exposes internet-familiar framing (packets, IPv4, ICMP, TCP, UDP) " +
      "on top of the existing chain mesh coordinator and miner relay fabric."
  ),
  bullet(
    "bullets",
    "BSM3 — typed payloads (text, json, binary) in sequenced mesh packets with TTL and inbox delivery."
  ),
  bullet(
    "bullets",
    "BSM4 — payload_type=ipv4 carrying complete IPv4 datagrams for userspace tunnel endpoints."
  ),
  bullet(
    "bullets",
    "mesh-gateway — VPS egress role (recipient mesh-gateway) forwarding ICMP, DNS, HTTP, HTTPS proxy, and raw TLS passthrough."
  ),
  bullet(
    "bullets",
    "Mining attestation — relay credit from share job_id + nonce bound to packet_id via work_digest."
  ),

  h1("2. BSM3 Virtual LAN"),
  h2("2.1 Packet framing"),
  p(
    "Each BSM3 packet belongs to a 64-hex channel_id derived from sender, recipient, and label. Packets are monotonically " +
      "sequenced per channel, capped at 1400 bytes payload, and stored in the coordinator SQLite inbox until expiry. " +
      "Frame metadata includes payload_type, payload_sha256, sender, recipient, created_at, and relay_count."
  ),
  mono('work_digest = SHA256("BSM3" | channel_id | packet_id | job_id | nonce_hex)'),
  h2("2.2 Channels and delivery"),
  table(
    ["Endpoint", "Purpose"],
    [
      ["POST /api/chain-mesh/packet/channel", "Open or refresh a virtual LAN channel"],
      ["POST /api/chain-mesh/packet/send", "Enqueue a packet (text, json, ipv4, …)"],
      ["GET /api/chain-mesh/packet/inbox/<recipient>", "Poll sequenced inbox"],
      ["GET /api/chain-mesh/packet/stream/<recipient>", "Server-Sent Events live stream"],
      ["POST /api/chain-mesh/packet/attest", "Miner relay attestation after share accept"],
      ["GET /api/chain-mesh/packet/peers-for/<recipient>", "LAN peer hints (:18341)"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h2("2.3 Browser and Android endpoints"),
  p(
    "The Network Data Portal exposes a Virtual LAN panel: open channel, send text packets, listen via SSE plus " +
      "12-second hybrid poll against coordinator and LAN chunk servers on port 18341. Android ChainMeshHttpServer " +
      "mirrors /packet routes for household P2P when the VPS is unreachable."
  ),
  h2("2.4 On-chain anchors"),
  p(
    "Optional BSM3 channel open anchors (44-byte OP_RETURN with BSM3 magic + channel prefix) are indexed by " +
      "packet_index.py for auditability. Anchors attest channel existence, not per-packet payloads."
  ),

  h1("3. BSM4 Mesh IP Tunnel"),
  h2("3.1 Encapsulation"),
  p(
    "BSM4 defines payload_type=ipv4 on BSM3 channels. The payload_b64 field holds a complete IPv4 datagram " +
      "(header + transport + data) up to 1400 bytes. Browsers construct ICMP, UDP, or TCP segments in JavaScript; " +
      "the coordinator validates IPv4 version, length, and optional header checksum before accept."
  ),
  mono("tunnel_id = SHA256(channel_id | virtual_ip)"),
  mono('work_digest = SHA256("BSM4" | channel_id | packet_id | job_id | nonce_hex)'),
  h2("3.2 Virtual subnet"),
  p(
    "Default virtual subnet 10.73.0.0/16 assigns each tunnel endpoint a private address (e.g. 10.73.0.42). " +
      "The mesh-gateway advertises virtual IP 10.73.0.1. These addresses exist only inside BSM4 frames; " +
      "the gateway performs NAT-style reply rewriting when talking to the public internet."
  ),
  h2("3.3 Tunnel API"),
  table(
    ["Route", "Role"],
    [
      ["GET /api/chain-mesh/tunnel/ip/protocol", "BSM4 + gateway metadata"],
      ["POST /api/chain-mesh/tunnel/ip/channel", "Open tunnel channel (adds tunnel_id)"],
      ["POST /api/chain-mesh/tunnel/ip/send", "Send raw IPv4 datagram"],
      ["GET /api/chain-mesh/tunnel/ip/inbox/<recipient>", "Inbox with decoded ipv4 summaries"],
      ["GET /api/chain-mesh/tunnel/ip/gateway/status", "Egress queue and capability flags"],
      ["POST /api/chain-mesh/tunnel/ip/gateway/egress", "Manual egress batch (admin/debug)"],
      ["GET /api/chain-mesh/tunnel/ip/tls/client-hello", "OpenSSL-backed ClientHello (+ handshake_id for flight 2)"],
      ["POST /api/chain-mesh/tunnel/ip/tls/client-flight2", "Build client CCS + Finished for TLS 1.3 flight 2"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("4. mesh-gateway Internet Egress"),
  h2("4.1 Architecture"),
  p(
    "Users open a BSM4 channel with recipient mesh-gateway. Outbound IPv4 frames addressed to mesh-gateway are " +
      "picked up by a background worker (default every 4 seconds) or an admin POST to /gateway/egress. " +
      "Supported egress actions in v1.2:"
  ),
  bullet("numbers", "icmp_echo — system ping to destination; inject ICMP echo reply."),
  bullet("numbers", "udp_dns — relay UDP port 53 to upstream 8.8.8.8; inject DNS answer."),
  bullet("numbers", "tcp_http — parse HTTP GET/HEAD in TCP port 80; fetch via HTTP client; inject TCP response segment."),
  bullet("numbers", "tcp_https — same HTTP GET framing on TCP port 443; gateway terminates TLS upstream and injects decoded HTTP response."),
  bullet("numbers", "tcp_tls_passthrough — relay raw TLS records to upstream TCP; inject raw server flight (flight 1)."),
  bullet("numbers", "tcp_tls_continue — same upstream socket; relay subsequent client TLS flights (flight 2+)."),
  p(
    "Processed packet_ids are recorded in chain_mesh_ip_gateway_processed to prevent duplicate handling. " +
      "TLS passthrough sessions are tracked in chain_mesh_ip_gateway_tcp_sessions (gateway_seq, relay_rounds, SNI). " +
      "TCP connect uses the IPv4 destination from the mesh frame; SNI stays inside TLS only. Reply packets are " +
      "injected on the same channel with sender mesh-gateway and recipient equal to the original mesh client."
  ),
  h2("4.2 TLS passthrough and multi-round handshake"),
  p(
    "For ports listed in BSM4_GATEWAY_HTTPS_PORTS (default 443, 8443, 18443), the gateway opens an upstream TCP " +
      "connection to dst_ip:dst_port and relays TLS payload bytes without parsing application data. Flight 1 " +
      "(ClientHello) yields ServerHello + certificate flight; flight 2 (ChangeCipherSpec + encrypted Finished) " +
      "completes TLS 1.3 when the browser supplies valid client bytes. The coordinator can build flight 2 server-side " +
      "via handshake_id session storage (X25519 key captured at ClientHello generation)."
  ),
  mono("Session key = channel_id | src_ip | src_port | dst_ip | dst_port"),
  mono("Flight 1 action: tcp_tls_passthrough · Flight 2+ action: tcp_tls_continue"),
  h2("4.3 Security and limits"),
  p(
    "Egress is intentionally centralized on the coordinator VPS in v1.2. Operators should treat mesh-gateway as a " +
      "policy-controlled NAT, not a censorship-free anonymity layer. HTTP/HTTPS proxy responses are truncated to fit " +
      "the 1400-byte IPv4 MTU. tcp_https terminates TLS at the gateway; tcp_tls_passthrough does not — upstream sees " +
      "the client's ClientHello SNI and negotiated cipher. Handshake sessions expire after 300 seconds."
  ),
  h2("4.4 Environment variables"),
  table(
    ["Variable", "Default", "Meaning"],
    [
      ["BSM4_GATEWAY_ENABLED", "1", "Enable background egress worker"],
      ["BSM4_GATEWAY_RECIPIENT", "mesh-gateway", "Inbox recipient for egress queue"],
      ["BSM4_GATEWAY_VIRTUAL_IP", "10.73.0.1", "Advertised gateway virtual address"],
      ["BSM4_GATEWAY_DNS", "8.8.8.8", "DNS upstream resolver"],
      ["BSM4_GATEWAY_INTERVAL_SEC", "4", "Background poll interval"],
      ["BSM4_GATEWAY_HTTPS_PORTS", "443,8443,18443", "TCP ports for HTTPS proxy and TLS passthrough"],
      ["BSM4_GATEWAY_TLS_RELAY_TIMEOUT", "8", "Upstream socket timeout (seconds)"],
      ["BSM4_GATEWAY_TLS_SESSION_TTL", "180", "Passthrough TCP session TTL (seconds)"],
    ]
  ),
  new Paragraph({ spacing: { after: 200 }, children: [] }),

  h1("5. Mining attestation and relay"),
  p(
    "After the pool accepts a share, web-miner.js calls relayMeshPacketOnShare() which posts attestations linking " +
      "packet_id to job_id and nonce_hex. Relay queue endpoints let Android miners prefetch packets for recipients " +
      "they are helping. Attestation does not prove payload correctness — it proves a miner expended hash work " +
      "while relaying a known packet hash within the channel TTL."
  ),

  h1("6. Browser workflow (quick start)"),
  bullet("numbers", "Open Network Data Portal → Virtual LAN (BSM3) or Internet tunnel (BSM4)."),
  bullet("numbers", "Enter STONE address or device id; open channel to peer or mesh-gateway."),
  bullet("numbers", "BSM3: type a message and Send packet; Listen for SSE/LAN replies."),
  bullet("numbers", "BSM4: set virtual IP 10.73.0.42; Ping over mesh (ICMP to 8.8.8.8) or HTTP GET over mesh."),
  bullet("numbers", "TLS lab: host bloodstone-tls-lab, dst 127.0.0.1, port 18443 → Full TLS handshake (lab)."),
  bullet("numbers", "Production TLS: set Host/SNI to real domain, dst to public IPv4; same handshake button (OpenSSL template)."),
  bullet("numbers", "Mine while sending — attestations accumulate on accepted shares."),

  h1("7. Roadmap"),
  bullet("bullets", "TCP stream fragmentation and reassembly for payloads larger than 1400 bytes."),
  bullet("bullets", "BSM4 on-chain anchor indexing (parallel to BSM3 packet_index)."),
  bullet("bullets", "Decentralized gateway election and multi-hop routing without a single coordinator."),
  bullet("bullets", "Browser-native TLS 1.3 flight 2 (Web Crypto) without coordinator flight-2 helper."),
  bullet("bullets", "Kernel TUN integration on Android full nodes for true VPN mode."),

  h1("8. References"),
  linkPara(
    "Network Data Portal",
    "https://bloodstonewallet.mytunnel.org/mining/network-data"
  ),
  linkPara(
    "Mesh File Upload white paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx"
  ),
  linkPara(
    "Chain Mesh Storage white paper",
    "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx"
  ),
  mono("Protocol magics: BSM3 (virtual LAN packets), BSM4 (IPv4 tunnel), BSM2 (transfers), BSM1 (asset anchors)"),

  new Paragraph({ children: [new PageBreak()] }),
  h1("Appendix A — Example ICMP ping over mesh"),
  mono("POST /api/chain-mesh/tunnel/ip/channel"),
  mono('{ "sender": "device-abc", "recipient": "mesh-gateway", "virtual_ip": "10.73.0.42" }'),
  mono("POST /api/chain-mesh/tunnel/ip/send"),
  mono(
    '{ "channel_id": "<64-hex>", "sender": "device-abc", "recipient": "mesh-gateway", "ip_packet_b64": "<ICMP echo to 8.8.8.8>" }'
  ),
  mono("GET /api/chain-mesh/tunnel/ip/inbox/device-abc?channel_id=<64-hex>"),
  p("Expect ipv4 summary: 8.8.8.8 → 10.73.0.42 icmp type 0 (echo reply) after gateway egress."),

  h1("Appendix B — Example HTTP GET over mesh"),
  mono("Browser builds TCP segment: port 80, PSH+ACK, payload GET / HTTP/1.1\\r\\nHost: example.com\\r\\n…"),
  mono("Gateway action tcp_http fetches http://example.com/ and injects HTTP/1.1 200 response in TCP reply."),

  h1("Appendix C — TLS passthrough lab workflow"),
  p(
    "The coordinator runs openssl s_server on 127.0.0.1:18443 (systemd: bloodstone-tls-lab.service) with a self-signed " +
      "certificate for CN=bloodstone-tls-lab. The mesh-gateway relays TLS to that upstream while the browser uses " +
      "virtual subnet addressing."
  ),
  bullet("numbers", "Start lab server: systemctl start bloodstone-tls-lab"),
  bullet("numbers", "Open BSM4 channel to mesh-gateway; virtual IP 10.73.0.42."),
  bullet("numbers", "GET /api/chain-mesh/tunnel/ip/tls/client-hello?host=bloodstone-tls-lab&connect_host=127.0.0.1&port=18443"),
  bullet("numbers", "Send returned ClientHello inside TCP/IPv4 to mesh-gateway; trigger /gateway/egress."),
  bullet("numbers", "Poll inbox — expect ~1355 B ServerHello + cert flight (tcp_tls_passthrough)."),
  bullet("numbers", "POST /api/chain-mesh/tunnel/ip/tls/client-flight2 with handshake_id + server_flight_b64."),
  bullet("numbers", "Send flight 2 TCP segment; egress returns tcp_tls_continue with server application data."),
  p("Verified E2E: flight 1 = 1355 B down; flight 2 = 80 B up, 24 B server app data down."),

  h1("Appendix D — Production TLS over mesh"),
  p(
    "For public hosts, client-hello uses openssl s_client against connect_host:port with -servername set to the " +
      "intended SNI. The coordinator patches client_random and X25519 key_share while preserving OpenSSL extension " +
      "layout. connect_host may be a hostname (resolved to IPv4) or literal address; TCP connect uses dst_ip from " +
      "the mesh IPv4 frame. Flight 2 requires TLS 1.3 upstream; TLS 1.2-only servers need a different client stack."
  ),
  mono("Example: host=bloodstonewallet.mytunnel.org connect_host=64.188.22.190 port=443"),
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
                  text: "Bloodstone Chain Mesh — BSM3 Virtual LAN & BSM4 Internet Tunnel",
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
  "/root/bloodstone-docs/Bloodstone-Mesh-Virtual-LAN-White-Paper.docx";
const outDownloads =
  "/var/www/bloodstone/downloads/Bloodstone-Mesh-Virtual-LAN-White-Paper.docx";

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outDocx, buffer);
  fs.copyFileSync(outDocx, outDownloads);
  console.log("Wrote", outDocx, buffer.length, "bytes");
  console.log("Copied to", outDownloads);
});