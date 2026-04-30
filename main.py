from pathlib import Path
import sys

# Allow `uvicorn main:app` from repository root by exposing backend/ on sys.path.
BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.main import app  # noqa: E402,F401
