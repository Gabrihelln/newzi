# Builds index.html for the 9:16 NEWZI reel. The stage is authored at 540x960 and scaled 2x to 1080x1920.
# App screens (Home, player) are the same markup as the 16:9 ad, extracted by hand into home.html / player.html.
import re

HOME = open("scripts/home.html", encoding="utf8").read()
PLAYER = open("scripts/player.html", encoding="utf8").read()

# the reel moves faster than the 16:9 cut: tighten Home's entrance delays and pull the card glow to the tap
for old, new in [("animation-delay: .5s", "animation-delay: .15s"), ("animation-delay: .62s", "animation-delay: .22s"),
                 ("animation-delay: .78s", "animation-delay: .29s"), ("animation-delay: .94s", "animation-delay: .36s"),
                 ("animation-delay: 1.1s", "animation-delay: .43s"), ("animation-delay: .9s", "animation-delay: .3s"),
                 ("animation-delay: 2.3s", "animation-delay: 1.05s")]:
    HOME = HOME.replace(old, new)


def prefixed(markup, pre):
    return re.sub(r'id="(home|pl)-', lambda m: f'id="{pre}{m.group(1)}-', markup)


def words(text, start, step=0.06, accent_from=None, accent="#69B7F4"):
    out = []
    for i, w in enumerate(text.split()):
        color = f"; color: {accent}" if accent_from is not None and i >= accent_from else ""
        out.append(f'<span class="a-word" style="animation-delay: {start + i * step:.2f}s{color}">{w}</span>')
    return "".join(out)


def phone(inner, scale, bg="#F7FBFF", extra=""):
    return f'''<div style="width: 414px; height: 868px; transform: scale({scale}); transform-origin: 0 0; border-radius: 60px; background: #0A0F1C; padding: 12px; box-sizing: border-box; box-shadow: 0 50px 90px -30px rgba(7,26,99,0.45)">
<div style="position: relative; width: 390px; height: 844px; border-radius: 48px; overflow: hidden; background: {bg}" {extra}>
<div style="position: absolute; top: 12px; left: 140px; width: 110px; height: 32px; border-radius: 20px; background: #0A0F1C; z-index: 9"></div>
{inner}
</div>
</div>'''


PAUSE_SVG = '<svg width="{s}" height="{s}" viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" rx="1.5" fill="#FFFFFF"></rect><rect x="14" y="4" width="4" height="16" rx="1.5" fill="#FFFFFF"></rect></svg>'
H1 = "margin: 0; font-size: 42px; line-height: 1.06; font-weight: 800; letter-spacing: -1.3px"


def mini_player(pid, width=468):
    """The app's MiniAudioPlayer: cover, title, date · time, progress, round play/pause."""
    return f'''<div style="width: {width}px; min-height: 94px; display: flex; align-items: center; gap: 12px; padding: 8px 12px; box-sizing: border-box; background: #FFFFFF; border: 1px solid #D8EAF7; border-radius: 20px; box-shadow: 0 10px 28px -10px rgba(73,107,153,0.45)">
<img src="assets/sunrise.png" alt="" style="width: 58px; height: 58px; border-radius: 14px; object-fit: cover; object-position: 30% 50%">
<div style="flex-grow: 1; min-width: 0">
<div style="font-size: 15px; font-weight: 800; color: #071A63">Seu briefing diário</div>
<div id="{pid}-time" style="font-size: 12px; color: #455E85; margin-top: 4px">30 set · 2:10 / 8:40</div>
<div style="height: 4px; border-radius: 3px; background: #DBE7F4; margin-top: 8px; overflow: hidden"><div id="{pid}-bar" style="width: 25%; height: 4px; border-radius: 3px; background: #087CF0"></div></div>
</div>
<div style="width: 52px; height: 52px; border-radius: 26px; background: #087CF0; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px -2px rgba(8,124,240,0.5)">{PAUSE_SVG.format(s=22)}</div>
</div>'''


def chip(text, dark=False):
    bg, fg, bd = ("rgba(255,255,255,0.14)", "#FFFFFF", "rgba(255,255,255,0.22)") if dark else ("#FFFFFF", "#071A63", "#D8EAF7")
    return f'<span style="display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border-radius: 999px; background: {bg}; border: 1px solid {bd}; color: {fg}; font-size: 13px; font-weight: 700">{text}</span>'


def generic_feed_item(src, age, headline, shade):
    return f'''<div style="display: flex; gap: 10px; padding: 12px 14px; border-bottom: 1px solid #ECECEC">
<div style="flex-grow: 1"><div style="display: flex; align-items: center; gap: 6px; font-size: 10px; color: #6B6B6B"><span style="width: 14px; height: 14px; border-radius: 7px; background: {shade}"></span>{src} · {age}</div>
<div style="font-size: 14px; line-height: 18px; font-weight: 700; color: #151515; margin-top: 4px">{headline}</div></div>
<div style="width: 58px; height: 58px; border-radius: 8px; background: {shade}; flex-shrink: 0"></div>
</div>'''


