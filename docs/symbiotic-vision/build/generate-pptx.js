const pptxgen = require("pptxgenjs");

const C = {
  teal: "028090",
  mint: "02C39A",
  navy: "21295C",
  ice: "E8F4F8",
  white: "FFFFFF",
  gray: "666666",
  amber: "F9A825",
  green: "2E7D32",
};

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Bloodstone LLC";
pres.title = "Blurt × Bloodstone — Symbiotic Vision";

function titleSlide(title, subtitle) {
  const s = pres.addSlide();
  s.background = { color: C.navy };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 4.8, w: 10, h: 0.15, fill: { color: C.mint } });
  s.addText(title, { x: 0.6, y: 1.2, w: 8.8, h: 1.4, fontSize: 36, bold: true, color: C.white, fontFace: "Georgia" });
  s.addText(subtitle, { x: 0.6, y: 2.8, w: 8.8, h: 1.2, fontSize: 18, color: C.ice, fontFace: "Calibri" });
  return s;
}

function contentSlide(title, bodyLines, accent) {
  const s = pres.addSlide();
  s.background = { color: C.ice };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.12, h: 5.625, fill: { color: accent || C.teal } });
  s.addText(title, { x: 0.5, y: 0.35, w: 9, h: 0.7, fontSize: 28, bold: true, color: C.navy, fontFace: "Georgia", margin: 0 });
  const items = bodyLines.map((t, i) => ({
    text: t,
    options: { bullet: true, breakLine: i < bodyLines.length - 1, fontSize: 15, color: C.navy, fontFace: "Calibri" },
  }));
  s.addText(items, { x: 0.55, y: 1.15, w: 8.8, h: 4.2, valign: "top", margin: 0 });
  return s;
}

function statSlide(title, stats) {
  const s = pres.addSlide();
  s.background = { color: C.white };
  s.addText(title, { x: 0.5, y: 0.3, w: 9, h: 0.6, fontSize: 28, bold: true, color: C.navy, fontFace: "Georgia", margin: 0 });
  const cols = stats.length;
  const w = 8.8 / cols;
  stats.forEach((st, i) => {
    const x = 0.5 + i * w;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.05, y: 1.2, w: w - 0.15, h: 3.8, fill: { color: C.ice }, rectRadius: 0.08 });
    s.addText(st.val, { x: x + 0.1, y: 1.5, w: w - 0.25, h: 1.2, fontSize: 44, bold: true, color: C.teal, align: "center", margin: 0 });
    s.addText(st.label, { x: x + 0.1, y: 2.8, w: w - 0.25, h: 1.5, fontSize: 13, color: C.navy, align: "center", margin: 0 });
  });
  return s;
}

function layerSlide() {
  const s = pres.addSlide();
  s.background = { color: C.white };
  s.addText("The Living Stack", { x: 0.5, y: 0.25, w: 9, h: 0.6, fontSize: 28, bold: true, color: C.navy, fontFace: "Georgia", margin: 0 });
  const layers = [
    { n: "L6", name: "Autonomous Expansion", st: "PLANNED", col: C.gray },
    { n: "L5", name: "Sovereign Interfaces", st: "BETA", col: C.green },
    { n: "L4", name: "Economic Singularity", st: "BETA", col: C.green },
    { n: "L3", name: "Edge Intelligence Fleet", st: "BETA", col: C.green },
    { n: "L2", name: "Planetary Chain Mesh", st: "BETA", col: C.amber },
    { n: "L1", name: "Eternal Publishing", st: "BETA", col: C.green },
    { n: "L0", name: "Sovereign Digital Souls", st: "BETA", col: C.green },
  ];
  layers.forEach((l, i) => {
    const y = 0.95 + i * 0.62;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y, w: 9, h: 0.52, fill: { color: i % 2 ? C.ice : C.white }, line: { color: "DDDDDD", width: 0.5 } });
    s.addShape(pres.shapes.OVAL, { x: 0.65, y: y + 0.1, w: 0.32, h: 0.32, fill: { color: l.col } });
    s.addText(l.n, { x: 0.65, y: y + 0.1, w: 0.32, h: 0.32, fontSize: 10, bold: true, color: C.white, align: "center", valign: "middle", margin: 0 });
    s.addText(l.name, { x: 1.1, y: y + 0.08, w: 6.5, h: 0.36, fontSize: 14, bold: true, color: C.navy, margin: 0 });
    s.addText(l.st, { x: 7.8, y: y + 0.1, w: 1.5, h: 0.32, fontSize: 11, bold: true, color: l.col, align: "right", margin: 0 });
  });
  return s;
}

// Slides
titleSlide("Blurt × Bloodstone", "The Symbiotic Vision — A Sovereign Internet Awakens (2027–2035)\nJuly 2026 · v0.15.0-beta");

