"""Edition-scoped audio scripts, durable TTS jobs and local artifact storage."""
import hashlib
import base64
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .paths import BACKEND_DATA


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class PermanentAudioError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class TTSOptions:
    sample_rate: int = 16000
    target_duration_seconds: int = 300


class TTSProvider:
    name = "abstract"
    version = "v1"
    extension = ".wav"

    def list_voices(self):
        return []

    def health_check(self):
        return bool(self.list_voices())

    def capabilities(self):
        return {"language": [], "ssml": False, "speaking_rate": False}

    def synthesize(self, text, voice, language, options=None):
        raise NotImplementedError

    def synthesize_segments(self, segments, voice, language, options=None):
        return self.synthesize("\n\n".join(segment["text"] for segment in segments), voice, language, options)


class LocalTTSProvider(TTSProvider):
    """Use an installed system voice; never silently use English for pt-BR."""
    name = "local-system"
    version = "v1"

    def synthesize(self, text, voice, language, options=None):
        try:
            import pyttsx3
        except ImportError as exc:
            raise PermanentAudioError("TTS_NOT_INSTALLED", "install pyttsx3 for local TTS") from exc
        engine = pyttsx3.init()
        wanted = language.lower().replace("_", "-")
        def matches(candidate):
            values = [str(getattr(candidate, "id", "")), str(getattr(candidate, "name", ""))]
            values += [value.decode("utf-8", "ignore") if isinstance(value, bytes) else str(value)
                       for value in getattr(candidate, "languages", []) or []]
            joined = " ".join(values).lower().replace("_", "-")
            return wanted in joined or (wanted == "pt-br" and ("brazil" in joined or "brasil" in joined))
        voices = engine.getProperty("voices") or []
        selected = next((candidate for candidate in voices if voice not in ("", "auto", "default")
                         and voice.lower() in (str(candidate.id) + " " + str(candidate.name)).lower()
                         and matches(candidate)), None)
        if selected is None and voice in ("", "auto", "default"):
            selected = next((candidate for candidate in voices if matches(candidate)), None)
        if selected is None:
            raise PermanentAudioError("VOICE_UNAVAILABLE", f"no installed {language} voice matches {voice}")
        engine.setProperty("voice", selected.id)
        output = Path(os.environ.get("NEWS_AUDIO_TMP", str(BACKEND_DATA / "audio"))) / ("tts_" + uuid.uuid4().hex + ".wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        engine.save_to_file(text, str(output))
        engine.runAndWait()
        if not output.is_file() or not output.stat().st_size:
            raise RuntimeError("TTS produced no audio")
        with wave.open(str(output), "rb") as stream:
            duration_ms = int(stream.getnframes() * 1000 / max(1, stream.getframerate()))
        return {"path": str(output), "mime_type": "audio/wav", "duration_ms": duration_ms,
                "size_bytes": output.stat().st_size, "resolved_voice": selected.id}

    def synthesize_segments(self, segments, voice, language, options=None):
        parts = []
        output = Path(os.environ.get("NEWS_AUDIO_TMP", str(BACKEND_DATA / "audio"))) / ("tts_briefing_" + uuid.uuid4().hex + ".wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        timings = []
        resolved_voice = None
        try:
            with wave.open(str(output), "wb") as combined:
                parameters = None
                elapsed_ms = 0
                for segment in segments:
                    part = self.synthesize(segment["text"], voice, language, options)
                    resolved_voice = resolved_voice or part.get("resolved_voice")
                    parts.append(Path(part["path"]))
                    with wave.open(part["path"], "rb") as stream:
                        current = (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype())
                        if parameters is None:
                            parameters = current
                            combined.setparams(stream.getparams())
                        elif current != parameters:
                            raise PermanentAudioError("TTS_FORMAT_MISMATCH", "TTS segments have incompatible formats")
                        duration = int(stream.getnframes() * 1000 / stream.getframerate())
                        combined.writeframes(stream.readframes(stream.getnframes()))
                    timings.append((segment["id"], elapsed_ms, elapsed_ms + duration))
                    elapsed_ms += duration
            return {"path": str(output), "mime_type": "audio/wav", "duration_ms": elapsed_ms,
                    "size_bytes": output.stat().st_size, "segment_timings": timings,
                    "resolved_voice": resolved_voice}
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            for part in parts:
                part.unlink(missing_ok=True)


class WindowsSAPIProvider(LocalTTSProvider):
    """Offline Windows SAPI speech through the installed PowerShell COM runtime."""
    name = "windows-sapi"
    version = "v1"

    def list_voices(self):
        if os.name != "nt":
            return []
        script = "$s=New-Object -ComObject SAPI.SpVoice; $s.GetVoices() | ForEach-Object { $_.GetDescription() }"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=15, check=False)
        return result.stdout.splitlines() if result.returncode == 0 else []

    def capabilities(self):
        return {"language": ["pt-BR", "en"], "ssml": False, "speaking_rate": False}

    def synthesize(self, text, voice, language, options=None):
        if os.name != "nt":
            raise PermanentAudioError("TTS_PLATFORM_UNAVAILABLE", "Windows SAPI requires Windows")
        directory = Path(os.environ.get("NEWS_AUDIO_TMP", str(BACKEND_DATA / "audio")))
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / ("tts_" + uuid.uuid4().hex + ".wav")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", dir=directory,
                                         delete=False) as source:
            source.write(text)
            source_path = Path(source.name)
        script = r"""
$ErrorActionPreference = 'Stop'
$speaker = New-Object -ComObject SAPI.SpVoice
$selected = $null
foreach ($candidate in $speaker.GetVoices()) {
  $description = $candidate.GetDescription()
  $identity = $candidate.Id
  $locale = $env:NEWZI_TTS_LANGUAGE
  $matchesLocale = if ($locale -eq 'pt-BR') {
    $identity -match 'PT-BR|ptBR' -or $description -match 'Portuguese.*Brazil|Português.*Brasil'
  } elseif ($locale -match '^en') {
    $identity -match 'EN-US|enUS|EN-GB' -or $description -match 'English'
  } else { $identity -match [regex]::Escape($locale) -or $description -match [regex]::Escape($locale) }
  $matchesVoice = $env:NEWZI_TTS_VOICE -in @('auto', 'default', '') -or
                  $identity.IndexOf($env:NEWZI_TTS_VOICE, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                  $description.IndexOf($env:NEWZI_TTS_VOICE, [StringComparison]::OrdinalIgnoreCase) -ge 0
  if ($matchesLocale -and $matchesVoice) { $selected = $candidate; break }
}
if ($null -eq $selected) { throw "VOICE_UNAVAILABLE: $($env:NEWZI_TTS_LANGUAGE) $($env:NEWZI_TTS_VOICE)" }
$speaker.Voice = $selected
$stream = New-Object -ComObject SAPI.SpFileStream
try {
  $stream.Open($env:NEWZI_TTS_OUTPUT_FILE, 3, $false)
  $speaker.AudioOutputStream = $stream
  $content = Get-Content -LiteralPath $env:NEWZI_TTS_TEXT_FILE -Raw -Encoding UTF8
  [void]$speaker.Speak($content, 0)
} finally { $stream.Close() }
Write-Output $selected.GetDescription()
"""
        env = os.environ.copy()
        env.update({"NEWZI_TTS_LANGUAGE": language, "NEWZI_TTS_VOICE": voice,
                    "NEWZI_TTS_TEXT_FILE": str(source_path), "NEWZI_TTS_OUTPUT_FILE": str(output)})
        try:
            command = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Sta",
                                     "-EncodedCommand", command], env=env, capture_output=True,
                                    text=True, timeout=180, check=False)
            if result.returncode:
                message = (result.stderr or result.stdout).strip()
                if "VOICE_UNAVAILABLE" in message:
                    raise PermanentAudioError("VOICE_UNAVAILABLE", f"no installed {language} voice matches {voice}")
                raise RuntimeError("Windows SAPI failed: " + message[-300:])
            if not output.is_file() or not output.stat().st_size:
                raise RuntimeError("Windows SAPI produced no audio")
            with wave.open(str(output), "rb") as stream:
                duration_ms = int(stream.getnframes() * 1000 / max(1, stream.getframerate()))
            return {"path": str(output), "mime_type": "audio/wav", "duration_ms": duration_ms,
                    "size_bytes": output.stat().st_size, "resolved_voice": result.stdout.strip()}
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            source_path.unlink(missing_ok=True)


