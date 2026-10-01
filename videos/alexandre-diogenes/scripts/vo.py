# ElevenLabs pt-BR voiceover, one file per line so pauses are placed on the timeline.
# Key read from videos/newzi-ad/.env (never printed). Usage: python scripts/vo.py [voice_id] [only_index...]
import json, os, subprocess, sys, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = next((l.split("=", 1)[1].strip().strip('"') for l in open(os.path.join(ROOT, "..", "newzi-ad", ".env"), encoding="utf8")
            if l.startswith("ELEVENLABS_API_KEY=")), None)
VOICE = sys.argv[1] if len(sys.argv) > 1 else "nPczCjzI2devNBz1zQrb"  # Brian - Deep, Resonant (premade; free plan has no library voices)
ONLY = {int(a) for a in sys.argv[2:]}

LINES = [
    "Há mais de dois mil anos, um dos homens mais poderosos do mundo decidiu visitar um homem que não possuía quase nada.",
    "Era Alexandre, o Grande.",
    "Rei da Macedônia, conquistador de impérios, senhor de milhares de soldados.",
    "O homem que ele procurava era Diógenes.",
    "Um filósofo que desprezava riquezas, títulos e tudo o que considerava desnecessário.",
    "Quando Alexandre o encontrou, Diógenes estava deitado ao sol.",
    "O rei parou diante dele e falou:",
    "Eu sou Alexandre. Peça o que quiser, e eu lhe darei.",
    "Diógenes olhou para o homem que poderia lhe dar ouro, terras ou poder.",
    "E respondeu:",
    "Sim. Há uma coisa que você pode fazer por mim.",
    "Alexandre esperou.",
    "Então Diógenes disse:",
    "Saia da frente do meu sol.",
    "Por alguns segundos, ninguém disse nada.",
    "Diante dele estava um homem que não queria seu dinheiro, suas terras ou sua influência.",
    "Porque quem não deseja o que você possui…",
    "não pode ser controlado por você.",
    "Conta-se que Alexandre, impressionado, disse:",
    "Se eu não fosse Alexandre… gostaria de ser Diógenes.",
    "Às vezes, o homem mais livre não é aquele que possui tudo.",
    "É aquele que precisa de quase nada.",
]


def tts(text, prev, nxt):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?" + urllib.parse.urlencode({"output_format": "mp3_44100_128"})
    body = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.62, "similarity_boost": 0.8, "style": 0.08, "use_speaker_boost": True, "speed": 0.9}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


out = os.path.join(ROOT, "audio")
for i, text in enumerate(LINES, 1):
    if ONLY and i not in ONLY:
        continue
    mp3 = os.path.join(out, f"vo{i:02d}.mp3")
    open(mp3, "wb").write(tts(text, " ".join(LINES[max(0, i - 3):i - 1]), " ".join(LINES[i:i + 2])))
    wav = mp3[:-4] + ".wav"
    # trim leading/trailing silence so timeline placement is exact
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-af",
                    "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                    "-ar", "44100", wav], check=True)
    os.remove(mp3)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                         capture_output=True, text=True).stdout.strip()
    print(i, dur)
