"""Settings (config.yaml), secrets (.env) and project paths."""
import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"
ASSETS = ROOT / "assets"
SECRETS_DIR = Path.home() / ".config" / "thoma-studio"


def _load_env():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #")[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@lru_cache
def cfg() -> dict:
    _load_env()
    DATA.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def secret(name: str) -> str:
    cfg()
    return os.environ.get(name, "").strip()