contentSlide("Executive Summary", [
  "Every Raspberry Pi as a sovereign node — censorship-resistant publishing + unstoppable storage mesh",
  "Self-healing, self-funding nervous system for human civilization",
  "Blurt = trust anchor & identity · Bloodstone = memory & compute fabric",
  "Layers 0–5 in beta today · Layer 6 on 2030+ horizon",
  "Not competing with the legacy web — replacing its fragile core",
], C.teal);

layerSlide();

contentSlide("Layer 0–2: Identity, Publishing, Mesh", [
  "L0: bloodstone_agent/v1 — Blurt keys + AI agent identity",
  "L1: bloodstone_provenance/v1 — Post-Truth Engine, blog manifests",
  "L2: BSM1 chunks + DTN bundles — 72h offline sync, quorum 2-of-3",
  "mDNS _bloodstone-dtn._tcp + TLS peer forwards (Wave E)",
  "HTTP Range streaming for video on any Pi node",
], C.teal);

contentSlide("Layer 3–6: Edge, Economy, UI, AI", [
  "L3: Pi/Android providers — storage, compute, bandwidth, sensor",
  "L4: BLURT→STONE memo rails (storage, compute, bandwidth)",
  "L5: Condenser embed + spatial WebXR + AR geo overlays",
  "L6 (planned): AI curation, DAO bounties, viral node replication",
  "QUASAR Phases 1–5: braid finality defense in core",
], C.mint);

contentSlide("Use Case: Eternal Dissident Journalist", [
  "Investigation sharded across nodes — survives ISP blocks & firewalls",
  "Accessible via LAN mesh, DTN sneakernet, satellite handoff (roadmap)",
  "Audience pays BLURT/STONE directly — node operators earn hosting fees",
  "Provenance anchor proves authenticity against deep fakes",
  "Fit today: STRONG — provenance + mesh + DTN forward live",
], C.navy);

contentSlide("Use Case: Disaster / Village Mesh", [
  "Hurricane or blackout — Pis keep digital life alive locally",
  "DTN store-and-forward queues bundles until brief uplink windows",
  "mDNS discovers neighbors; TLS secures peer bundle exchange",
  "Quorum heal replicates under-provisioned chunks automatically",
  "Fit today: STRONGEST — Waves C–E built exactly for this",
], C.teal);

contentSlide("Use Case: Creator Media Empire", [
  "Zero platform rent — your audience graph, your revenue",
  "HTTP Range video from neighborhood Pis (not centralized CDN)",
  "Condenser embed — paste into Blurt posts, iframe anywhere",
  "Fans earn STONE seeding content they love (rails designed)",
  "Fit today: MODERATE — streaming + embed live, incentives next",
], C.mint);

statSlide("Live Today — July 2026", [
  { val: "6", label: "Convergence Layers\n(0–5 beta)" },
  { val: "A–E", label: "Waves Complete\nprovenance → TLS" },
  { val: "5", label: "QUASAR Phase\nbraid validation" },
  { val: "7+", label: "DTN Peers\nmDNS + TLS" },
]);

contentSlide("Economic Hyper-Flywheel", [
  "Creation → content floods the network",
  "Demand → storage & bandwidth drive STONE value",
  "Infrastructure → millions run nodes, earn while strengthening mesh",
  "Innovation → developers & AIs build on open APIs",
  "Adoption → billions participate → compounding returns",
  "Dual token: BLURT rewards creativity · STONE pays infrastructure",
], C.teal);

contentSlide("Roadmap 2027–2035", [
  "2027 Spine ✓ — Layers 0–5 beta, Waves A–E complete",
  "2028–29 Scale — enforce memo rails, compute job manifests, Pi fleet",
  "2030–32 Mesh — gossip protocol, Starlink handoff, offline Condenser",
  "2033–35 Symbiosis — L6 AI ecosystem, DAO bounties, closed flywheel",
  "Verify: GET /api/convergence/status",
], C.navy);

const end = pres.addSlide();
end.background = { color: C.navy };
end.addText("Let\u2019s build the\nSymbiotic Stack.", { x: 0.6, y: 1.0, w: 8.8, h: 2.0, fontSize: 40, bold: true, color: C.white, fontFace: "Georgia", margin: 0 });
end.addText("Blurt + Bloodstone = the permanent, self-owning nervous system\nof a free and creative humanity.", { x: 0.6, y: 3.2, w: 8.8, h: 1.2, fontSize: 16, color: C.ice, fontFace: "Calibri", margin: 0 });
end.addText("bloodstonewallet.mytunnel.org", { x: 0.6, y: 4.6, w: 8.8, h: 0.5, fontSize: 14, color: C.mint, margin: 0 });

const out = "/root/bloodstone-docs/symbiotic-vision/Bloodstone-Symbiotic-Vision-Deck.pptx";
pres.writeFile({ fileName: out }).then(() => console.log("wrote", out));