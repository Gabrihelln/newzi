"""CPU-only machine translation for briefing narration (Argos Translate models via CTranslate2).

Models are plain Argos packages (CTranslate2 model + SentencePiece tokenizer); they are loaded
directly so no GPU, stanza, spacy or torch is required. Install them with:

    python -m newzi_backend.translation --download
"""
import io
import json
import logging
import os
import re
import threading
import urllib.request
import zipfile
from pathlib import Path

from .paths import BACKEND_DATA

log = logging.getLogger(__name__)

MODELS_DIR = Path(os.getenv("TRANSLATION_MODELS_DIR", str(BACKEND_DATA / "models" / "translation")))
ARGOS_INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
SUPPORTED_PAIRS = (("en", "pt"), ("pt", "en"))
# Only the narrated opening is translated; translating whole articles would only cost time.
MAX_SUMMARY_WORDS = 90


def _base(language):
    return str(language or "").split("-")[0].lower()


def _sentences(text):
    return [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]


class ArgosTranslator:
    """Translates the narration fields of a briefing item into the briefing language."""

    def __init__(self, models_dir=MODELS_DIR, threads=None):
        self.models_dir = Path(models_dir)
        self.threads = int(threads or os.getenv("TRANSLATION_THREADS", "4"))
        self._loaded = {}
        self._lock = threading.Lock()

    def _package_dir(self, source, target):
        root = self.models_dir / f"{source}_{target}"
        if not root.is_dir():
            return None
        return next((path.parent for path in root.rglob("sentencepiece.model") if (path.parent / "model").is_dir()), None)

    def available(self, source="en", target="pt"):
        try:
            import ctranslate2  # noqa: F401
            import sentencepiece  # noqa: F401
        except ImportError:
            return False
        return self._package_dir(source, target) is not None

    def _model(self, source, target):
        with self._lock:
            key = (source, target)
            if key not in self._loaded:
                import ctranslate2
                import sentencepiece
                package = self._package_dir(source, target)
                if package is None:
                    raise RuntimeError(f"translation model missing: {source}->{target}")
                self._loaded[key] = (ctranslate2.Translator(str(package / "model"), device="cpu", intra_threads=self.threads),
                                     sentencepiece.SentencePieceProcessor(model_file=str(package / "sentencepiece.model")))
            return self._loaded[key]

    def translate_text(self, text, source, target):
        sentences = _sentences(text or "")
        if not sentences:
            return ""
        translator, tokenizer = self._model(source, target)
        results = translator.translate_batch([tokenizer.encode(sentence, out_type=str) for sentence in sentences],
                                             beam_size=2, max_decoding_length=256)
        # Argos models emit SentencePiece pieces; "▁" marks a word boundary.
        return " ".join("".join(result.hypotheses[0]).replace("▁", " ").strip() for result in results)

    def translate(self, fields, language):
        """AudioScriptComposer translator contract: same keys, values in the briefing language."""
        target = _base(language)
        source = "en" if target == "pt" else "pt"
        if (source, target) not in SUPPORTED_PAIRS:
            raise RuntimeError(f"unsupported translation target: {language}")
        output = {}
        for key, value in fields.items():
            text = str(value or "")
            if key == "summary":
                kept, count = [], 0
                for sentence in _sentences(text):
                    count += len(sentence.split())
                    kept.append(sentence)
                    if count >= MAX_SUMMARY_WORDS:
                        break
                text = " ".join(kept)
            output[key] = self.translate_text(text, source, target) if text else ""
        return output


_default = None


def default_translator():
    """Shared translator when models are installed; None keeps narration in the source language."""
    global _default
    if _default is None:
        candidate = ArgosTranslator()
        if not candidate.available("en", "pt") and not candidate.available("pt", "en"):
            log.warning("translation models not installed in %s; foreign-language stories are narrated untranslated", candidate.models_dir)
            return None
        _default = candidate
    return _default


def download_models(models_dir=MODELS_DIR):
    headers = {"User-Agent": "Mozilla/5.0 (Newzi translation model setup)"}
    fetch = lambda url: urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600).read()
    index = json.loads(fetch(ARGOS_INDEX_URL))
    for source, target in SUPPORTED_PAIRS:
        package = next(item for item in index if item["from_code"] == source and item["to_code"] == target)
        data = None
        for link in package["links"]:
            try:
                data = fetch(link)
                break
            except Exception as exc:  # try the next mirror
                log.warning("translation model download failed from %s: %s", link, exc)
        if data is None:
            raise RuntimeError(f"could not download translation model {source}->{target}")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(Path(models_dir) / f"{source}_{target}")
        print(f"{source}->{target} {package.get('package_version')} installed in {Path(models_dir) / f'{source}_{target}'}")


if __name__ == "__main__":
    import sys
    if "--download" in sys.argv:
        download_models()
    else:
        print(__doc__)