def news_card(cat, cat_bg, cat_fg, headline, mins, rot, left, top, delay):
    return f'''<div data-layout-allow-overlap class="a-drop" style="position: absolute; left: {left}px; top: {top}px; animation-delay: {delay}s">
<div data-layout-allow-overlap style="width: 330px; transform: rotate({rot}deg); background: #FFFFFF; border-radius: 18px; padding: 14px 16px; box-sizing: border-box; box-shadow: 0 24px 50px -20px rgba(0,0,0,0.6)">
<div data-layout-allow-overlap style="display: flex; align-items: center; gap: 8px"><span data-layout-allow-overlap style="background: {cat_bg}; color: {cat_fg}; font-size: 10px; font-weight: 800; padding: 4px 9px; border-radius: 14px">{cat}</span><span data-layout-allow-overlap style="color: #455E85; font-size: 11px">{mins} min de leitura</span></div>
<div data-layout-allow-overlap style="margin-top: 6px; font-size: 17px; line-height: 21px; font-weight: 700; color: #091D42">{headline}</div>
</div></div>'''


# ─────────────────────────── scenes ───────────────────────────
feed = "".join(generic_feed_item(*row) for row in [
    ("Portal Diário", "há 2 min", "Mercados reagem aos novos dados de inflação", "#D9D9D9"),
    ("Agência News", "há 5 min", "Nova regulação de IA avança no Congresso", "#CFCFCF"),
    ("Jornal da Manhã", "há 8 min", "Reforma entra na reta final de votação", "#DEDEDE"),
    ("Portal Diário", "há 11 min", "Startups ampliam investimentos em inteligência artificial", "#D4D4D4"),
    ("Revista Tech", "há 14 min", "Missão espacial revela novas imagens do Sol", "#CBCBCB"),
    ("Agência News", "há 20 min", "Dólar fecha em alta após decisão do Fed", "#DADADA"),
    ("Jornal da Manhã", "há 26 min", "Chuvas devem voltar no fim de semana", "#D0D0D0"),
    ("Portal Diário", "há 31 min", "Seleção anuncia convocados para amistosos", "#D7D7D7"),
    ("Revista Tech", "há 40 min", "Nova geração de chips promete baterias mais duradouras", "#CECECE"),
])
SKIN = "#E3B08C"

