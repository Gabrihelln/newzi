# Offline pt-BR voiceover via Kokoro; espeak data copied to an ASCII path (Windows user path has "ú").
import os, sys, soundfile as sf
from kokoro_onnx import Kokoro
from kokoro_onnx.config import EspeakConfig
home = os.path.expanduser("~/.cache/hyperframes/tts")
k = Kokoro(f"{home}/models/kokoro-v1.0.onnx", f"{home}/voices/voices-v1.0.bin",
           espeak_config=EspeakConfig(data_path="C:/hf-espeak/espeak-ng-data"))
lines = [
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
for i, text in enumerate(lines, 1):
    samples, sr = k.create(text.replace("NEWZI", "Niúzi"), voice="pf_dora", speed=1.08, lang="pt-br")
    sf.write(f"audio/vo{i}.wav", samples, sr)
    print(i, round(len(samples) / sr, 2))