VOICE_CATALOG = {
    "edge-tts": (
        {"id": "newzi_clara", "name": "Clara", "description": "Voz feminina em português brasileiro",
         "language": "pt-BR", "gender": "female", "provider_voice": "pt-BR-ThalitaMultilingualNeural"},
        {"id": "newzi_lucas", "name": "Lucas", "description": "Voz masculina em português brasileiro",
         "language": "pt-BR", "gender": "male", "provider_voice": "pt-BR-AntonioNeural"},
        {"id": "newzi_sofia", "name": "Sofia", "description": "Outra voz feminina em português brasileiro",
         "language": "pt-BR", "gender": "female", "provider_voice": "pt-BR-FranciscaNeural"},
        {"id": "newzi_ava", "name": "Ava", "description": "English voice",
         "language": "en", "gender": "female", "provider_voice": "en-US-EmmaMultilingualNeural"},
    ),
    "windows-sapi": (
        {"id": "newzi_maria", "name": "Maria", "description": "Voz local do Windows em português brasileiro",
         "language": "pt-BR", "gender": "female", "provider_voice": "Maria"},
        {"id": "newzi_zira", "name": "Zira", "description": "Local Windows voice",
         "language": "en", "gender": "female", "provider_voice": "Zira"},
    ),
}
PREVIEW_TEXT = {
    "pt-BR": "Bom dia. Este é o seu briefing Newzi, com as histórias mais importantes selecionadas para você acompanhar o dia com clareza.",
    "en": "Good morning. This is your Newzi briefing, with the most important stories selected to help you follow the day clearly.",
}


class EdgeTTSProvider(TTSProvider):
    """Online neural voices exposed by the edge-tts client as MP3 audio."""
    name = "edge-tts"
    version = "7.2.7-rate-2"
    extension = ".mp3"
    _cached_voices = None
    _cache_checked_at = 0.0
    _last_voice_query_ok = False

    def list_voices(self):
        provider = type(self)
        if provider._cached_voices is not None and time.monotonic() - provider._cache_checked_at < 60:
            return provider._cached_voices
        try:
            import asyncio
            import edge_tts
            voices = asyncio.run(edge_tts.list_voices())
            provider._cached_voices = [item["ShortName"] for item in voices]
            provider._last_voice_query_ok = True
        except Exception:
            provider._cached_voices = [entry["provider_voice"] for entry in VOICE_CATALOG[self.name]]
            provider._last_voice_query_ok = False
        provider._cache_checked_at = time.monotonic()
        return provider._cached_voices

    def health_check(self):
        self.list_voices()
        return type(self)._last_voice_query_ok

    def capabilities(self):
        return {"language": ["pt-BR", "en"], "ssml": False, "speaking_rate": True}

    @staticmethod
    def _duration_ms(path):
        try:
            result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                     "-of", "default=nw=1:nk=1", str(path)], capture_output=True,
                                    text=True, timeout=30, check=True)
            return int(float(result.stdout.strip()) * 1000)
        except FileNotFoundError as exc:
            raise PermanentAudioError("AUDIO_TOOL_MISSING", "ffprobe is required for edge-tts audio") from exc

    def synthesize(self, text, voice, language, options=None):
        if voice not in self.list_voices():
            raise PermanentAudioError("VOICE_UNAVAILABLE", f"Edge voice unavailable: {voice}")
        if not text.strip():
            raise PermanentAudioError("EMPTY_SCRIPT", "cannot synthesize empty text")
        import asyncio
        import edge_tts
        directory = Path(os.environ.get("NEWS_AUDIO_TMP", str(BACKEND_DATA / "audio")))
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / ("tts_" + uuid.uuid4().hex + ".mp3")
        try:
            async def save_with_timeout():
                await asyncio.wait_for(edge_tts.Communicate(text, voice=voice, rate="-2%").save(str(output)),
                                       timeout=float(os.getenv("TTS_SEGMENT_TIMEOUT_SECONDS", "90")))
            asyncio.run(save_with_timeout())
            if not output.is_file() or not output.stat().st_size:
                raise RuntimeError("Edge TTS produced no audio")
            return {"path": str(output), "mime_type": "audio/mpeg", "duration_ms": self._duration_ms(output),
                    "size_bytes": output.stat().st_size, "resolved_voice": voice}
        except Exception:
            output.unlink(missing_ok=True)
            raise

    def synthesize_segments(self, segments, voice, language, options=None):
        parts = []
        timings = []
        directory = Path(os.environ.get("NEWS_AUDIO_TMP", str(BACKEND_DATA / "audio")))
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / ("tts_briefing_" + uuid.uuid4().hex + ".mp3")
        playlist = directory / ("tts_concat_" + uuid.uuid4().hex + ".txt")
        elapsed_ms = 0
        try:
            # A small bounded pool removes the old per-chapter serial network wait
            # while limiting load against the provider.
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, max(1, len(segments)))) as pool:
                futures=[pool.submit(self.synthesize, segment["text"], voice, language, options) for segment in segments]
                generated=[future.result(timeout=float(os.getenv("TTS_SEGMENT_TIMEOUT_SECONDS", "90"))+10) for future in futures]
            for segment, part in zip(segments, generated):
                parts.append(Path(part["path"]))
                duration = part["duration_ms"]
                timings.append((segment["id"], elapsed_ms, elapsed_ms + duration))
                elapsed_ms += duration
            playlist.write_text("".join("file '" + part.resolve().as_posix().replace("'", "'\\''") + "'\n"
                                        for part in parts), encoding="utf-8")
            try:
                subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "concat", "-safe", "0",
                                "-i", str(playlist), "-c", "copy", "-y", str(output)],
                               capture_output=True, text=True, timeout=120, check=True)
            except FileNotFoundError as exc:
                raise PermanentAudioError("AUDIO_TOOL_MISSING", "ffmpeg is required for edge-tts audio") from exc
            if not output.is_file() or not output.stat().st_size:
                raise RuntimeError("ffmpeg produced no combined audio")
            return {"path": str(output), "mime_type": "audio/mpeg", "duration_ms": self._duration_ms(output),
                    "size_bytes": output.stat().st_size, "segment_timings": timings, "resolved_voice": voice}
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            playlist.unlink(missing_ok=True)
            for part in parts:
                part.unlink(missing_ok=True)


class UnavailableTTSProvider(TTSProvider):
    def __init__(self, name):
        self.name = name

    def synthesize(self, text, voice, language, options=None):
        raise PermanentAudioError("TTS_PROVIDER_UNSUPPORTED", f"unsupported TTS_PROVIDER: {self.name}")


class OllamaTranslator:
    """Translate source-language fallback text locally for spoken output."""
    def translate(self, fields, language):
        import httpx
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        prompt = ("Translate each JSON string into " + language + ". Preserve every fact, number, "
                  "name and uncertainty. Do not add information. Return only a JSON object with "
                  "the same keys. Input: " + json.dumps(fields, ensure_ascii=False))
        response = httpx.post(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/generate",
                              json={"model": model, "prompt": prompt, "stream": False, "format": "json"}, timeout=60)
        response.raise_for_status()
        translated = json.loads(response.json()["response"])
        if not isinstance(translated, dict) or any(not isinstance(translated.get(key), str) for key in fields):
            raise PermanentAudioError("TRANSLATION_INVALID", "translation did not preserve the script fields")
        for key, original in fields.items():
            digits = lambda value: re.findall(r"\d+(?:[.,]\d+)*", value)
            if digits(original) != digits(translated[key]):
                raise PermanentAudioError("TRANSLATION_INVALID", "translation changed a numeric fact")
        return translated