S1 = f'''<section id="s1" class="clip" data-start="0" data-duration="2.75" data-track-index="1">
<div class="scene" style="background: #06122F; animation-delay: 0s, 2.4s">
<div data-layout-allow-overflow class="a-fin" style="position: absolute; left: -180px; top: -260px; width: 900px; height: 900px; border-radius: 50%; background: radial-gradient(circle, rgba(8,124,240,0.30), rgba(8,124,240,0) 60%)"></div>
<div style="position: absolute; left: 36px; top: 118px; width: 440px">
<h1 style="{H1}; font-size: 44px; color: #FFFFFF">{words("Sem tempo para parar e ler notícias?", 0.05, 0.06, accent_from=5)}</h1>
<div class="a-up" style="margin-top: 14px; font-size: 19px; font-weight: 600; color: #A9C6EA; animation-delay: .75s">Todo dia é notícia demais.</div>
</div>
<div data-layout-allow-overflow class="a-rise" style="position: absolute; left: 168px; top: 392px; width: 250px; height: 540px; animation-duration: .6s">
<div data-layout-allow-overflow style="position: relative; width: 250px; height: 540px; transform: rotate(-5deg)">
<div style="position: absolute; left: 0; top: 0; width: 250px; height: 540px; border-radius: 34px; background: #111418; padding: 8px; box-sizing: border-box">
<div style="position: relative; width: 234px; height: 524px; border-radius: 27px; overflow: hidden; background: #FFFFFF">
<div data-layout-allow-overlap style="position: absolute; left: 0; right: 0; top: 0; height: 58px; padding: 26px 14px 0; box-sizing: border-box; display: flex; justify-content: space-between; background: #FFFFFF; z-index: 2; border-bottom: 1px solid #ECECEC"><span data-layout-allow-overlap style="font-size: 15px; font-weight: 800; color: #151515">Notícias</span><span data-layout-allow-overlap style="font-size: 11px; color: #6B6B6B">Mais lidas</span></div>
<div class="a-feed" style="position: absolute; left: 0; right: 0; top: 58px; animation-delay: .35s">{feed}</div>
</div></div>
<div data-layout-allow-overflow style="position: absolute; left: -16px; top: 300px; width: 38px; height: 76px; border-radius: 19px; background: {SKIN}; transform: rotate(18deg)"></div>
<div data-layout-allow-overflow style="position: absolute; left: 234px; top: 214px; width: 34px; height: 24px; border-radius: 12px; background: {SKIN}"></div>
<div data-layout-allow-overflow style="position: absolute; left: 236px; top: 262px; width: 34px; height: 24px; border-radius: 12px; background: {SKIN}"></div>
<div data-layout-allow-overflow style="position: absolute; left: 234px; top: 310px; width: 32px; height: 24px; border-radius: 12px; background: {SKIN}"></div>
</div></div>
<div data-layout-allow-overflow class="a-up" style="position: absolute; left: 14px; top: 600px; width: 130px; height: 170px; animation-delay: .2s">
<svg width="130" height="170" viewBox="0 0 130 170" style="position: absolute; left: 0; top: 0">
<path class="a-steam" d="M44 40 q-8 -12 0 -24 q8 -12 0 -24" fill="none" stroke="#9FB7D6" stroke-width="3" stroke-linecap="round"></path>
<path class="a-steam" d="M66 36 q-8 -12 0 -24 q8 -12 0 -24" fill="none" stroke="#9FB7D6" stroke-width="3" stroke-linecap="round" style="animation-delay: .5s"></path>
<path d="M92 76 a20 20 0 0 1 0 40" fill="none" stroke="#F4EFE9" stroke-width="9" stroke-linecap="round"></path>
<rect x="18" y="56" width="80" height="94" rx="16" fill="#F4EFE9"></rect>
<rect x="18" y="80" width="80" height="22" fill="#087CF0"></rect>
</svg>
<div data-layout-allow-overflow style="position: absolute; left: 6px; top: 96px; width: 34px; height: 60px; border-radius: 17px; background: {SKIN}"></div>
<div data-layout-allow-overflow style="position: absolute; left: 88px; top: 90px; width: 26px; height: 64px; border-radius: 13px; background: {SKIN}"></div>
</div>
<div class="a-pop" style="position: absolute; right: 40px; top: 344px; animation-delay: .95s">
<div class="a-alarm" style="display: flex; align-items: center; gap: 7px; padding: 9px 15px; border-radius: 999px; background: rgba(255,255,255,0.13); border: 1px solid rgba(255,255,255,0.24); color: #FFFFFF; font-size: 17px; font-weight: 800; animation-delay: 1.15s">
<svg width="18" height="18" viewBox="0 0 24 24" class="ic"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>07:42</div></div>
</div>
</section>'''

S2 = f'''<section id="s2" class="clip" data-start="2.4" data-duration="2.85" data-track-index="2">
<div class="scene" style="background: #0B1B4D; animation-delay: 0s, 2.5s">
<div class="cut" style="animation-delay: 0s, .8s">
{news_card("ECONOMIA", "#FFF4E4", "#9A5C08", "Mercados reagem aos novos dados de inflação", 7, -5, 70, 360, .02)}
{news_card("TECNOLOGIA", "#E8F3FF", "#1266D0", "Nova regulação de IA avança no Congresso", 9, 4, 130, 450, .1)}
{news_card("POLÍTICA", "#FFECEF", "#B92F46", "Reforma entra na reta final de votação", 6, -3, 60, 540, .18)}
{news_card("NEGÓCIOS", "#E7F8EF", "#0D7549", "Startups ampliam investimentos em inteligência artificial", 5, 5, 120, 630, .26)}
<div class="a-pop" style="position: absolute; left: 290px; top: 322px; animation-delay: .3s">{chip("+48 notícias não lidas", dark=True)}</div>
</div>
<div class="cut" style="animation-delay: .8s, 1.6s">
<svg width="540" height="960" viewBox="0 0 540 960" style="position: absolute; left: 0; top: 0">
<g class="a-pop" style="animation-delay: .82s; transform-origin: 150px 480px">
<path d="M100 440 h100 a14 14 0 0 1 14 14 v150 a20 20 0 0 1 -20 20 h-88 a20 20 0 0 1 -20 -20 v-150 a14 14 0 0 1 14 -14z" fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linejoin="round"></path>
<path d="M120 440 v-24 a30 30 0 0 1 60 0 v24" fill="none" stroke="#FFFFFF" stroke-width="5"></path>
<rect x="118" y="520" width="64" height="40" rx="10" fill="none" stroke="#69B7F4" stroke-width="5"></rect>
</g>
<g class="a-pop" style="animation-delay: .9s; transform-origin: 330px 470px">
<circle cx="300" cy="450" r="30" fill="none" stroke="#FFFFFF" stroke-width="5"></circle>
<path d="M324 468 l70 70 m-24 -24 l16 -16 m-2 30 l16 -16" fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round"></path>
</g>
<g class="a-pop" style="animation-delay: .98s; transform-origin: 400px 600px">
<path d="M368 560 h64 l-8 96 a10 10 0 0 1 -10 9 h-28 a10 10 0 0 1 -10 -9z" fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linejoin="round"></path>
<path d="M362 546 h76 v14 h-76z" fill="#69B7F4"></path>
</g>
</svg>
<div class="a-pop" style="position: absolute; left: 36px; top: 700px; animation-delay: 1.05s">{chip("07:50 · saindo de casa", dark=True)}</div>
</div>
<div class="cut" style="animation-delay: 1.6s, 9s">
<svg width="540" height="960" viewBox="0 0 540 960" style="position: absolute; left: 0; top: 0">
<rect x="150" y="330" width="240" height="440" rx="6" fill="#071238"></rect>
<polygon class="a-fin" points="150,330 390,330 390,770 150,770" fill="#FFE2B8" opacity="0.9" style="animation-delay: 1.62s"></polygon>
<polygon points="150,330 250,360 250,740 150,770" fill="#1B2F6E"></polygon>
<circle cx="236" cy="560" r="6" fill="#69B7F4"></circle>
</svg>
<div class="a-fill" style="position: absolute; left: 190px; top: 470px; width: 170px; height: 110px; border-radius: 18px; background: #F7FBFF; padding: 12px; box-sizing: border-box; animation-delay: 2.0s">
<div style="width: 60px; height: 8px; border-radius: 4px; background: #CFE3F7"></div>
<div style="width: 140px; height: 10px; border-radius: 5px; background: #9DB4D3; margin-top: 10px"></div>
<div style="width: 110px; height: 10px; border-radius: 5px; background: #9DB4D3; margin-top: 6px"></div>
</div>
</div>
<div style="position: absolute; left: 36px; top: 118px; width: 450px">
<h1 style="{H1}; color: #FFFFFF">{words("Mas você também não quer ficar por fora.", 0.05, 0.05, accent_from=5)}</h1>
</div>
</div>
</section>'''

