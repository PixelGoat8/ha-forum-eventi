"""I moduli di parsing/punteggio non dipendono da HA: li carichiamo senza eseguire
custom_components/forum_eventi/__init__.py (che importa homeassistant)."""
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "forum_eventi"
for name, path in (("custom_components", PKG_DIR.parent), ("custom_components.forum_eventi", PKG_DIR)):
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]
    sys.modules.setdefault(name, mod)

FIXTURES = Path(__file__).parent / "fixtures"
