from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow tests to import from the repo-level scripts/ package.
REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/tests -> backend -> Amarktai-App-Builder-4
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("APP_ENV", "test")

