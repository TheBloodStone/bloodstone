"""Chain mesh paths and tunables."""

import os

DATADIR = os.environ.get(
    "BLOODSTONE_DATADIR",
    os.environ.get("CHAIN_MESH_DATADIR", "/root/.bloodstone"),
)
MESH_ROOT = os.environ.get("CHAIN_MESH_ROOT", "/var/lib/bloodstone-chain-mesh")
DB_PATH = os.environ.get("CHAIN_MESH_DB", os.path.join(MESH_ROOT, "mesh.db"))
CHUNK_STORE = os.environ.get("CHAIN_MESH_CHUNK_DIR", os.path.join(MESH_ROOT, "chunks"))

# 256 KiB — small enough for phones, large enough for reasonable manifest size.
CHUNK_SIZE = int(os.environ.get("CHAIN_MESH_CHUNK_SIZE", str(256 * 1024)))

CLI = os.environ.get("BLOODSTONE_CLI", "/root/bloodstone-cli")
CONF = os.environ.get("BLOODSTONE_CONF", os.path.join(DATADIR, "bloodstone.conf"))

# Relative paths inside datadir that are safe to shard (immutable block files).
SHARD_SOURCES = (
    "blocks/blk00000.dat",
    "blocks/blk00001.dat",
    "blocks/blk00002.dat",
    "blocks/blk00003.dat",
    "blocks/blk00004.dat",
    "blocks/blk00005.dat",
    "blocks/blk00006.dat",
    "blocks/blk00007.dat",
    "blocks/blk00008.dat",
    "blocks/blk00009.dat",
    "blocks/rev00000.dat",
    "blocks/rev00001.dat",
    "blocks/rev00002.dat",
    "blocks/rev00003.dat",
    "blocks/rev00004.dat",
    "blocks/rev00005.dat",
    "blocks/rev00006.dat",
    "blocks/rev00007.dat",
    "blocks/rev00008.dat",
    "blocks/rev00009.dat",
)

MAX_CHUNK_UPLOAD_BYTES = int(os.environ.get("CHAIN_MESH_MAX_UPLOAD", str(CHUNK_SIZE + 4096)))
MAX_CHUNKS_PER_DEVICE = int(os.environ.get("CHAIN_MESH_MAX_CHUNKS_PER_DEVICE", "96"))
# Blurt tenant default (July 2026): 256 MiB per file, up to ~1 GiB via 1024 × 256 KiB chunks.
BLURT_MAX_ASSET_BYTES = 256 * 1024 * 1024
BLURT_MAX_ASSET_CHUNKS = 1024
MAX_ASSET_PUBLISH_BYTES = int(
    os.environ.get("CHAIN_MESH_MAX_ASSET_BYTES", str(BLURT_MAX_ASSET_BYTES))
)
MAX_ASSET_PUBLISH_CHUNKS = int(
    os.environ.get("CHAIN_MESH_MAX_ASSET_CHUNKS", str(BLURT_MAX_ASSET_CHUNKS))
)
PUBLISH_TOKEN = os.environ.get("CHAIN_MESH_PUBLISH_TOKEN", "").strip()
# Each node independently backs up this percentage of manifest chunks (hash of node ID).
CHAIN_MESH_BACKUP_PCT = int(os.environ.get("CHAIN_MESH_BACKUP_PCT", "10"))

# Time Capsule — archive to mesh first; prune local disk only when explicitly enabled.
TIME_CAPSULE_ENABLE_PRUNE = os.environ.get("BLOODSTONE_TIME_CAPSULE_ENABLE_PRUNE", "0") == "1"
TIME_CAPSULE_PRUNE_MIB = int(os.environ.get("BLOODSTONE_TIME_CAPSULE_PRUNE_MIB", "550"))
TIME_CAPSULE_MIN_PEER_UNIQUE_CHUNKS = int(
    os.environ.get("BLOODSTONE_TIME_CAPSULE_MIN_PEER_CHUNKS", "0")
)