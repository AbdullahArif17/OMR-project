import sys
from pathlib import Path

# Add the parent directory to sys.path so that local module imports work
sys.path.append(str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402