# Home → tap Play → player slides up, all inside one phone that stays on screen (4.9s → 8.95s)
home_tap = '''<div class="a-tap" style="position: absolute; left: 312px; top: 212px; width: 40px; height: 40px; border-radius: 50%; background: rgba(255,255,255,0.85); border: 2px solid rgba(7,26,99,0.2); box-shadow: 0 8px 20px -6px rgba(7,26,99,0.4); animation-delay: .7s"></div>
<div class="a-ripple" style="position: absolute; left: 305px; top: 205px; width: 54px; height: 54px; border-radius: 50%; background: rgba(8,124,240,0.4); animation-delay: 1.05s"></div>'''
player_sheet = f'<div class="a-slideup" style="position: absolute; left: 0; top: 0; width: 390px; height: 844px; background: #F7FBFF; z-index: 5; animation-delay: 1.7s">{PLAYER}</div>'

S3 = f'''<section id="s3" class="clip" data-start="4.9" data-duration="4.05" data-track-index="3">
<div class="scene" style="background: #F7FBFF; animation-delay: 0s, 3.7s">
<div data-layout-allow-overflow class="a-fin" style="position: absolute; left: -160px; top: 300px; width: 860px; height: 860px; border-radius: 50%; background: #E3F0FD"></div>
<div class="txt" style="position: absolute; left: 36px; top: 118px; width: 468px; animation-delay: .1s, 1.55s">
<h1 style="{H1}; color: #071A63">{words("Então, só dê o play.", 0.12, 0.07, accent_from=3, accent="#0668CF")}</h1>
</div>
<div class="txt" style="position: absolute; left: 36px; top: 118px; width: 468px; animation-delay: 1.8s, 9s">
<h1 style="{H1}; color: #071A63">{words("NEWZI resume o que importa para você.", 1.8, 0.05, accent_from=0, accent="#0668CF").replace('#0668CF">resume', '#071A63">resume')}</h1>
</div>
<div class="a-rise" style="position: absolute; left: 108px; top: 262px; width: 323px; height: 677px; animation-duration: .6s">
<div class="a-zoomcard" style="width: 323px; height: 677px; transform-origin: 50% 31%">
<div class="a-zoomwave" style="width: 323px; height: 677px; transform-origin: 50% 72%; animation-delay: 1.9s">
{phone(f'<div class="a-gone" style="position: absolute; left: 0; top: 0; width: 390px; height: 844px; animation-delay: 2.3s">{HOME}{home_tap}</div>' + player_sheet, 0.78)}
</div></div></div>
</div>
</section>'''
# only "NEWZI" takes the accent in the second line
S3 = re.sub(r'(<span class="a-word" style="animation-delay: [12]\.\d\ds); color: #0668CF">(?!NEWZI)', r'\1">', S3)

