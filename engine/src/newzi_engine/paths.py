import os
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = ENGINE_ROOT.parent
ENGINE_CONFIG = ENGINE_ROOT / 'config'
ENGINE_FIXTURES = ENGINE_ROOT / 'fixtures'
_data_root = Path(os.environ.get('NEWS_ENGINE_DATA_DIR', ENGINE_ROOT / 'data')).expanduser()
ENGINE_DATA = _data_root if _data_root.is_absolute() else (PROJECT_ROOT / _data_root).resolve()
ENGINE_OUTPUT = ENGINE_DATA / 'output'

def engine_path(*parts: str) -> Path:
    return ENGINE_ROOT.joinpath(*parts)

def engine_data_path(*parts: str) -> Path:
    return ENGINE_DATA.joinpath(*parts)

def engine_output_path(*parts: str) -> Path:
    return ENGINE_OUTPUT.joinpath(*parts)
