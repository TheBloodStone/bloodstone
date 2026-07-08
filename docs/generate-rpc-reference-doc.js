#!/usr/bin/env node
/** Bloodstone Core JSON-RPC Reference — DOCX generator. */
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
function mono(text) {
  return new Paragraph({
    spacing: { after: 100 },
    children: [new TextRun({ text, font: "Courier New", size: 20 })],
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
    children: [new TextRun({ text: "Bloodstone Core JSON-RPC Reference", bold: true, size: 30 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({ text: "Document version 1.0 · July 2026", size: 22, color: "444444" })],
  }),

  h1("Executive summary"),
  p(
    "Bloodstone Core (bloodstoned) exposes Bitcoin Core–compatible JSON-RPC 1.0 over HTTP, plus SpaceXpanse heritage extensions for on-chain names, multi-algorithm mining, and game-aware ZMQ notifications."
  ),
  p(
    "This document covers connection details, Bloodstone-specific methods, ZMQ topics, and integration alternatives. Inherited Bitcoin Core commands are listed by category; run bloodstone-cli help <command> for full syntax."
  ),
  p("Bloodstone is not an EVM chain. ethers.js, web3.js, and MetaMask do not work against STONE RPC.", { bold: true }),

  h1("1. Quick start"),
  h2("Network parameters (mainnet)"),
  table(
    ["Parameter", "Value"],
    [
      ["P2P port", "17333"],
      ["RPC port (Linux)", "18332"],
      ["RPC port (Android LAN)", "18340"],
      ["Currency", "STONE (8 decimals)"],
      ["Addresses", "S… legacy, stone1… bech32"],
      ["PoW algorithms", "neoscrypt, yespower, sha256d (merge ID 1899)"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 200 } }),

  h2("bloodstone-cli examples"),
  mono("bloodstone-cli getblockchaininfo"),
  mono('bloodstone-cli getblockstats $(bloodstone-cli getblockcount) \'["subsidy"]\''),
  mono('bloodstone-cli name_show "d/myname"'),
  mono('bloodstone-cli creatework "SAddress" "neoscrypt"'),
  mono('bloodstone-cli trackedgames add "mygame"'),

  h2("HTTP JSON-RPC (curl)"),
  p("JSON-RPC 1.0 with HTTP basic auth (rpcuser / rpcpassword):"),
  mono(
    'curl --user USER:PASS --data-binary \'{"jsonrpc":"1.0","id":"curltest","method":"getblockchaininfo","params":[]}\' -H \'content-type: text/plain;\' http://127.0.0.1:18332/'
  ),
  p("Wallet context uses /wallet/<name> in the URL path (Bitcoin Core convention)."),

  h2("Security"),
  bullet(
    "bullets",
    "RPC on the public pool VPS is localhost-only — run your own exchange node or use ElectrumX."
  ),
  bullet("bullets", "Never expose RPC credentials to browsers or mobile clients."),

  new PageBreak(),

  h1("2. Not Ethereum — alternatives"),
  table(
    ["Ethereum stack", "Bloodstone"],
    [
      ["eth_* methods", "getblockchaininfo, sendrawtransaction, listunspent"],
      ["0x accounts", "UTXO model — S… / stone1…"],
      ["MetaMask", "Not applicable"],
      ["ethers.js / web3.js", "Bitcoin-style RPC or Electrum protocol"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 200 } }),
  table(
    ["Integration goal", "Recommended approach"],
    [
      ["CEX deposits/withdrawals", "Own node + getnewaddress / sendtoaddress / getrawtransaction"],
      ["Lightweight monitoring", "ElectrumX ssl://bloodstonewallet.mytunnel.org:50002"],
      ["Web dashboards", "Explorer REST API (read-only)"],
      ["Game engines", "ZMQ game-block-* + game_sendupdates"],
    ],
    [4680, 4680]
  ),

  h1("3. Command index"),
  p("Run bloodstone-cli help for the full list (~186 commands). Categories:"),

  h3("Blockchain (inherited)"),
  p(
    "getblock, getblockchaininfo, getblockcount, getblockstats, getrawmempool, scantxoutset, gettxout, verifychain, …"
  ),
  p("Bloodstone note: getblockstats includes subsidy for live reward verification."),

  h3("Game (Bloodstone)"),
  p("game_sendupdates — on-demand ZMQ catch-up between block hashes."),
  p("trackedgames — add/remove/list game IDs for ZMQ filtering."),

  h3("Mining (Bloodstone extensions)"),
  p("creatework, submitwork, getwork — solo mining with neoscrypt or yespower algo argument."),
  p("generatetoaddress — optional algo; merge-mined blocks use sha256d (chain ID 1899)."),

  h3("Names (Namecoin heritage)"),
  p(
    "name_register, name_update, name_show, name_scan, name_list, name_history, name_pending, sendtoname, queuerawtransaction, …"
  ),
  p("Namespaces: d/, id/, g/, p/. Game moves live in name JSON under .g[GAMEID]."),

  h3("Raw transactions + PSBT"),
  p("Standard Bitcoin suite plus namepsbt and namerawtransaction."),

  h3("Wallet, Network, Util, Zmq"),
  p("Full Bitcoin Core wallet RPC. getzmqnotifications lists active ZMQ publishers."),

  new PageBreak(),

  h1("4. Names RPC"),
  table(
    ["Method", "Purpose"],
    [
      ["name_show", "Current value, owner, height, txid"],
      ["name_scan", "Paginated name iterator"],
      ["name_register", "Register new name"],
      ["name_update", "Update value or transfer (destAddress)"],
      ["sendtoname", "Send STONE to name owner"],
    ],
    [3120, 6240]
  ),
  new Paragraph({ spacing: { after: 160 } }),
  p("Example game move:"),
  mono('bloodstone-cli name_update "p/alice" \'{"g":{"chess":"e4"}}\''),
  p("Upstream game model: SpaceXpanse rod-core-wallet doc/spacexpanse/games.md"),

  h1("5. Mining RPC"),
  p("Solo workflow:"),
  mono('bloodstone-cli creatework "SAddress" "neoscrypt"'),
  mono("bloodstone-cli submitwork \"<hash>\" \"<data>\""),
  p("LAN stratum ports (Android/local node): 3437 neoscrypt, 3438 yespower, 3440 ROD neoscrypt label."),

  h1("6. Game ZMQ"),
  p("Daemon flags:"),
  mono("zmqpubgameblocks=tcp://127.0.0.1:28332"),
  mono("zmqpubgamepending=tcp://127.0.0.1:28332"),
  table(
    ["Publisher", "Topics", "Purpose"],
    [
      ["zmqpubgameblocks", "game-block-attach, game-block-detach", "Block connect/disconnect with moves"],
      ["zmqpubgamepending", "game-tx-pending", "Mempool game transactions"],
    ],
    [2800, 3560, 3000]
  ),
  new Paragraph({ spacing: { after: 160 } }),
  p("Multipart format: game-block-attach json GAMEID | JSON-DATA | SEQ (little-endian 32-bit)."),
  p("Full spec: upstream doc/spacexpanse/interface.md"),

  new PageBreak(),

  h1("7. Exchange integration"),
  p("Use the bloodstone-exchange-node package (txindex + hot wallet). Credit rules from /api/exchange:"),
  table(
    ["Rule", "Value"],
    [
      ["Deposit confirmations", "6"],
      ["Withdrawal confirmations", "6"],
      ["Coinbase maturity", "100 blocks"],
    ],
    [4680, 4680]
  ),
  new Paragraph({ spacing: { after: 160 } }),
  mono("$CLI -conf=$CONF -rpcwallet=exchange-hot getnewaddress \"user-12345\""),
  mono("$CLI -conf=$CONF -rpcwallet=exchange-hot sendtoaddress \"S...\" 1.5"),
  mono("$CLI -conf=$CONF getrawtransaction \"TXID\" true"),
  p("ElectrumX: DAEMON_URL=http://exchange_rpc:PASSWORD@127.0.0.1:18332/"),

  h1("8. Configuration"),
  mono("server=1"),
  mono("txindex=1"),
  mono("rpcport=18332"),
  mono("rpcbind=127.0.0.1"),
  mono("rpcallowip=127.0.0.1"),
  mono("wallet=exchange-hot"),

  h1("9. Explorer REST (read-only)"),
  linkPara(`${COORDINATOR}/explorer/api/stats`, `${COORDINATOR}/explorer/api/stats`),
  linkPara(`${COORDINATOR}/explorer/api/blocks`, `${COORDINATOR}/explorer/api/blocks`),
  p("Not a full RPC replacement — use for dashboards only."),

  h1("10. Upstream references"),
  linkPara("Bitcoin Core RPC", "https://developer.bitcoin.org/reference/rpc/"),
  linkPara(
    "SpaceXpanse game interface",
    "https://github.com/SpaceXpanse/rod-core-wallet/blob/master/doc/spacexpanse/interface.md"
  ),
  linkPara("Exchange listing pack", `${COORDINATOR}/api/exchange`),
  linkPara("Markdown RPC reference", `${COORDINATOR}/downloads/Bloodstone-RPC-Reference.md`),

  h1("11. Troubleshooting"),
  table(
    ["Symptom", "Fix"],
    [
      ["Connection refused :18332", "Start bloodstoned; check rpcbind / rpcallowip"],
      ["401 Unauthorized", "Match rpcuser/rpcpassword in bloodstone.conf"],
      ["getrawtransaction fails", "Enable txindex=1"],
      ["Game ZMQ silent", "trackedgames add \"gameid\""],
      ["Help shows spacexpanse-cli", "Use bloodstone-cli and port 18332"],
    ],
    [4680, 4680]
  ),

  new Paragraph({ spacing: { before: 400 } }),
  p("Bloodstone · Core JSON-RPC reference · July 2026", { italics: true, color: "666666" }),
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
                new TextRun({ text: "Bloodstone · Core JSON-RPC Reference", size: 18, color: "666666" }),
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

const outPath = "/root/bloodstone-docs/Bloodstone-RPC-Reference.docx";
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote", outPath, buffer.length, "bytes");
});