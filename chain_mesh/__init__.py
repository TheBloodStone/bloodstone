"""Decentralized blockchain chunk storage — shard node data across devices.

Version is the single source of truth for the Pi fleet convergence stack
(bloodstone-pi-fleet-convergence-X.Y.Z). Prefer the VERSION file next to this
package or under ops/bloodstone-pi-fleet/.
"""

from pathlib import Path


def _load_version() -> str:
    here = Path(__file__).resolve().parent
    candidates = (
        here / "VERSION",
        here.parent / "ops" / "bloodstone-pi-fleet" / "VERSION",
    )
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text.splitlines()[0].strip()
        except OSError:
            continue
    return "0.36.3-beta"


__version__ = _load_version()

from chain_mesh.config import CHUNK_SIZE, DATADIR, MESH_ROOT
from chain_mesh.assets import publish_asset
from chain_mesh.manifest import current_manifest, publish_manifest
from chain_mesh.restore import restore_from_mesh

__all__ = [
    "__version__",
    "CHUNK_SIZE",
    "DATADIR",
    "MESH_ROOT",
    "current_manifest",
    "publish_asset",
    "publish_manifest",
    "restore_from_mesh",
]