def spoken_text(value):
    value = re.sub(r"https?://\S+|www\.\S+", "", str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"(?m)^\s{0,3}(?:[-*#>]+|\d+[.)])\s*", "", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = value.replace(" | ", ". ")
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    magnitude = r"(?:milh(?:ão|ões)|bilh(?:ão|ões))"
    value = re.sub(r"\bR\$\s*(\d[\d.,]*(?:\s+" + magnitude + r")?)", r"\1 de reais", value)
    value = re.sub(r"\bUS\$\s*(\d[\d.,]*(?:\s+" + magnitude + r")?)", r"\1 de dólares", value)
    value = re.sub(r"(\d[\d.,]*)%", r"\1 por cento", value)
    return re.sub(r"\s+", " ", value).strip(" .")


def spoken_excerpt(value, max_words=55, max_sentences=2):
    """Keep complete opening sentences when possible, without inventing a summary."""
    sentences = re.split(r"(?<=[.!?])\s+", spoken_text(value))
    chosen = []
    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue
        if len(chosen) >= max_sentences or sum(len(part.split()) for part in chosen) + len(words) > max_words:
            break
        chosen.append(sentence)
    if chosen:
        return " ".join(chosen).strip(" .")
    return ""


class AudioScriptComposer:
    def __init__(self, translator=None):
        # Translation enrichment may be injected, but it is not on the critical
        # delivery path: a missing Ollama service must not block daily audio.
        self.translator = translator
        self.translation_warnings = []

    def compose(self, edition, language):
        if edition["status"] != "READY" or not edition.get("items"):
            raise PermanentAudioError("EDITION_NOT_READY", "audio requires a ready edition")
        if language != edition["language"]:
            raise PermanentAudioError("LANGUAGE_MISMATCH", "audio language must match edition language")
        self.translation_warnings=[]
        portuguese = language.lower().startswith("pt")
        intro = ("Olá. Este é o seu briefing Newzi. Vamos aos destaques."
                 if portuguese else "Hello. This is your Newzi briefing. Here are the highlights.")
        segments = [("INTRO", None, intro)]
        previous = None
        recent_transitions = []
        items = edition["items"]
        for index, item in enumerate(items):
            fields = {"headline": item.get("headline") or "", "summary": item.get("summary") or "",
                      "why_it_matters": item.get("why_it_matters") or ""}
            if self.translator and "SOURCE_LANGUAGE_FALLBACK" in (item.get("warnings") or []):
                try:
                    translated=self.translator.translate(fields, language)
                    digits=lambda value:re.findall(r"\d+(?:[.,]\d+)*",value)
                    if not isinstance(translated,dict) or any(not isinstance(translated.get(key),str) for key in fields):
                        raise PermanentAudioError("TRANSLATION_INVALID","translation did not preserve the script fields")
                    if any(digits(fields[key])!=digits(translated[key]) for key in fields):
                        raise PermanentAudioError("TRANSLATION_INVALID","translation changed a numeric fact")
                    fields=translated
                except Exception as exc:
                    # Translation is optional enrichment; unsafe output or a missing
                    # local translator must not block otherwise valid audio.
                    code=exc.code if isinstance(exc,PermanentAudioError) else "TRANSLATION_UNAVAILABLE"
                    self.translation_warnings.append({"item_id":item.get("id"),"code":code})
            headline = spoken_text(fields["headline"])
            summary = spoken_excerpt(fields["summary"])
            reason = spoken_excerpt(fields["why_it_matters"], max_words=25, max_sentences=1)
            if not headline and not summary:
                continue
            narrative = headline or summary
            if summary and summary.casefold() != headline.casefold() and not summary.casefold().startswith(headline.casefold()):
                narrative += (" " if narrative.endswith((".", "?", "!")) else ". ") + summary
            if reason and len(reason.split()) >= 8 and reason.casefold() not in narrative.casefold():
                narrative += (" " if narrative.endswith((".", "?", "!")) else ". ") + reason
            transition_kind, transition = self._transition(previous, item, index, len(items), recent_transitions, portuguese)
            if transition:
                recent_transitions.append((transition_kind, index))
                if narrative[:1] in {"O", "A"} and narrative[1:2] == " ":
                    narrative = narrative[0].lower() + narrative[1:]
                narrative = transition + narrative
            narrative = narrative.rstrip(" .")
            segments.append(("ITEM", item["id"], narrative if narrative.endswith(("?", "!")) else narrative + "."))
            previous = item
        segments.append(("OUTRO", None, "Esse foi o briefing Newzi. Até a próxima."
                         if portuguese else "That was your Newzi briefing. See you next time."))
        return segments

    @staticmethod
    def _transition(previous, item, index, count, recent, portuguese):
        if previous is None:
            return None, ""
        if index == count - 1 and count >= 4:
            return "closing", "Para fechar, " if portuguese else "Finally, "
        stop = {"para", "sobre", "após", "entre", "mais", "como", "pela", "pelo", "com", "sem",
                "ainda", "novo", "nova", "hoje", "brasil", "brasileiro", "brasileira", "the", "and",
                "with", "from", "after", "new", "says", "news"}
        def keywords(value):
            return {word for word in re.findall(r"[^\W\d_]{4,}", spoken_text(value).casefold()) if word not in stop}
        shared = keywords(previous.get("headline")) & keywords(item.get("headline"))
        related = (previous.get("primary_taxonomy_id") == item.get("primary_taxonomy_id")
                   and len(shared) >= 1)
        if related and not any(kind == "related" and index - position <= 2 for kind, position in recent):
            return "related", "Ainda nesse tema, " if portuguese else "Still on that subject, "
        if index % 4 == 3:
            if portuguese:
                return "shift", ("Em outra frente, ", "Entre outros destaques, ", "Mudando de assunto, ")[(index // 4) % 3]
            return "shift", ("In another development, ", "Among other highlights, ", "On another subject, ")[(index // 4) % 3]
        return None, ""


class AudioStorage:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("AUDIO_STORAGE_ROOT", str(BACKEND_DATA / "audio"))).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def move_into_storage(self, source, checksum):
        destination = self.root / (checksum + Path(source).suffix.lower())
        reusable=False
        if destination.is_file():
            digest=hashlib.sha256()
            with destination.open("rb") as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
            reusable=digest.hexdigest()==checksum
        if Path(source).resolve() != destination and not reusable:
            temporary=destination.with_name(destination.name+"."+uuid.uuid4().hex+".tmp")
            try:
                shutil.copyfile(source, temporary)
                with temporary.open("r+b") as stream: stream.flush(); os.fsync(stream.fileno())
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        Path(source).unlink(missing_ok=True)
        return str(destination)

    def resolve(self, value):
        path = Path(value).resolve()
        return path if self.root in path.parents and path.is_file() else None


def ensure_audio_schema(repo):
    repo.db.executescript("""
    CREATE TABLE IF NOT EXISTS audio_scripts(id TEXT PRIMARY KEY,edition_id TEXT NOT NULL,language TEXT NOT NULL,target_duration_seconds INTEGER NOT NULL,estimated_duration_seconds INTEGER NOT NULL,script_version TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(edition_id,language,script_version));
    CREATE TABLE IF NOT EXISTS audio_script_segments(id TEXT PRIMARY KEY,audio_script_id TEXT NOT NULL,position INTEGER NOT NULL,type TEXT NOT NULL,briefing_item_id TEXT,text TEXT NOT NULL,estimated_duration_ms INTEGER NOT NULL,segment_start_ms INTEGER,segment_end_ms INTEGER,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audio_artifacts(id TEXT PRIMARY KEY,audio_script_id TEXT NOT NULL,status TEXT NOT NULL,provider TEXT NOT NULL,voice TEXT NOT NULL,language TEXT NOT NULL,mime_type TEXT,storage_path TEXT,duration_ms INTEGER,size_bytes INTEGER,checksum TEXT,created_at TEXT NOT NULL,error_message TEXT,resolved_voice TEXT,UNIQUE(audio_script_id,provider,voice,language));
    CREATE TABLE IF NOT EXISTS audio_generation_jobs(id TEXT PRIMARY KEY,edition_id TEXT NOT NULL,language TEXT NOT NULL,voice TEXT NOT NULL,script_version TEXT NOT NULL,status TEXT NOT NULL,attempt_count INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,error_message TEXT,UNIQUE(edition_id,language,voice,script_version));
    CREATE TABLE IF NOT EXISTS audio_events(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT NOT NULL,edition_id TEXT,artifact_id TEXT,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audio_artifact_segments(artifact_id TEXT NOT NULL,segment_id TEXT NOT NULL,segment_start_ms INTEGER NOT NULL,segment_end_ms INTEGER NOT NULL,PRIMARY KEY(artifact_id,segment_id));
    CREATE TABLE IF NOT EXISTS audio_job_phases(id INTEGER PRIMARY KEY AUTOINCREMENT,audio_job_id TEXT NOT NULL,phase TEXT NOT NULL,duration_ms INTEGER NOT NULL,started_at TEXT NOT NULL,finished_at TEXT NOT NULL,status TEXT NOT NULL,error_code TEXT,UNIQUE(audio_job_id,phase));
    """)
    columns = {row[1] for row in repo.db.execute("PRAGMA table_info(audio_generation_jobs)")}
    for name in ("next_retry_at", "error_code"):
        if name not in columns:
            repo.db.execute(f"ALTER TABLE audio_generation_jobs ADD COLUMN {name} TEXT")
    artifact_columns = {row[1] for row in repo.db.execute("PRAGMA table_info(audio_artifacts)")}
    if "resolved_voice" not in artifact_columns:
        repo.db.execute("ALTER TABLE audio_artifacts ADD COLUMN resolved_voice TEXT")
    script_columns={row[1] for row in repo.db.execute("PRAGMA table_info(audio_scripts)")}
    if "script_hash" not in script_columns:
        repo.db.execute("ALTER TABLE audio_scripts ADD COLUMN script_hash TEXT")
    job_columns={row[1] for row in repo.db.execute("PRAGMA table_info(audio_generation_jobs)")}
    for name, declaration in (("stage","TEXT"),("updated_at","TEXT")):
        if name not in job_columns: repo.db.execute(f"ALTER TABLE audio_generation_jobs ADD COLUMN {name} {declaration}")
    repo.db.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(3,?)", (now_iso(),))
    repo.db.commit()


def _duration_ms(text):
    return max(1000, int(len(text.split()) / 2.4 * 1000))


class AudioService:
    def __init__(self, repo, provider=None, storage=None, voice=None, script_version="v3", composer=None):
        ensure_audio_schema(repo)
        self.repo = repo
        provider_name = os.getenv("TTS_PROVIDER")
        if not provider_name:
            try:
                import edge_tts  # noqa: F401
                provider_name = "edge-tts"
            except ImportError:
                provider_name = "windows-sapi" if os.name == "nt" else "local-system"
        self.provider = provider or ({"local-system": LocalTTSProvider,
                                     "windows-sapi": WindowsSAPIProvider,
                                     "edge-tts": EdgeTTSProvider}.get(provider_name,
                                     lambda: UnavailableTTSProvider(provider_name))())
        self.storage = storage or AudioStorage()
        self.voice = voice or os.getenv("TTS_VOICE", "auto")
        self.narration_version = script_version
        # Preserve the existing durable job key while keeping narration identity
        # independent from the TTS provider/version.
        self.tts_version = f"{script_version}:{self.provider.name}:{self.provider.version}"
        self.script_version = self.tts_version
        self.composer = composer or AudioScriptComposer()

    def available_voices(self, language="pt-BR"):
        candidates = VOICE_CATALOG.get(self.provider.name, ())
        installed = self.provider.list_voices()
        return [voice for voice in candidates if voice["language"] == language and
                any(voice["provider_voice"].casefold() in name.casefold() for name in installed)]

    def default_voice(self, language="pt-BR"):
        voices = self.available_voices(language)
        return voices[0]["id"] if voices else self.voice if self.provider.name not in VOICE_CATALOG else None

    def effective_voice(self, preferred=None, language="pt-BR"):
        available = {voice["id"] for voice in self.available_voices(language)}
        return preferred if preferred in available else self.default_voice(language)

    def _provider_voice(self, voice_id, language):
        profile = next((voice for voice in self.available_voices(language) if voice["id"] == voice_id), None)
        if profile:
            return profile["provider_voice"]
        if self.provider.name not in VOICE_CATALOG:
            return voice_id
        raise PermanentAudioError("VOICE_UNAVAILABLE", f"voice unavailable: {voice_id}")

    def voice_catalog(self, language="pt-BR"):
        voices = []
        for profile in self.available_voices(language):
            public = {key: value for key, value in profile.items() if key != "provider_voice"}
            public["preview_url"] = f"/api/v1/me/audio/voices/{profile['id']}/preview?v={self.provider.version}"
            voices.append(public)
        return {"voices": voices, "default_voice_id": self.default_voice(language)}

    def voice_preview(self, voice_id, language="pt-BR"):
        provider_voice = self._provider_voice(voice_id, language)
        sample = PREVIEW_TEXT[language]
        digest = hashlib.sha256(f"{self.provider.name}:{self.provider.version}:{voice_id}:{sample}".encode()).hexdigest()
        destination = self.storage.root / "previews" / (digest + self.provider.extension)
        if destination.is_file() and destination.stat().st_size:
            self._event("voice_preview_cache_hit", metadata={"voice_id": voice_id})
            return destination
        result = self.provider.synthesize(sample, provider_voice, language)
        source = Path(result["path"])
        if not source.is_file() or not source.stat().st_size:
            raise RuntimeError("TTS produced no voice preview")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.stem + "_" + uuid.uuid4().hex + destination.suffix)
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
            source.unlink(missing_ok=True)
        self._event("voice_preview_created", metadata={"voice_id": voice_id})
        return destination

    def _event(self, event_type, edition_id=None, artifact_id=None, metadata=None):
        self.repo.db.execute("INSERT INTO audio_events(event_type,edition_id,artifact_id,metadata_json,created_at) VALUES(?,?,?,?,?)",
                             (event_type, edition_id, artifact_id, json.dumps(metadata or {}, ensure_ascii=False), now_iso()))
        self.repo.db.commit()

    def _edition(self, edition_id):
        from .scheduling import serialize_edition
        return serialize_edition(self.repo, edition_id)

    def serialize_script(self, script_id):
        row = self.repo.db.execute("SELECT * FROM audio_scripts WHERE id=?", (script_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["segments"] = [dict(value) for value in self.repo.db.execute(
            "SELECT * FROM audio_script_segments WHERE audio_script_id=? ORDER BY position", (script_id,))]
        return out

    def build_script(self, edition_id, language=None, target_duration_seconds=300):
        edition = self._edition(edition_id)
        if not edition:
            raise PermanentAudioError("EDITION_NOT_FOUND", "edition not found")
        language = language or edition["language"]
        existing = self.repo.db.execute(
            "SELECT id FROM audio_scripts WHERE edition_id=? AND language=? AND (script_version=? OR script_version LIKE ?) ORDER BY CASE WHEN script_version=? THEN 0 ELSE 1 END,created_at DESC LIMIT 1",
            (edition_id, language, self.narration_version,self.narration_version+":%",self.narration_version)).fetchone()
        if existing:
            return self.serialize_script(existing["id"]), False
        segments = self.composer.compose(edition, language)
        sid, created = "audio_script_" + uuid.uuid4().hex, now_iso()
        estimated = sum(_duration_ms(text) for _, _, text in segments)
        script_hash=hashlib.sha256(json.dumps(segments,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        self.repo.db.execute("INSERT INTO audio_scripts(id,edition_id,language,target_duration_seconds,estimated_duration_seconds,script_version,status,created_at,script_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                             (sid, edition_id, language, target_duration_seconds, estimated // 1000,
                              self.narration_version, "READY", created,script_hash))
        self.repo.db.executemany("INSERT INTO audio_script_segments VALUES(?,?,?,?,?,?,?,?,?,?)",
                                 [("audio_segment_" + uuid.uuid4().hex, sid, pos, kind, item_id,
                                   text, _duration_ms(text), None, None, created)
                                  for pos, (kind, item_id, text) in enumerate(segments, 1)])
        self.repo.db.commit()
        self._event("audio_script_created", edition_id, metadata={"script_chars": sum(len(x[2]) for x in segments),
                                                          "script_generation_mode": "deterministic_editorial",
                                                          "script_version": self.script_version,
                                                          "translation_fallbacks":list(getattr(self.composer,"translation_warnings",[]))})
        return self.serialize_script(sid), True

    def request(self, edition_id, language=None, voice=None):
        edition = self._edition(edition_id)
        if not edition or edition["status"] != "READY":
            raise PermanentAudioError("EDITION_NOT_READY", "edition is not ready")
        language = language or edition["language"]
        if language != edition["language"]:
            raise PermanentAudioError("LANGUAGE_MISMATCH", "audio language must match edition language")
        requested_voice=voice
        voice = self.effective_voice(voice, language)
        if not voice:
            raise PermanentAudioError("VOICE_UNAVAILABLE", f"no {language} TTS voice available")
        script,_=self.build_script(edition_id,language)
        existing = self.audio_for_edition(edition_id, language, voice)
        recoverable_errors={"AUDIO_FILE_MISSING","AUDIO_METADATA_INVALID","TRANSLATION_INVALID"}
        if existing["status"] in ("READY", "PENDING", "GENERATING") or (existing["status"]=="FAILED" and existing.get("error_code") not in recoverable_errors):
            self._event("audio_cache_hit", edition_id, metadata={"status": existing["status"], "tts_voice_id": voice})
            return existing
        if existing.get("error_code") in recoverable_errors:
            script_row=self.repo.db.execute("SELECT id FROM audio_scripts WHERE edition_id=? AND language=? AND (script_version=? OR script_version LIKE ?) ORDER BY CASE WHEN script_version=? THEN 0 ELSE 1 END,created_at DESC LIMIT 1",(edition_id,language,self.narration_version,self.narration_version+":%",self.narration_version)).fetchone()
            if script_row and existing.get("error_code") in {"AUDIO_FILE_MISSING","AUDIO_METADATA_INVALID"}:
                self.repo.db.execute("UPDATE audio_artifacts SET status='FAILED',error_message=? WHERE audio_script_id=? AND provider=? AND voice=? AND language=?",(existing["error_code"],script_row["id"],self.provider.name,voice,language))
                self.repo.db.execute("UPDATE user_briefing_deliveries SET audio_artifact_id=NULL,active_voice_id=NULL,status='AUDIO_QUEUED',audio_status='PENDING' WHERE edition_id=? AND selected_voice_id=? AND active_voice_id=?",(edition_id,voice,voice))
            self.repo.db.execute("UPDATE audio_generation_jobs SET status='PENDING',stage='QUEUED',attempt_count=0,max_attempts=3,next_retry_at=NULL,finished_at=NULL,error_code=NULL,error_message=NULL,updated_at=? WHERE edition_id=? AND language=? AND voice=? AND script_version=?",(now_iso(),edition_id,language,voice,self.script_version)); self.repo.db.commit()
            repaired=self.repo.db.execute("SELECT id FROM audio_generation_jobs WHERE edition_id=? AND language=? AND voice=? AND script_version=?",(edition_id,language,voice,self.script_version)).fetchone()
            if repaired:
                self._event("audio_job_requeued_corrupt_artifact",edition_id,metadata={"tts_voice_id":voice,"reason":existing["error_code"]})
                return self.audio_for_edition(edition_id,language,voice)
        self.repo.db.execute("""INSERT OR IGNORE INTO audio_generation_jobs
            (id,edition_id,language,voice,script_version,status,attempt_count,max_attempts,created_at,stage,updated_at)
            VALUES(?,?,?,?,?,'PENDING',0,3,?,'QUEUED',?)""",
            ("audio_job_" + uuid.uuid4().hex, edition_id, language, voice, self.script_version, now_iso(),now_iso()))
        self.repo.db.commit()
        self._event("audio_cache_miss", edition_id, metadata={"tts_voice_id": voice})
        self._event("audio_job_created", edition_id, metadata={"provider": self.provider.name, "tts_voice_id": voice})
        fallback_reason="VOICE_UNAVAILABLE" if requested_voice and requested_voice!=voice else None
        self.repo.db.execute("UPDATE user_briefing_deliveries SET script_id=?,selected_voice_id=?,voice_fallback_reason=?,generation_stage='AUDIO_QUEUED',generation_updated_at=?,status=CASE WHEN audio_artifact_id IS NOT NULL THEN 'READY' ELSE 'AUDIO_QUEUED' END,audio_status=CASE WHEN audio_artifact_id IS NOT NULL THEN 'READY' ELSE 'PENDING' END,generation_error_code=NULL,generation_error_message=NULL WHERE edition_id=? AND (selected_voice_id=? OR selected_voice_id IS NULL)",
                             (script["id"],voice,fallback_reason,now_iso(),edition_id,requested_voice))
        self.repo.db.commit()
        return self.audio_for_edition(edition_id, language, voice)

    def retry(self, edition_id, language=None, voice=None):
        """Retry only the existing edition/script/voice after a transient TTS failure."""
        edition=self._edition(edition_id)
        if not edition or edition["status"]!="READY":
            raise PermanentAudioError("EDITION_NOT_READY","edition is not ready")
        language=language or edition["language"]
        voice=self.effective_voice(voice,language)
        current=self.audio_for_edition(edition_id,language,voice)
        if current.get("status")!="FAILED":
            return current
        code=current.get("error_code") or "TTS_FAILED"
        if code in {"VOICE_UNAVAILABLE","LANGUAGE_MISMATCH","AUDIO_FORMAT_UNSUPPORTED","SCRIPT_INVALID"}:
            raise PermanentAudioError(code,"audio failure is not retryable; update the voice or configuration")
        now=now_iso()
        self.repo.db.execute("UPDATE audio_generation_jobs SET status='PENDING',stage='QUEUED',attempt_count=0,max_attempts=3,next_retry_at=NULL,finished_at=NULL,error_code=NULL,error_message=NULL,updated_at=? WHERE edition_id=? AND language=? AND voice=? AND status='FAILED'",(now,edition_id,language,voice))
        self.repo.db.commit()
        return self.request(edition_id,language,voice)

    def attach_variant_to_delivery(self, delivery_id, metadata):
        """Switch the delivery's active audio only after a validated artifact exists."""
        if metadata.get("status")!="READY" or not metadata.get("artifact_id") or int(metadata.get("duration_ms") or 0)<=0:
            self.repo.db.execute("UPDATE user_briefing_deliveries SET audio_status=?,generation_stage=?,generation_updated_at=?,generation_error_code=? WHERE id=?",
                (metadata.get("status","PENDING"),metadata.get("status","AUDIO_QUEUED"),now_iso(),metadata.get("error_code"),delivery_id))
            self.repo.db.commit(); return False
        artifact=self.repo.db.execute("SELECT * FROM audio_artifacts WHERE id=? AND status='READY' AND duration_ms>0 AND size_bytes>0",(metadata["artifact_id"],)).fetchone()
        if not artifact or int(artifact["size_bytes"] or 0)<128 or not self.storage.resolve(artifact["storage_path"]):
            return False
        self.repo.db.execute("""UPDATE user_briefing_deliveries SET status='READY',audio_status='READY',
            audio_artifact_id=?,active_voice_id=?,selected_voice_id=?,script_id=?,generation_stage='READY',
            generation_updated_at=?,generation_error_code=NULL,generation_error_message=NULL,delivered_at=? WHERE id=?""",
            (artifact["id"],artifact["voice"],artifact["voice"],artifact["audio_script_id"],now_iso(),now_iso(),delivery_id))
        self.repo.db.commit(); return True

    def queue_voice_for_delivery(self, delivery_id, voice, language):
        row=self.repo.db.execute("SELECT edition_id,audio_artifact_id FROM user_briefing_deliveries WHERE id=?",(delivery_id,)).fetchone()
        if not row: return {"status":"NOT_AVAILABLE"}
        current=self.repo.db.execute("SELECT voice FROM audio_artifacts WHERE id=? AND status='READY'",(row["audio_artifact_id"],)).fetchone() if row["audio_artifact_id"] else None
        self.repo.db.execute("UPDATE user_briefing_deliveries SET selected_voice_id=?,audio_status='PENDING',generation_stage='AUDIO_QUEUED',generation_started_at=COALESCE(generation_started_at,?),generation_updated_at=?,generation_error_code=NULL,generation_error_message=NULL WHERE id=?",
            (voice,now_iso(),now_iso(),delivery_id)); self.repo.db.commit()
        result=self.request(row["edition_id"],language,voice)
        if result.get("status")=="READY": self.attach_variant_to_delivery(delivery_id,result)
        else:
            self.repo.db.execute("UPDATE user_briefing_deliveries SET status=?,audio_status=?,generation_stage=?,generation_updated_at=? WHERE id=?",
                ("READY" if current else result.get("status","AUDIO_QUEUED"),result.get("status","PENDING"),result.get("status","AUDIO_QUEUED"),now_iso(),delivery_id)); self.repo.db.commit()
        return result

    def validate_audio(self, path, mime_type, reported_duration_ms):
        path=Path(path)
        if not path.is_file() or path.stat().st_size < 128:
            raise RuntimeError("AUDIO_VALIDATION_SIZE")
        suffix=path.suffix.lower()
        expected={".wav":"audio/wav",".mp3":"audio/mpeg",".m4a":"audio/mp4",".aac":"audio/aac"}
        if suffix not in expected or mime_type!=expected[suffix]: raise RuntimeError("AUDIO_VALIDATION_MIME")
        if suffix==".wav":
            with wave.open(str(path),"rb") as stream:
                duration=int(stream.getnframes()*1000/max(1,stream.getframerate()))
                if stream.getnframes()<=0 or duration<=0: raise RuntimeError("AUDIO_VALIDATION_DURATION")
        else:
            result=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)],capture_output=True,text=True,timeout=30,check=True)
            duration=int(float(result.stdout.strip())*1000)
            if duration<=0: raise RuntimeError("AUDIO_VALIDATION_DURATION")
        if int(reported_duration_ms or 0)<=0: raise RuntimeError("AUDIO_VALIDATION_DURATION")
        return duration

    def enqueue_ready_editions(self):
        count = 0
        linked=self.repo.db.execute("SELECT id,audio_artifact_id FROM user_briefing_deliveries WHERE status='READY' AND audio_artifact_id IS NOT NULL").fetchall()
        for delivery in linked:
            if self.audio_for_artifact(delivery["audio_artifact_id"]).get("status")!="READY":
                self.repo.db.execute("UPDATE user_briefing_deliveries SET status='AUDIO_QUEUED',audio_status='PENDING',active_voice_id=NULL,audio_artifact_id=NULL,generation_stage='AUDIO_QUEUED',generation_error_code='AUDIO_ARTIFACT_INVALID',generation_error_message='persisted audio is missing or invalid',generation_updated_at=? WHERE id=?",(now_iso(),delivery["id"]))
        self.repo.db.commit()
        rows=self.repo.db.execute("""SELECT DISTINCT d.edition_id,e.language,d.selected_voice_id,d.user_id,d.id FROM user_briefing_deliveries d
            JOIN briefing_editions e ON e.id=d.edition_id WHERE d.status IN ('AUDIO_QUEUED','PENDING','CONTENT_READY','READY')
            AND e.status='READY' AND (d.selected_voice_id IS NULL OR d.selected_voice_id<>COALESCE(d.active_voice_id,''))
            AND NOT EXISTS (SELECT 1 FROM audio_generation_jobs j WHERE j.edition_id=d.edition_id
                AND j.language=e.language AND j.voice=d.selected_voice_id AND j.script_version=?
                AND j.status IN ('PENDING','GENERATING'))""",(self.script_version,)).fetchall()
        for row in rows:
            preferred=row["selected_voice_id"]
            if not preferred: preferred=(self.repo.get_preferences(row["user_id"]) or {}).get("audio_voice_id")
            voice=self.effective_voice(preferred,row["language"])
            if not voice: continue
            if voice!=row["selected_voice_id"]:
                self.repo.db.execute("UPDATE user_briefing_deliveries SET selected_voice_id=?,voice_fallback_reason=?,audio_status='PENDING',generation_stage='AUDIO_QUEUED',generation_updated_at=? WHERE id=?",(voice,"VOICE_UNAVAILABLE" if preferred and preferred!=voice else None,now_iso(),row["id"])); self.repo.db.commit()
            result=self.request(row["edition_id"],row["language"],voice)
            if result.get("status")=="READY":
                targets=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE edition_id=? AND selected_voice_id=?",(row["edition_id"],result.get("voice"))).fetchall()
                for delivery in targets: self.attach_variant_to_delivery(delivery["id"],result)
            else: count += 1
        return count

    def _claim(self):
        stale = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        self.repo.db.execute("BEGIN IMMEDIATE")
        try:
            stale_jobs=self.repo.db.execute("SELECT edition_id,voice,attempt_count,max_attempts FROM audio_generation_jobs WHERE status='GENERATING' AND started_at<?",(stale,)).fetchall()
            self.repo.db.execute("""UPDATE audio_generation_jobs SET status='PENDING',stage='RETRY',updated_at=?,started_at=NULL,
                next_retry_at=NULL WHERE status='GENERATING' AND started_at<? AND attempt_count<max_attempts""", (now_iso(),stale))
            self.repo.db.execute("""UPDATE audio_generation_jobs SET status='FAILED',stage='FAILED_FINAL',error_code='WORKER_TIMEOUT',
                error_message='stale audio job exceeded worker timeout',updated_at=?,finished_at=? WHERE status='GENERATING' AND started_at<? AND attempt_count>=max_attempts""",
                (now_iso(),now_iso(), stale))
            for stale_job in stale_jobs:
                retry=stale_job["attempt_count"]<stale_job["max_attempts"]
                rows=self.repo.db.execute("SELECT id,audio_artifact_id FROM user_briefing_deliveries WHERE edition_id=? AND selected_voice_id=?",(stale_job["edition_id"],stale_job["voice"])).fetchall()
                for delivery in rows:
                    active=self.repo.db.execute("SELECT 1 FROM audio_artifacts WHERE id=? AND status='READY' AND duration_ms>0",(delivery["audio_artifact_id"],)).fetchone() if delivery["audio_artifact_id"] else None
                    self.repo.db.execute("UPDATE user_briefing_deliveries SET status=?,audio_status=?,generation_stage=?,generation_updated_at=?,generation_error_code=?,generation_error_message=? WHERE id=?",
                        ("READY" if active else ("AUDIO_QUEUED" if retry else "FAILED"),"READY" if active else ("PENDING" if retry else "FAILED"),"AUDIO_QUEUED" if retry else "FAILED_FINAL",now_iso(),"WORKER_TIMEOUT",None if retry else "audio job exceeded worker timeout",delivery["id"]))
            job = self.repo.db.execute("""SELECT * FROM audio_generation_jobs WHERE status='PENDING'
                AND script_version=? AND (next_retry_at IS NULL OR next_retry_at<=?)
                ORDER BY created_at LIMIT 1""", (self.script_version, now_iso())).fetchone()
            if not job:
                self.repo.db.commit()
                return None
            self.repo.db.execute("UPDATE audio_generation_jobs SET status='GENERATING',stage='SCRIPT',updated_at=?,started_at=?,attempt_count=attempt_count+1 WHERE id=?",
                                 (now_iso(),now_iso(), job["id"]))
            self._update_delivery_stage(job["edition_id"],job["voice"],"GENERATING","SCRIPT")
            self.repo.db.commit()
            return dict(self.repo.db.execute("SELECT * FROM audio_generation_jobs WHERE id=?",(job["id"],)).fetchone())
        except Exception:
            self.repo.db.rollback()
            raise

    def generate_pending(self):
        job = self._claim()
        if not job:
            return {"jobs_claimed": 0, "jobs_completed": 0, "jobs_failed": 0, "jobs_retried": 0}
        started = time.monotonic()
        phase_started=started
        queued=datetime.fromisoformat(job["created_at"])
        claimed=datetime.fromisoformat(job["started_at"])
        queue_ms=max(0,int((claimed-queued).total_seconds()*1000))
        self.repo.db.execute("INSERT OR REPLACE INTO audio_job_phases(audio_job_id,phase,duration_ms,started_at,finished_at,status) VALUES(?,?,?,?,?,'READY')",
            (job["id"],"QUEUE_WAIT",queue_ms,job["created_at"],job["started_at"])); self.repo.db.commit()
        self._event("audio_generation_started", job["edition_id"], metadata={"provider": self.provider.name})
        try:
            script, _ = self.build_script(job["edition_id"], job["language"])
            self._record_phase(job["id"],"SCRIPT",phase_started)
            provider_voice = self._provider_voice(job["voice"], job["language"])
            self.repo.db.execute("UPDATE audio_generation_jobs SET stage='TTS',updated_at=? WHERE id=?",(now_iso(),job["id"])); self._update_delivery_stage(job["edition_id"],job["voice"],"GENERATING","TTS"); self.repo.db.commit()
            phase_started=time.monotonic()
            result = self.provider.synthesize_segments(script["segments"], provider_voice, job["language"],
                                                       TTSOptions(target_duration_seconds=script["target_duration_seconds"]))
            path = Path(result["path"])
            self._record_phase(job["id"],"TTS",phase_started)
            self.repo.db.execute("UPDATE audio_generation_jobs SET stage='VALIDATING',updated_at=? WHERE id=?",(now_iso(),job["id"])); self._update_delivery_stage(job["edition_id"],job["voice"],"VALIDATING","VALIDATING"); self.repo.db.commit()
            phase_started=time.monotonic()
            duration_ms=self.validate_audio(path,result.get("mime_type"),result.get("duration_ms"))
            self._record_phase(job["id"],"VALIDATION",phase_started)
            phase_started=time.monotonic()
            digest=hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
            checksum = digest.hexdigest()
            stored = self.storage.move_into_storage(path, checksum)
            self._record_phase(job["id"],"STORAGE",phase_started)
            if not self.storage.resolve(stored): raise RuntimeError("AUDIO_STORAGE_VALIDATION")
            artifact_id = "audio_artifact_" + uuid.uuid4().hex
            self.repo.db.execute("BEGIN IMMEDIATE")
            self.repo.db.execute("""INSERT OR REPLACE INTO audio_artifacts
                (id,audio_script_id,status,provider,voice,language,mime_type,storage_path,duration_ms,
                 size_bytes,checksum,created_at,error_message,resolved_voice) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (artifact_id, script["id"], "READY", self.provider.name, job["voice"], job["language"],
                 result.get("mime_type", "audio/wav"), stored, duration_ms,
                 Path(stored).stat().st_size, checksum, now_iso(), None, result.get("resolved_voice")))
            self.repo.db.executemany("""INSERT INTO audio_artifact_segments
                (artifact_id,segment_id,segment_start_ms,segment_end_ms) VALUES(?,?,?,?)""",
                [(artifact_id, segment_id, start_ms, end_ms)
                 for segment_id, start_ms, end_ms in result.get("segment_timings", [])])
            self.repo.db.execute("UPDATE audio_generation_jobs SET status='READY',stage='READY',finished_at=?,updated_at=?,error_code=NULL,error_message=NULL WHERE id=?",
                                 (now_iso(),now_iso(), job["id"]))
            deliveries=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE edition_id=? AND selected_voice_id=?",(job["edition_id"],job["voice"])).fetchall()
            for delivery in deliveries:
                self.repo.db.execute("""UPDATE user_briefing_deliveries SET status='READY',audio_status='READY',
                    audio_artifact_id=?,active_voice_id=?,script_id=?,generation_stage='READY',generation_updated_at=?,
                    generation_error_code=NULL,generation_error_message=NULL,delivered_at=? WHERE id=?""",
                    (artifact_id,job["voice"],script["id"],now_iso(),now_iso(),delivery["id"]))
            self.repo.db.commit()
            self._record_phase(job["id"],"TOTAL",started)
            self._event("audio_generation_completed", job["edition_id"], artifact_id,
                        {"duration_ms": duration_ms, "file_size": Path(stored).stat().st_size,
                         "latency_ms": int((time.monotonic() - started) * 1000), "provider": self.provider.name,
                         "tts_voice_id": job["voice"], "script_version": self.script_version})
            try:
                from .notifications import NotificationService
                NotificationService(self.repo).enqueue_ready()
            except Exception:
                import logging
                logging.getLogger(__name__).exception("notification enqueue failed after persisted audio READY")
            return {"jobs_claimed": 1, "jobs_completed": 1, "jobs_failed": 0, "jobs_retried": 0, "artifact_id": artifact_id}
        except Exception as exc:
            permanent = isinstance(exc, PermanentAudioError)
            retry = not permanent and job["attempt_count"] < job["max_attempts"]
            status = "PENDING" if retry else "FAILED"
            delay = (datetime.now(timezone.utc) + timedelta(minutes=2 ** job["attempt_count"])).isoformat() if retry else None
            code = exc.code if permanent else "TTS_TRANSIENT" if retry else "TTS_FAILED"
            self.repo.db.execute("""UPDATE audio_generation_jobs SET status=?,stage=?,updated_at=?,next_retry_at=?,finished_at=?,
                error_code=?,error_message=? WHERE id=?""",
                (status,"RETRY" if retry else "FAILED_FINAL",now_iso(),delay,None if retry else now_iso(),code,str(exc)[:500],job["id"]))
            deliveries=self.repo.db.execute("SELECT id,audio_artifact_id FROM user_briefing_deliveries WHERE edition_id=? AND selected_voice_id=?",(job["edition_id"],job["voice"])).fetchall()
            for delivery in deliveries:
                active=self.repo.db.execute("SELECT 1 FROM audio_artifacts WHERE id=? AND status='READY' AND duration_ms>0",(delivery["audio_artifact_id"],)).fetchone() if delivery["audio_artifact_id"] else None
                self.repo.db.execute("UPDATE user_briefing_deliveries SET status=?,audio_status=?,generation_stage=?,generation_updated_at=?,generation_error_code=?,generation_error_message=? WHERE id=?",
                    ("READY" if active else ("AUDIO_QUEUED" if retry else "FAILED"),"READY" if active else status,"AUDIO_QUEUED" if retry else "FAILED_FINAL",now_iso(),code,str(exc)[:500],delivery["id"]))
            self.repo.db.commit()
            self._record_phase(job["id"],"TOTAL",started,"RETRY" if retry else "FAILED",code)
            self._event("audio_generation_failed", job["edition_id"], metadata={"provider": self.provider.name,
                        "error_code": code, "retry": retry, "latency_ms": int((time.monotonic() - started) * 1000)})
            return {"jobs_claimed": 1, "jobs_completed": 0, "jobs_failed": 0 if retry else 1,
                    "jobs_retried": 1 if retry else 0}

    def _record_phase(self, job_id, phase, started, status="READY", error_code=None):
        finished=now_iso(); duration=max(0,int((time.monotonic()-started)*1000))
        self.repo.db.execute("INSERT OR REPLACE INTO audio_job_phases(audio_job_id,phase,duration_ms,started_at,finished_at,status,error_code) VALUES(?,?,?,?,?,?,?)",
                             (job_id,phase,duration,finished,finished,status,error_code)); self.repo.db.commit()

    def _update_delivery_stage(self, edition_id, voice, audio_status, stage, error_code=None, error_message=None):
        self.repo.db.execute("""UPDATE user_briefing_deliveries SET audio_status=?,generation_stage=?,generation_updated_at=?,
            generation_error_code=?,generation_error_message=?,status=CASE WHEN audio_artifact_id IS NOT NULL THEN 'READY' ELSE 'AUDIO_QUEUED' END
            WHERE edition_id=? AND selected_voice_id=?""",(audio_status,stage,now_iso(),error_code,error_message,edition_id,voice))

    def run_forever(self, interval_seconds=10):
        try:
            while True:
                self.enqueue_ready_editions()
                generated=self.generate_pending()
                from .notifications import NotificationService
                notifications=NotificationService(self.repo)
                notifications.enqueue_ready(); notifications.run_once()
                if not generated["jobs_claimed"]:
                    time.sleep(interval_seconds)
        except KeyboardInterrupt:
            return

    def audio_for_edition(self, edition_id, language=None, voice=None):
        edition = self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=?", (edition_id,)).fetchone()
        if not edition:
            return {"status": "NOT_AVAILABLE"}
        language = language or edition["language"]
        voice = voice or self.default_voice(language)
        if not voice:
            return {"status": "NOT_AVAILABLE", "edition_id": edition_id, "language": language}
        script = self.repo.db.execute("SELECT id FROM audio_scripts WHERE edition_id=? AND language=? AND (script_version=? OR script_version LIKE ?) ORDER BY CASE WHEN script_version=? THEN 0 ELSE 1 END,created_at DESC LIMIT 1",
                                      (edition_id, language, self.narration_version,self.narration_version+":%",self.narration_version)).fetchone()
        if script:
            row = self.repo.db.execute("""SELECT * FROM audio_artifacts WHERE audio_script_id=?
                AND provider=? AND voice=? AND language=? AND status='READY'""",
                (script["id"], self.provider.name, voice, language)).fetchone()
            if row:
                if not self.storage.resolve(row["storage_path"]):
                    return {"status": "FAILED", "error_code": "AUDIO_FILE_MISSING"}
                if int(row["duration_ms"] or 0)<=0 or int(row["size_bytes"] or 0)<128:
                    return {"status":"FAILED","error_code":"AUDIO_METADATA_INVALID"}
                return {"status": "READY", "edition_id": edition_id, "script_id": script["id"], "artifact_id":row["id"],
                        "duration_ms": row["duration_ms"], "size_bytes": row["size_bytes"],
                        "mime_type": row["mime_type"], "language": language, "voice": voice,
                        "provider": self.provider.name, "generated_at": row["created_at"],
                        "resolved_voice": row["resolved_voice"],
                        "asset_version": row["checksum"][:12],
                        "segments": [{"id": segment["id"], "position": segment["position"],
                                      "type": segment["type"], "briefing_item_id": segment["briefing_item_id"],
                                      "script_text": segment["text"],
                                      "segment_start_ms": segment["segment_start_ms"],
                                      "segment_end_ms": segment["segment_end_ms"]}
                                     for segment in self.repo.db.execute("""SELECT s.id,s.position,s.type,s.briefing_item_id,s.text,
                                        COALESCE(t.segment_start_ms,s.segment_start_ms) AS segment_start_ms,
                                        COALESCE(t.segment_end_ms,s.segment_end_ms) AS segment_end_ms
                                        FROM audio_script_segments s LEFT JOIN audio_artifact_segments t
                                        ON t.segment_id=s.id AND t.artifact_id=?
                                        WHERE s.audio_script_id=? ORDER BY s.position""",
                                        (row["id"], script["id"]))]}
        job = self.repo.db.execute("""SELECT status,error_code,stage,attempt_count,max_attempts,started_at,updated_at FROM audio_generation_jobs
            WHERE edition_id=? AND language=? AND voice=? AND script_version=?""",
            (edition_id, language, voice, self.script_version)).fetchone()
        return {"status": job["status"] if job else "NOT_AVAILABLE", "edition_id": edition_id,
                "language": language,
                "error_code": job["error_code"] if job and job["status"] == "FAILED" else None,
                "generation_stage":job["stage"] if job else None,
                "attempt_count":job["attempt_count"] if job else 0,
                "max_attempts":job["max_attempts"] if job else 3,
                "generation_started_at":job["started_at"] if job else None,
                "generation_updated_at":job["updated_at"] if job else None}

    def audio_for_artifact(self, artifact_id):
        row=self.repo.db.execute("""SELECT a.*,s.edition_id,s.id AS script_id FROM audio_artifacts a
            JOIN audio_scripts s ON s.id=a.audio_script_id WHERE a.id=? AND a.status='READY'""",(artifact_id,)).fetchone()
        if not row or int(row["duration_ms"] or 0)<=0 or int(row["size_bytes"] or 0)<128:
            return {"status":"FAILED","error_code":"AUDIO_METADATA_INVALID"}
        path=self.storage.resolve(row["storage_path"])
        if not path: return {"status":"FAILED","error_code":"AUDIO_FILE_MISSING"}
        segments=[]
        for segment in self.repo.db.execute("""SELECT s.id,s.position,s.type,s.briefing_item_id,s.text,
            t.segment_start_ms,t.segment_end_ms FROM audio_script_segments s
            LEFT JOIN audio_artifact_segments t ON t.segment_id=s.id AND t.artifact_id=?
            WHERE s.audio_script_id=? ORDER BY s.position""",(artifact_id,row["script_id"])):
            segments.append({"id":segment["id"],"position":segment["position"],"type":segment["type"],
                "briefing_item_id":segment["briefing_item_id"],"script_text":segment["text"],
                "segment_start_ms":segment["segment_start_ms"],"segment_end_ms":segment["segment_end_ms"]})
        return {"status":"READY","edition_id":row["edition_id"],"script_id":row["script_id"],
            "artifact_id":row["id"],"duration_ms":row["duration_ms"],"size_bytes":row["size_bytes"],
            "mime_type":row["mime_type"],"language":row["language"],"voice":row["voice"],
            "provider":row["provider"],"generated_at":row["created_at"],
            "resolved_voice":row["resolved_voice"],"asset_version":row["checksum"][:12],"segments":segments}

    def artifact_path(self, edition_id, language=None, voice=None):
        language = language or self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=?", (edition_id,)).fetchone()["language"]
        script = self.repo.db.execute("SELECT id FROM audio_scripts WHERE edition_id=? AND language=? AND (script_version=? OR script_version LIKE ?) ORDER BY CASE WHEN script_version=? THEN 0 ELSE 1 END,created_at DESC LIMIT 1",
                                      (edition_id, language, self.narration_version,self.narration_version+":%",self.narration_version)).fetchone()
        if not script:
            return None
        row = self.repo.db.execute("""SELECT storage_path FROM audio_artifacts WHERE audio_script_id=?
            AND provider=? AND voice=? AND language=? AND status='READY'""",
            (script["id"], self.provider.name, voice or self.default_voice(language), language)).fetchone()
        return self.storage.resolve(row["storage_path"]) if row else None

    def metrics(self):
        counts = {row["status"]: row["count"] for row in self.repo.db.execute(
            "SELECT status,COUNT(*) AS count FROM audio_generation_jobs GROUP BY status")}
        events = {row["event_type"]: row["count"] for row in self.repo.db.execute(
            "SELECT event_type,COUNT(*) AS count FROM audio_events GROUP BY event_type")}
        completed = [json.loads(row["metadata_json"]) for row in self.repo.db.execute(
            "SELECT metadata_json FROM audio_events WHERE event_type='audio_generation_completed'")]
        failures = [json.loads(row["metadata_json"]) for row in self.repo.db.execute(
            "SELECT metadata_json FROM audio_events WHERE event_type='audio_generation_failed'")]
        phases={row["phase"]:round(row["avg_ms"]) for row in self.repo.db.execute("SELECT phase,AVG(duration_ms) AS avg_ms FROM audio_job_phases GROUP BY phase")}
        stale_cutoff=(datetime.now(timezone.utc)-timedelta(minutes=30)).isoformat()
        stale=self.repo.db.execute("SELECT COUNT(*) FROM audio_generation_jobs WHERE status='GENERATING' AND COALESCE(updated_at,started_at)<?",(stale_cutoff,)).fetchone()[0]
        oldest=self.repo.db.execute("SELECT MIN(created_at) FROM audio_generation_jobs WHERE status IN ('PENDING','GENERATING')").fetchone()[0]
        return {"audio_jobs_created": events.get("audio_job_created", 0),
                "audio_jobs_completed": counts.get("READY", 0), "audio_jobs_failed": counts.get("FAILED", 0),
                "audio_cache_hits": events.get("audio_cache_hit", 0), "tts_provider": self.provider.name,
                "audio_variant_cache_misses": events.get("audio_cache_miss", 0),
                "voice_preview_cache_hits": events.get("voice_preview_cache_hit", 0),
                "script_version": self.narration_version,"tts_version":self.tts_version,
                "audio_generation_latency_ms_avg": round(sum(x.get("latency_ms", 0) for x in completed) / len(completed)) if completed else 0,
                "audio_phase_avg_ms":phases,"audio_stale_jobs":stale,"oldest_pending_audio_job":oldest,
                "audio_duration_ms_avg": round(sum(x.get("duration_ms", 0) for x in completed) / len(completed)) if completed else 0,
                "audio_file_size_bytes_total": sum(x.get("file_size", 0) for x in completed),
                "tts_errors": {code: sum(x.get("error_code") == code for x in failures)
                               for code in {x.get("error_code") for x in failures} if code}}
