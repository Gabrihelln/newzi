# Offline pt-BR voiceover via Kokoro; espeak data copied to an ASCII path (Windows user path has "ú").
import os, sys, soundfile as sf
from kokoro_onnx import Kokoro
from kokoro_onnx.config import EspeakConfig
home = os.path.expanduser("~/.cache/hyperframes/tts")
k = Kokoro(f"{home}/models/kokoro-v1.0.onnx", f"{home}/voices/voices-v1.0.bin",
           espeak_config=EspeakConfig(data_path="C:/hf-espeak/espeak-ng-data"))
lines = [
    "Correria, reunião, trânsito... e as notícias ficando pra depois?",
    "Com o NEWZI, você não precisa parar.",
    "Todo dia, um briefing feito pra você, com o que realmente importa.",
    "É só dar o play e ouvir, capítulo por capítulo, na velocidade que preferir.",
    "No carro, no café, no seu dia.",
    "NEWZI. As notícias que importam, no seu ritmo. Baixe agora.",
]
voice = sys.argv[1] if len(sys.argv) > 1 else "pf_dora"
for i, text in enumerate(lines, 1):
    samples, sr = k.create(text.replace("NEWZI", "Niúzi"), voice=voice, speed=1.0, lang="pt-br")
    sf.write(f"audio/vo{i}.wav", samples, sr)
    print(i, round(len(samples) / sr, 2))
