"""Installer icon branding for Windows GUI packages."""

from __future__ import annotations

import os
import shutil
import struct
import zlib
from datetime import datetime
from typing import Dict, List, Tuple

BRANDING_DIR = os.environ.get(
    "BLOODSTONE_INSTALLER_BRANDING_DIR", "/var/www/bloodstone/branding"
)
ICON_PNG_NAME = "installer-icon.png"
ICON_ICO_NAME = "installer-icon.ico"
META_NAME = "installer-icon.meta"

GUI_ASSET_DIRS = [
    "/root/bloodstone-node-gui/assets",
    "/root/bloodstone-wallet-node-gui/assets",
]

# Core Qt wallet trees (splash + window icon use res/icons/bitcoin.png).
QT_CHAIN_ROOTS = [
    "/root/bloodstone-chain",
    "/root/bloodstone-linux-build",
    "/root/bloodstone-win-build",
    "/root/bloodstone-arm-build",
]

QT_ICON_SIZES = [16, 32, 64, 128, 256, 512, 1024]

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MIN_ICON_SIZE = 64
MAX_ICON_SIZE = 1024


def icon_png_path() -> str:
    return os.path.join(BRANDING_DIR, ICON_PNG_NAME)


def icon_ico_path() -> str:
    return os.path.join(BRANDING_DIR, ICON_ICO_NAME)


def meta_path() -> str:
    return os.path.join(BRANDING_DIR, META_NAME)


def ensure_branding_dir() -> None:
    os.makedirs(BRANDING_DIR, mode=0o755, exist_ok=True)


def _read_png_dimensions(data: bytes) -> Tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("File must be a PNG image.")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise ValueError("PNG has invalid dimensions.")
    return width, height


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    body = chunk_type + payload
    crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return struct.pack(">I", len(payload)) + body + crc


def _resize_png_nearest(data: bytes, size: int) -> bytes:
    width, height = _read_png_dimensions(data)
    if width == size and height == size:
        return data

    src = _decode_png_rgba(data)
    dst = _resize_rgba_nearest(src, width, height, size, size)
    return _encode_png_rgba(dst, size, size)


def _decode_png_rgba(data: bytes) -> List[Tuple[int, int, int, int]]:
    if data[12:16] != b"IHDR":
        raise ValueError("Invalid PNG (missing IHDR).")

    width, height = struct.unpack(">II", data[16:24])
    bit_depth = data[24]
    color_type = data[25]
    if bit_depth != 8 or color_type != 6:
        raise ValueError("PNG must be 8-bit RGBA.")

    pos = 8
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    pixels: List[Tuple[int, int, int, int]] = []
    offset = 0
    for _ in range(height):
        offset += 1  # filter byte
        row = raw[offset : offset + stride]
        offset += stride
        for i in range(0, stride, 4):
            pixels.append((row[i], row[i + 1], row[i + 2], row[i + 3]))
    return pixels


