---
workflow: general-video
flow: automation
storyboard: no
message: "O homem mais livre não é aquele que possui tudo; é aquele que precisa de quase nada."
destination: reels-tiktok-shorts
aspect: 1080x1920
language: pt-BR
length: ~87s
angle: narrative
---

## Intent

Curta vertical 9:16, minimalista e filosófico: o encontro de Alexandre, o Grande, com Diógenes de Sínope (Corinto, ~336 a.C.).
Sem imagens realistas: linha do tempo + formas abstratas. Uma linha do tempo vertical (I–VIII) atravessa o filme;
Alexandre é uma figura vertical vermelho-escura, Diógenes uma figura deitada cor de linho, o sol é um disco cuja
sombra encobre e depois libera Diógenes (cena 5, o momento mais forte). Tipografia serifada, muito espaço vazio.

Paleta: arenito, bege, oliva desbotado, bronze, marrom escuro. Granulação de filme sutil, movimentos lentos,
pausas silenciosas, fade para preto com 1–2 s de silêncio no final.

## Assets

- audio/vo01..vo22.wav — narração (ElevenLabs, voz padrão "Brian", eleven_multilingual_v2, plano gratuito).
- audio/vo22.wav — PROVISÓRIO (Kokoro pm_alex): cota ElevenLabs esgotou; regenerar com `python scripts/vo.py nPczCjzI2devNBz1zQrb 22` após 11/10.
- assets/fonts/newsreader-*.woff2 — Newsreader (serifada).

## Customizations

- Roteiro do usuário com cortes mínimos para caber na cota (ver scripts/vo.py): "praticamente"→"quase", "simplesmente" removido,
  "comandante"→"senhor", "perguntou"→"falou", "respondeu"→"disse", L5/L9/L16/L17 levemente encurtadas.

## Notes

- Evitar: tela cheia de texto, transições complexas, edição estilo TikTok. Preferir cortes lentos, silhuetas, luz, sombra.
- Zonas seguras Reels: texto essencial entre y 220–1500, nada nos 22% inferiores.