CAR = '''<svg width="540" height="960" viewBox="0 0 540 960" style="position: absolute; left: 0; top: 0">
<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#BFD9F2"></stop><stop offset="1" stop-color="#F6E6D2"></stop></linearGradient></defs>
<rect x="0" y="0" width="540" height="560" fill="url(#sky)"></rect>
<g fill="#A9BFD8"><rect x="30" y="360" width="26" height="80"></rect><rect x="62" y="330" width="22" height="110"></rect><rect x="90" y="378" width="30" height="62"></rect><rect x="380" y="340" width="28" height="100"></rect><rect x="414" y="310" width="20" height="130"></rect><rect x="440" y="364" width="34" height="76"></rect></g>
<polygon points="248,440 292,440 540,760 0,760" fill="#8C9DB3"></polygon>
<line class="a-road" x1="270" y1="446" x2="270" y2="760" stroke="#FFFFFF" stroke-width="6" stroke-dasharray="20 26"></line>
<path fill-rule="evenodd" d="M0 0 H540 V960 H0Z M44 150 Q270 96 496 150 L516 560 Q270 520 24 560Z" fill="#0B1B4D"></path>
<path d="M0 600 Q270 540 540 600 L540 960 L0 960Z" fill="#101F52"></path>
<path d="M0 600 Q270 540 540 600" fill="none" stroke="#2A4A9A" stroke-width="3"></path>
<circle cx="150" cy="930" r="210" fill="none" stroke="#1B2C66" stroke-width="36"></circle>
<circle cx="150" cy="930" r="60" fill="#1B2C66"></circle>
</svg>'''

S5 = f'''<section id="s5" class="clip" data-start="8.6" data-duration="2.05" data-track-index="5">
<div class="scene iris" style="background: #0B1B4D; animation-delay: 0s, 1.7s">
<div class="a-sway" style="position: absolute; left: 0; top: 0; width: 540px; height: 960px">{CAR}</div>
<div style="position: absolute; left: 70px; top: 196px; width: 400px">
<h1 style="{H1}; font-size: 60px; color: #071A63">{words("No carro.", 0.3, 0.1)}</h1>
<div class="a-up" style="margin-top: 10px; animation-delay: .6s">{chip("Pelo som do carro, sem tocar no celular")}</div>
</div>
</div>
</section>'''

S6 = f'''<section id="s6" class="clip" data-start="10.3" data-duration="2.05" data-track-index="6">
<div class="scene" style="background: #EFE6DA; animation-delay: 0s, 1.7s">
<svg width="540" height="960" viewBox="0 0 540 960" style="position: absolute; left: 0; top: 0">
<g stroke="#E4D6C4" stroke-width="2"><line x1="0" y1="140" x2="540" y2="170"></line><line x1="0" y1="420" x2="540" y2="400"></line><line x1="0" y1="720" x2="540" y2="760"></line></g>
<rect x="-30" y="600" width="210" height="260" rx="10" fill="#F9F5EF" transform="rotate(-8 75 730)"></rect>
<line x1="10" y1="660" x2="150" y2="640" stroke="#E0D5C6" stroke-width="3"></line><line x1="14" y1="690" x2="154" y2="670" stroke="#E0D5C6" stroke-width="3"></line>
<g transform="translate(400 700)"><rect x="-46" y="-34" width="92" height="68" rx="30" fill="#FFFFFF"></rect><line x1="-44" y1="-6" x2="44" y2="-6" stroke="#E3E3E3" stroke-width="2"></line><circle cx="0" cy="10" r="4" fill="#087CF0"></circle></g>
<circle cx="300" cy="430" r="126" fill="#FFFFFF"></circle>
<circle cx="300" cy="430" r="126" fill="none" stroke="#E7DFD4" stroke-width="3"></circle>
<rect x="378" y="410" width="70" height="36" rx="18" fill="#FFFFFF" stroke="#E7DFD4" stroke-width="3"></rect>
<circle cx="300" cy="430" r="84" fill="#FFFFFF" stroke="#E7DFD4" stroke-width="3"></circle>
<circle cx="300" cy="430" r="70" fill="#6B4226"></circle>
<path d="M300 462 C262 432 272 398 300 414 C328 398 338 432 300 462Z" fill="#E9CFAE"></path>
</svg>
<div class="a-steam2" style="position: absolute; left: 250px; top: 300px; width: 70px; height: 110px; border-radius: 50%; background: radial-gradient(circle, rgba(255,255,255,0.85), rgba(255,255,255,0) 70%)"></div>
<div class="a-steam2" style="position: absolute; left: 290px; top: 280px; width: 60px; height: 100px; border-radius: 50%; background: radial-gradient(circle, rgba(255,255,255,0.8), rgba(255,255,255,0) 70%); animation-delay: .6s"></div>
<div style="position: absolute; left: 36px; top: 118px; width: 440px">
<h1 style="{H1}; font-size: 60px; color: #071A63">{words("No café.", 0.15, 0.1)}</h1>
</div>
<div class="a-bloom" style="position: absolute; left: 0; top: 0; width: 540px; height: 960px; background: #EAF4FF; animation-delay: 1.45s"></div>
</div>
</section>'''


