# Make the local test helper (_fakes) importable regardless of pytest import mode.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
