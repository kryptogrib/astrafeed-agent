import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "docs" / "research"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))
