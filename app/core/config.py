from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def resource_path(relative: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / relative
    return Path(__file__).resolve().parents[1] / relative


def load_rules(path: Path | None = None) -> dict[str, Any]:
    rules_path = path or resource_path("config/rules.json")
    with rules_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