def _resize_rgba_nearest(
    src: List[Tuple[int, int, int, int]],
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> List[Tuple[int, int, int, int]]:
    out: List[Tuple[int, int, int, int]] = []
    for y in range(dst_h):
        sy = min(src_h - 1, int(y * src_h / dst_h))
        for x in range(dst_w):
            sx = min(src_w - 1, int(x * src_w / dst_w))
            out.append(src[sy * src_w + sx])
    return out


def _encode_png_rgba(
    pixels: List[Tuple[int, int, int, int]], width: int, height: int
) -> bytes:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        row_start = y * width
        for x in range(width):
            r, g, b, a = pixels[row_start + x]
            raw.extend((r, g, b, a))

    compressed = zlib.compress(bytes(raw), level=9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def _write_ico_from_png(png_data: bytes, out_path: str) -> None:
    sizes = [256, 128, 64, 48, 32, 16]
    images: List[bytes] = []
    for size in sizes:
        try:
            images.append(_resize_png_nearest(png_data, size))
        except ValueError:
            continue
    if not images:
        raise ValueError("Could not prepare icon sizes for ICO.")

    with open(out_path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(images)))
        offset = 6 + 16 * len(images)
        entries: List[bytes] = []
        blobs: List[bytes] = []
        for png in images:
            width, height = _read_png_dimensions(png)
            width_byte = 0 if width >= 256 else width
            height_byte = 0 if height >= 256 else height
            blob = png
            entries.append(
                struct.pack(
                    "<BBBBHHII",
                    width_byte,
                    height_byte,
                    0,
                    0,
                    1,
                    32,
                    len(blob),
                    offset,
                )
            )
            blobs.append(blob)
            offset += len(blob)
        for entry in entries:
            fh.write(entry)
        for blob in blobs:
            fh.write(blob)


def validate_png_upload(file_storage) -> bytes:
    data = file_storage.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise ValueError("No file uploaded.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Image is too large (max 2 MB).")

    width, height = _read_png_dimensions(data)
    if width != height:
        raise ValueError("Image must be square (same width and height).")
    if width < MIN_ICON_SIZE or width > MAX_ICON_SIZE:
        raise ValueError(
            f"Image must be between {MIN_ICON_SIZE}×{MIN_ICON_SIZE} and "
            f"{MAX_ICON_SIZE}×{MAX_ICON_SIZE} pixels."
        )
    return data


def sync_to_gui_projects() -> List[str]:
    png = icon_png_path()
    ico = icon_ico_path()
    if not os.path.isfile(png):
        raise FileNotFoundError("Installer icon PNG is not configured yet.")

    updated: List[str] = []
    for assets_dir in GUI_ASSET_DIRS:
        os.makedirs(assets_dir, exist_ok=True)
        shutil.copy2(png, os.path.join(assets_dir, "icon.png"))
        if os.path.isfile(ico):
            shutil.copy2(ico, os.path.join(assets_dir, "icon.ico"))
        updated.append(assets_dir)
    return updated


def _write_png(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def sync_to_qt_projects() -> List[str]:
    """Copy admin coin image into Qt wallet icon resources (splash + app icon)."""
    png = icon_png_path()
    if not os.path.isfile(png):
        raise FileNotFoundError("Installer icon PNG is not configured yet.")

    with open(png, "rb") as fh:
        source = fh.read()

    updated: List[str] = []
    for chain_root in QT_CHAIN_ROOTS:
        qt_icon = os.path.join(chain_root, "src/qt/res/icons/bitcoin.png")
        pixmaps_dir = os.path.join(chain_root, "share/pixmaps")
        if not os.path.isdir(os.path.dirname(qt_icon)) and not os.path.isdir(pixmaps_dir):
            continue

        if os.path.isdir(os.path.dirname(qt_icon)):
            icon_1024 = _resize_png_nearest(source, 1024)
            _write_png(qt_icon, icon_1024)
            updated.append(qt_icon)

        if os.path.isdir(pixmaps_dir):
            for size in QT_ICON_SIZES:
                out = os.path.join(pixmaps_dir, f"bitcoin{size}.png")
                _write_png(out, _resize_png_nearest(source, size))
            updated.append(pixmaps_dir)

    return updated


def sync_all_branding() -> Dict[str, List[str]]:
    return {
        "gui_dirs": sync_to_gui_projects(),
        "qt_paths": sync_to_qt_projects(),
    }


def save_uploaded_png(file_storage, uploaded_by: str = "admin") -> Dict[str, object]:
    data = validate_png_upload(file_storage)
    ensure_branding_dir()

    png_path = icon_png_path()
    ico_path = icon_ico_path()
    with open(png_path, "wb") as fh:
        fh.write(data)
    _write_ico_from_png(data, ico_path)

    width, height = _read_png_dimensions(data)
    synced = sync_all_branding()
    mtime = os.path.getmtime(png_path)
    meta = (
        f"updated_utc={datetime.utcfromtimestamp(mtime).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"uploaded_by={uploaded_by}\n"
        f"width={width}\n"
        f"height={height}\n"
    )
    with open(meta_path(), "w", encoding="utf-8") as fh:
        fh.write(meta)

    return {
        "width": width,
        "height": height,
        "synced_dirs": synced.get("gui_dirs", []),
        "synced_qt_paths": synced.get("qt_paths", []),
        "updated_utc": datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_icon_info() -> Dict[str, object]:
    png = icon_png_path()
    if not os.path.isfile(png):
        return {"configured": False}

    width, height = _read_png_dimensions(open(png, "rb").read())
    stat = os.stat(png)
    meta: Dict[str, str] = {}
    if os.path.isfile(meta_path()):
        with open(meta_path(), encoding="utf-8") as fh:
            for line in fh:
                if "=" in line:
                    key, val = line.split("=", 1)
                    meta[key.strip()] = val.strip()

    public_root = os.environ.get("BLOODSTONE_PUBLIC_URL", "").rstrip("/")
    if public_root.endswith("/mining"):
        public_root = public_root[: -len("/mining")]
    preview_url = f"{public_root}/branding/{ICON_PNG_NAME}" if public_root else None

    return {
        "configured": True,
        "width": width,
        "height": height,
        "size_bytes": stat.st_size,
        "updated_utc": datetime.utcfromtimestamp(stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M UTC"
        ),
        "uploaded_by": meta.get("uploaded_by"),
        "preview_url": preview_url,
        "png_path": png,
        "ico_path": icon_ico_path() if os.path.isfile(icon_ico_path()) else None,
    }