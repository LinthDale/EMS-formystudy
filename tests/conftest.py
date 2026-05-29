"""Root conftest: adds simulator source to sys.path so unit tests can import main."""
import sys
from pathlib import Path

_tests_dir = Path(__file__).parent
_root = _tests_dir.parent

# Support two layouts:
#   project: EMS/tests/conftest.py  → EMS/services/simulator/src/main.py
#   container: /app/tests/conftest.py → /app/src/main.py
_candidates = [
    _root / "services" / "simulator" / "src",
    _root / "src",
]
for _p in _candidates:
    if (_p / "main.py").exists():
        sys.path.insert(0, str(_p))
        break

# device-service package (PRD-0003) — import as `device_service`
for _dp in (_root / "services" / "device-service", _root):
    if (_dp / "device_service" / "__init__.py").exists():
        sys.path.insert(0, str(_dp))
        break