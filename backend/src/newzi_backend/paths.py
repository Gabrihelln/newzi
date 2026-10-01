from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
BACKEND_DATA = BACKEND_ROOT / 'data'

def backend_path(*parts: str) -> Path:
    return BACKEND_ROOT.joinpath(*parts)
