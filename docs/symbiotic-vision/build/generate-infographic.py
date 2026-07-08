#!/usr/bin/env python3
"""One-page Living Stack infographic with live/planned status colors."""

from PIL import Image, ImageDraw, ImageFont

W, H = 1400, 2000
OUT = "/root/bloodstone-docs/symbiotic-vision/Bloodstone-Symbiotic-Stack-Infographic.png"

COLORS = {
    "bg": (33, 41, 92),
    "panel": (232, 244, 248),
    "teal": (2, 128, 144),
    "mint": (2, 195, 154),
    "white": (255, 255, 255),
    "green": (46, 125, 50),
    "amber": (249, 168, 37),
    "gray": (120, 120, 120),
    "navy": (33, 41, 92),
}

LAYERS = [
    ("L6", "Autonomous Expansion", "AI agents · DAO bounties · viral nodes", "PLANNED", "gray"),
    ("L5", "Sovereign Interfaces", "Condenser embed · WebXR · AR overlays", "BETA", "green"),
    ("L4", "Economic Singularity", "STONE + BLURT memo rails · dual flywheel", "BETA", "green"),
    ("L3", "Edge Intelligence Fleet", "Pi/mobile nodes · mDNS · Bitaxe mining", "BETA", "green"),
    ("L2", "Planetary Chain Mesh", "BSM1 chunks · DTN · quorum · TLS", "SCALING", "amber"),
    ("L1", "Eternal Publishing", "Provenance · blog manifests · archive", "BETA", "green"),
    ("L0", "Sovereign Digital Souls", "Blurt keys · agent identity · wallet", "BETA", "green"),
]

WAVES = "Wave A ✓  Wave B ✓  Wave C ✓  Wave D ✓  Wave E ✓"
FOOTER = "v0.15.0-beta · July 2026 · bloodstonewallet.mytunnel.org"


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    img = Image.new("RGB", (W, H), COLORS["bg"])
    draw = ImageDraw.Draw(img)

    f_title = font(52, True)
    f_sub = font(24)
    f_h = font(20, True)
    f_b = font(17)
    f_s = font(15)
    f_leg = font(14)

    draw.text((W // 2, 70), "BLURT × BLOODSTONE", fill=COLORS["mint"], font=f_title, anchor="mm")
    draw.text((W // 2, 130), "The Living Stack — Symbiotic Vision", fill=COLORS["white"], font=f_sub, anchor="mm")
    draw.rectangle([60, 160, W - 60, 164], fill=COLORS["mint"])

    y = 200
    box_h = 200
    for lid, name, detail, status, sc in LAYERS:
        draw.rounded_rectangle([60, y, W - 60, y + box_h], radius=16, fill=COLORS["panel"])
        dot = COLORS[sc]
        draw.ellipse([85, y + 28, 125, y + 68], fill=dot)
        draw.text((105, y + 48), lid, fill=COLORS["white"], font=f_h, anchor="mm")
        draw.text((145, y + 28), name, fill=COLORS["navy"], font=f_h)
        draw.text((145, y + 62), detail, fill=(80, 80, 100), font=f_b)
        sw = draw.textlength(status, font=f_h)
        draw.text((W - 85 - sw, y + 36), status, fill=dot, font=f_h)
        y += box_h + 18

    draw.rounded_rectangle([60, y + 20, W - 60, y + 100], radius=12, fill=COLORS["teal"])
    draw.text((W // 2, y + 60), WAVES, fill=COLORS["white"], font=f_sub, anchor="mm")

    ly = y + 130
    legend = [
        (COLORS["green"], "LIVE BETA — shipping APIs"),
        (COLORS["amber"], "SCALING — beta, not planetary yet"),
        (COLORS["gray"], "PLANNED — 2030+ horizon"),
    ]
    for col, label in legend:
        draw.ellipse([80, ly, 100, ly + 20], fill=col)
        draw.text((115, ly + 2), label, fill=COLORS["white"], font=f_leg)
        ly += 32

    draw.text((W // 2, H - 50), FOOTER, fill=COLORS["mint"], font=f_leg, anchor="mm")
    img.save(OUT, "PNG", optimize=True)
    print("wrote", OUT, img.size)


if __name__ == "__main__":
    main()