# ElevenLabs voiceover for the 9:16 reel. Reads ELEVENLABS_API_KEY from videos/newzi-ad/.env (never printed).
#   python scripts/eleven.py list                 -> pt-BR voices from the shared library + your own voices
#   python scripts/eleven.py gen <voice_id> <tag> -> audio/<tag>/vo1..vo6.wav
import json, os, subprocess, sys, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = next((l.split("=", 1)[1].strip().strip('"') for l in open(os.path.join(ROOT, "..", "newzi-ad", ".env"), encoding="utf8")
            if l.startswith("ELEVENLABS_API_KEY=")), None)
if not KEY:
    sys.exit("ELEVENLABS_API_KEY not found in videos/newzi-ad/.env")

LINES = [
    "Sem tempo pra parar e ler notícia todo dia?",
    "Mas também não quer ficar por fora?",
    "Com o NEWZI, é só dar o play.",
    "Seu resumo diário vira um briefing em áudio.",
    "No carro.",
    "No café.",
    "Ou durante a sua rotina.",
    "As notícias que importam pra você, em poucos minutos.",
    "NEWZI. Informação no seu ritmo. Baixe agora.",
]


def call(path, body=None, params=None):
    url = "https://api.elevenlabs.io" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


if sys.argv[1] == "list":
    shared = json.loads(call("/v1/shared-voices", params={"language": "pt", "locale": "pt-BR", "page_size": 40, "sort": "trending"}))
    for v in shared.get("voices", []):
        print(f'{v["voice_id"]}  {v.get("gender","?"):6} {v.get("age","?"):11} {v.get("accent","?"):10} {v["name"]} — {(v.get("descriptive") or v.get("use_case") or "")}')
    mine = json.loads(call("/v1/voices"))
    print("\n# suas vozes / premade")
    for v in mine.get("voices", []):
        labels = v.get("labels") or {}
        print(f'{v["voice_id"]}  {labels.get("gender","?"):6} {labels.get("accent","?"):12} {v["name"]}')
elif sys.argv[1] == "gen":
    voice, tag = sys.argv[2], sys.argv[3]
    out = os.path.join(ROOT, "audio", tag)
    os.makedirs(out, exist_ok=True)
    for i, text in enumerate(LINES, 1):
        mp3 = os.path.join(out, f"vo{i}.mp3")
        open(mp3, "wb").write(call(f"/v1/text-to-speech/{voice}", {
            "text": text.replace("NEWZI", "Niúzi"),
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "use_speaker_boost": True},
        }, params={"output_format": "mp3_44100_128"}))
        wav = mp3[:-4] + ".wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-ar", "44100", wav], check=True)
        os.remove(mp3)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                             capture_output=True, text=True).stdout.strip()
        print(i, dur)
