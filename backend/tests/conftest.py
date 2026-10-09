import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import support  # noqa: E402,F401  (configures the isolated test environment before any backend import)