def vignette(i, start, bg, art, label):
    end = start + 0.52 if i < 3 else 9
    return f'''<div class="cut" style="animation-delay: {start}s, {end}s; background: {bg}">
<div class="a-settle" style="position: absolute; left: 0; top: 0; width: 468px; height: 290px; animation-delay: {start}s">{art}</div>
<div style="position: absolute; left: 16px; top: 16px">{chip(label)}</div>
</div>'''


WALK = '''<svg width="468" height="290" viewBox="0 0 468 290"><rect width="468" height="290" fill="#CFE3F7"></rect><polygon points="200,120 268,120 468,290 0,290" fill="#F4F8FC"></polygon><line class="a-road" x1="234" y1="124" x2="234" y2="290" stroke="#CFE3F7" stroke-width="5" stroke-dasharray="14 18"></line><circle cx="90" cy="96" r="38" fill="#9DC7EC"></circle><rect x="86" y="120" width="8" height="40" fill="#7FA9CF"></rect><circle cx="392" cy="86" r="30" fill="#9DC7EC"></circle><rect x="388" y="104" width="8" height="46" fill="#7FA9CF"></rect><g transform="translate(300 170)"><path d="M0 60 q10 -40 40 -46 l40 -4 q30 0 40 24 l6 26z" fill="#FFFFFF" stroke="#071A63" stroke-width="4" stroke-linejoin="round"></path><line x1="0" y1="60" x2="126" y2="60" stroke="#071A63" stroke-width="6" stroke-linecap="round"></line></g></svg>'''
METRO = '''<svg width="468" height="290" viewBox="0 0 468 290"><rect width="468" height="290" fill="#0B1B4D"></rect><rect x="30" y="40" width="408" height="170" rx="26" fill="#BFD9F2"></rect><g class="a-pan" fill="#8FB2D6"><rect x="40" y="120" width="40" height="90"></rect><rect x="96" y="90" width="30" height="120"></rect><rect x="140" y="130" width="54" height="80"></rect><rect x="214" y="80" width="34" height="130"></rect><rect x="266" y="116" width="46" height="94"></rect><rect x="330" y="96" width="30" height="114"></rect><rect x="380" y="126" width="52" height="84"></rect><rect x="450" y="100" width="36" height="110"></rect><rect x="500" y="124" width="44" height="86"></rect><rect x="560" y="92" width="30" height="118"></rect></g><rect x="30" y="40" width="408" height="170" rx="26" fill="none" stroke="#16307A" stroke-width="10"></rect><line x1="0" y1="250" x2="468" y2="250" stroke="#69B7F4" stroke-width="8" stroke-linecap="round"></line></svg>'''
READY = '''<svg width="468" height="290" viewBox="0 0 468 290"><rect width="468" height="290" fill="#F2F6FB"></rect><rect x="60" y="30" width="150" height="230" rx="75" fill="#DCEAF7" stroke="#9DB4D3" stroke-width="6"></rect><path d="M90 90 l40 -30 M96 130 l60 -44" stroke="#FFFFFF" stroke-width="8" stroke-linecap="round"></path><line x1="250" y1="60" x2="430" y2="60" stroke="#9DB4D3" stroke-width="6" stroke-linecap="round"></line><path d="M340 60 v14 l-60 40 h120 l-60 -40" fill="none" stroke="#071A63" stroke-width="5" stroke-linejoin="round"></path><path d="M288 114 h104 l-10 130 h-84z" fill="#087CF0"></path></svg>'''
DESK = '''<svg width="468" height="290" viewBox="0 0 468 290"><rect width="468" height="290" fill="#EEF4FA"></rect><rect x="0" y="210" width="468" height="80" fill="#D9E6F2"></rect><rect x="120" y="70" width="210" height="136" rx="10" fill="#071A63"></rect><rect x="132" y="82" width="186" height="112" rx="4" fill="#DCEAF7"></rect><rect x="96" y="206" width="258" height="12" rx="6" fill="#9DB4D3"></rect><path d="M372 190 a36 36 0 0 1 72 0" fill="none" stroke="#071A63" stroke-width="7"></path><rect x="364" y="182" width="18" height="30" rx="8" fill="#087CF0"></rect><rect x="434" y="182" width="18" height="30" rx="8" fill="#087CF0"></rect><rect x="40" y="150" width="40" height="60" rx="8" fill="#9DC7EC"></rect><path d="M60 150 q-20 -40 0 -60 q20 20 0 60" fill="#16A568"></path></svg>'''

S7 = f'''<section id="s7" class="clip" data-start="12.0" data-duration="2.35" data-track-index="7">
<div class="scene" style="background: #EAF4FF; animation-delay: 0s, 2.0s">
<div class="txt" style="position: absolute; left: 36px; top: 118px; width: 468px; animation-delay: .05s, 1.0s">
<h1 style="{H1}; font-size: 52px; color: #071A63">{words("Na sua rotina.", 0.1, 0.08, accent_from=1, accent="#0668CF")}</h1>
</div>
<div class="txt" style="position: absolute; left: 36px; top: 118px; width: 468px; animation-delay: 1.05s, 9s">
<h1 style="{H1}; color: #071A63">{words("Sem precisar parar para ler tudo.", 1.05, 0.05)}</h1>
</div>
<div class="a-up" style="position: absolute; left: 36px; top: 262px; width: 468px; height: 290px; border-radius: 28px; overflow: hidden; box-shadow: 0 30px 60px -30px rgba(7,26,99,0.35); animation-delay: .05s">
{vignette(0, 0, "#CFE3F7", WALK, "Caminhando")}
{vignette(1, .52, "#0B1B4D", METRO, "No metrô")}
{vignette(2, 1.04, "#F2F6FB", READY, "Se arrumando")}
{vignette(3, 1.56, "#EEF4FA", DESK, "No trabalho")}
</div>
</div>
</section>'''

MINI = f'''<section id="mini" class="clip" data-start="8.6" data-duration="5.6" data-track-index="8">
<div class="scene" style="animation-delay: 0s, 5.3s">
<div class="a-up" style="position: absolute; left: 36px; top: 580px; animation-delay: .35s">{mini_player("mp")}</div>
</div>
</section>'''

ARTICLE = f'''<div style="position: absolute; left: 0; top: 0; right: 0; bottom: 0; background: #F5FAFF">
<div style="height: 62px; margin-top: 44px; padding: 0 14px; display: flex; align-items: center; justify-content: space-between; background: #F8FBFF; color: #1D3767">
<svg width="24" height="24" viewBox="0 0 24 24" class="ic"><path d="m15 5-7 7 7 7"></path></svg>
<img src="assets/newzi-lockup.png" alt="NEWZI" style="width: 105px; height: 36px; object-fit: contain">
<div style="display: flex; gap: 12px"><svg width="22" height="22" viewBox="0 0 24 24" class="ic"><path d="M6 4.5A1.5 1.5 0 0 1 7.5 3h9A1.5 1.5 0 0 1 18 4.5V21l-6-4-6 4Z"></path></svg><svg width="22" height="22" viewBox="0 0 24 24" class="ic"><path d="M12 3v12m-5-7 5-5 5 5M5 14v6h14v-6"></path></svg></div>
</div>
<div style="height: 210px; background: #FFF4E4; display: flex; align-items: center; justify-content: center; color: #E99113"><svg width="64" height="64" viewBox="0 0 24 24" class="ic"><path d="M4 18V9m5 9V5m5 13v-6m5 6V7"></path><path d="m3 7 6-3 5 4 7-5"></path></svg></div>
<div style="margin-top: -22px; border-radius: 24px 24px 0 0; background: #FBFDFF; padding: 19px 20px 0">
<div style="display: flex; align-items: center; justify-content: space-between"><span style="border-radius: 18px; background: #E6F0FF; color: #1066D6; padding: 7px 13px; font-size: 11px; font-weight: 800">ECONOMIA</span><span style="font-size: 12px; color: #455E85">4 min de leitura</span></div>
<div style="color: #091940; font-size: 28px; line-height: 34px; font-weight: 800; letter-spacing: -0.7px; margin-top: 14px">Banco Central mantém juros e sinaliza cautela</div>
<div style="color: #455E85; font-size: 16px; line-height: 24px; margin-top: 9px">A decisão veio dentro do esperado. O que muda para o crédito e para os investimentos nos próximos meses.</div>
<div style="display: flex; align-items: center; gap: 11px; margin-top: 16px"><div style="width: 42px; height: 42px; border-radius: 21px; background: #E7F1FC; color: #1066D6; font-weight: 800; display: flex; align-items: center; justify-content: center">P</div><div><div style="font-size: 13px; font-weight: 700; color: #0B1B40">Fonte: Portal Diário</div><div style="font-size: 12px; color: #455E85">30 de setembro de 2026</div></div></div>
</div>
<div class="a-up" style="position: absolute; left: 16px; right: 16px; bottom: 26px; animation-delay: 1.35s">{mini_player("am", 358)}</div>
</div>'''

B_HOME = f'<div class="a-gone" style="position: absolute; left: 0; top: 0; width: 390px; height: 844px; animation-delay: 1.6s"><div class="a-homescroll" style="position: absolute; left: 0; top: 0; width: 390px; height: 1100px; animation-delay: .2s">{prefixed(HOME, "b-")}</div></div>'
S8 = f'''<section id="s8" class="clip" data-start="14.0" data-duration="3.35" data-track-index="9">
<div class="scene" style="background: #F7FBFF; animation-delay: 0s, 3.0s">
<div data-layout-allow-overflow class="a-fin" style="position: absolute; left: -200px; top: 360px; width: 940px; height: 940px; border-radius: 50%; background: #E3F0FD"></div>
<div class="txt" style="position: absolute; left: 36px; top: 118px; width: 468px; animation-delay: .05s, .95s"><h1 style="{H1}; color: #071A63">{words("Seu resumo diário.", 0.08, 0.06, accent_from=1, accent="#0668CF")}</h1></div>
<div class="txt" style="position: absolute; left: 36px; top: 118px; width: 468px; animation-delay: 1.0s, 1.95s"><h1 style="{H1}; color: #071A63">{words("As notícias que importam.", 1.0, 0.05, accent_from=3, accent="#0668CF")}</h1></div>
<div class="txt" style="position: absolute; left: 36px; top: 118px; width: 468px; animation-delay: 2.0s, 9s"><h1 style="{H1}; color: #071A63">{words("Em poucos minutos.", 2.0, 0.06, accent_from=1, accent="#0668CF")}</h1></div>
<div class="a-rise" style="position: absolute; left: 104px; top: 250px; width: 331px; height: 694px; animation-duration: .6s">
{phone(B_HOME + f'<div class="a-slideup" style="position: absolute; left: 0; top: 0; width: 390px; height: 844px; z-index: 5; animation-delay: 1.0s"><div class="a-gone" style="position: absolute; left: 0; top: 0; width: 390px; height: 844px; animation-delay: 2.6s">{ARTICLE}</div></div>' + f'<div class="a-slideup" style="position: absolute; left: 0; top: 0; width: 390px; height: 844px; background: #F7FBFF; z-index: 6; animation-delay: 2.0s">{prefixed(PLAYER, "b-")}</div>', 0.8)}
</div>
</div>
</section>'''

S9 = f'''<section id="s9" class="clip" data-start="17.0" data-duration="3.6" data-track-index="10">
<div class="scene" style="background: #FFFFFF; animation-delay: 0s, 99s">
<div data-layout-allow-overflow class="a-pop" style="position: absolute; left: -110px; top: 170px; width: 760px; height: 760px; border-radius: 50%; background: #F0F7FE; animation-delay: .05s"></div>
<div style="position: absolute; left: 36px; top: 118px; width: 468px">
<h1 style="{H1}; color: #071A63">{words("Fique informado sem parar sua rotina.", 0.1, 0.06, accent_from=3, accent="#0668CF")}</h1>
</div>
<div class="a-rise" style="position: absolute; left: 154px; top: 300px; width: 232px; height: 486px; animation-duration: .7s; animation-delay: .15s">
<div class="a-dock" style="width: 232px; height: 486px; animation-delay: 1.25s">
{phone(prefixed(PLAYER, "c-"), 0.56)}
</div></div>
<div style="position: absolute; left: 0; right: 0; top: 296px; display: flex; flex-direction: column; align-items: center">
<img class="a-pop" src="assets/newzi-lockup.png" alt="NEWZI" style="width: 360px; height: 128px; object-fit: contain; animation-delay: 1.4s">
<div class="a-up" style="margin-top: -6px; font-size: 19px; font-weight: 600; color: #455E85; animation-delay: 1.6s">Informação no seu ritmo.</div>
<div class="a-pop" style="margin-top: 22px; animation-delay: 1.75s"><div class="a-pulse" style="display: flex; align-items: center; gap: 10px; height: 58px; padding: 0 30px; border-radius: 999px; background: #087CF0; color: #FFFFFF; font-size: 22px; font-weight: 800; animation-delay: 2.3s">Baixe agora<svg width="20" height="20" viewBox="0 0 24 24" class="ic" style="stroke-width: 2.6"><path d="M5 12h14m-6-6 6 6-6 6"></path></svg></div></div>
<div class="a-up" style="margin-top: 14px; font-size: 15px; font-weight: 600; color: #0668CF; animation-delay: 1.95s">Ouça seu briefing diário</div>
</div>
</div>
</section>'''

head = open("scripts/head.html", encoding="utf8").read()
tail = open("scripts/tail.html", encoding="utf8").read()
open("index.html", "w", encoding="utf8").write(head + "\n".join([S1, S2, S3, S5, S6, S7, MINI, S8, S9]) + tail)
print("ok")
