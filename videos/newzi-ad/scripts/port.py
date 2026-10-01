# One-shot port of the canvas artboard (Main.dc.html) into the HyperFrames body markup.
import re, sys
src = open(sys.argv[1], encoding="utf8").read()
body = src.split('<div class="{{stageCls}}">', 1)[1].split('<sc-if value="{{showSubs}}"', 1)[0]

def rep(old, new, count=1):
    global body
    n = body.count(old)
    assert n == count, (old[:80], n)
    body = body.replace(old, new)

# asset urls → local files
for blob, path in {
    "/_blob/e2eb442681ccd7098fa5bd9ddec15c69": "assets/newzi-lockup.png",
    "/_blob/12c2f5d32f9662cc85cbe41dd1d49fdd": "assets/sunrise.png",
    "/_blob/0060450334e440778da7cfabffabd38d": "assets/reading.png",
    "/_blob/40a25b02b30c0d5a23650f2f01077ec1": "assets/waving.png",
    "/_blob/a6025fe0073813d683e8f96ad231a89c": "assets/app-icon.svg",
}.items():
    body = body.replace(blob, path)

# scenes → timed clips (0.6s overlap for the crossfade)
scenes = [(0, 5.5), (5.5, 3.5), (9, 6.5), (15.5, 6), (21.5, 6.5), (28, 6)]
for i, (s, d) in enumerate(scenes, 1):
    dur = d + 0.6 if i < 6 else d
    hint = "true" if i == 1 else "false"
    rep(f'<sc-if value="{{{{v{i}}}}}" hint-placeholder-val="{{{{{hint}}}}}">',
        f'<section id="s{i}" class="clip" data-start="{s}" data-duration="{dur}" data-track-index="{i}">')
body = body.replace("animation-delay: 0s, 99s", "animation-delay: 0s, 99s")

# home play/pause
rep('<sc-if value="{{homePlaying}}" hint-placeholder-val="{{false}}">', '<span id="home-pause" style="display: flex; opacity: 0">')
rep('<sc-if value="{{homeIdle}}" hint-placeholder-val="{{true}}">', '<span id="home-play" style="position: absolute; display: flex">')
rep('<div style="width: 54px; height: 54px; border-radius: 28px; background: #087CF0;', '<div style="position: relative; width: 54px; height: 54px; border-radius: 28px; background: #087CF0;')
# waveforms
rep('<sc-for list="{{homeBars}}" as="b" hint-placeholder-count="34"><div style="width: 2.5px; height: {{b.h}}px; border-radius: 2px; background: {{b.c}}"></div></sc-for>', '<span id="home-bars" style="display: contents"></span>')
rep('<sc-for list="{{plBars}}" as="b" hint-placeholder-count="50"><div style="width: 2.5px; height: {{b.h}}px; border-radius: 2px; background: {{b.c}}"></div></sc-for>', '<span id="pl-bars" style="display: contents"></span>')
rep('<span>{{homePos}}</span>', '<span id="home-pos">0:00</span>')
rep('Agora: {{plChapter}}', 'Agora: <span id="pl-chap">Economia</span>')
rep('<span>{{plPos}}</span><span>-{{plRemain}}</span>', '<span id="pl-pos">2:00</span><span id="pl-rem">-6:40</span>')
rep('{{speedLabel}}', '<span id="pl-speed">1x</span>')

# chapters list
m = re.search(r'<sc-for list="\{\{chapters\}\}".*?</sc-for>', body, re.S)
chap_tpl = m.group(0)
chaps = [("Economia", "0:00"), ("Tecnologia", "1:44"), ("Política", "3:28"), ("Negócios", "5:12"), ("Ciência", "6:56")]
rows = []
for i, (name, tm) in enumerate(chaps):
    rows.append(f'''<div id="ch{i}" class="chrow" style="display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 14px">
<span class="chnum" style="width: 26px; height: 26px; border-radius: 13px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; background: #EDF3FA; color: #55719A">{i+1}</span>
<span class="chname" style="flex-grow: 1; font-size: 15px; font-weight: 600; color: #071A42">{name}</span>
<span class="cheq" style="display: flex; align-items: flex-end; gap: 2px; height: 14px; opacity: 0"><span class="a-eq" style="width: 3px; height: 14px; border-radius: 2px; background: #087CF0"></span><span class="a-eq" style="width: 3px; height: 14px; border-radius: 2px; background: #087CF0; animation-delay: -.2s"></span><span class="a-eq" style="width: 3px; height: 14px; border-radius: 2px; background: #087CF0; animation-delay: -.4s"></span></span>
<span style="font-size: 12px; color: #55719A">{tm}</span>
</div>''')
body = body.replace(chap_tpl, "\n".join(rows))

# speeds list
m = re.search(r'<sc-for list="\{\{speeds\}\}".*?</sc-for>', body, re.S)
sp = [("0,75x", "Mais lento"), ("1x", "Normal"), ("1,25x", "Mais rápido"), ("1,5x", "Mais rápido")]
rows = []
for i, (v, h) in enumerate(sp):
    rows.append(f'''<div id="sp{i}" style="display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 14px">
<div style="flex-grow: 1"><div class="spv" style="font-size: 15px; font-weight: 800; color: #071A42">{v}</div><div style="font-size: 12px; color: #55719A">{h}</div></div>
<svg class="ic spck" width="20" height="20" viewBox="0 0 24 24" style="color: #087CF0; opacity: 0"><path d="m5 12 5 5 9-10"></path></svg>
</div>''')
body = body.replace(m.group(0), "\n".join(rows))

# routine mini players
for i in (1, 2, 3):
    rep(f'{{{{r{i}.chap}}}} · {{{{r{i}.pos}}}}', f'<span id="r{i}-label">Tecnologia · 2:30</span>')
    rep(f'width: {{{{r{i}.pct}}}}%"></div>', f'width: 30%" id="r{i}-bar"></div>')

# remaining sc-if closers are exactly the scene sections + the replaced spans; convert in order
parts = body.split("</sc-if>")
closers = []
opens = re.findall(r'<section id="s\d"|<span id="home-(?:pause|play)"', body)
body_out = parts[0]
stack_iter = iter(opens)
# walk: each </sc-if> closes the most recent unclosed opener of those kinds
import collections
tokens = re.split(r'(<section id="s\d"[^>]*>|<span id="home-(?:pause|play)"[^>]*>|</sc-if>)', body)
out, stack = [], []
for tk in tokens:
    if tk.startswith('<section id="s'): stack.append("section"); out.append(tk)
    elif tk.startswith('<span id="home-'): stack.append("span"); out.append(tk)
    elif tk == "</sc-if>": out.append(f"</{stack.pop()}>")
    else: out.append(tk)
body = "".join(out)
assert "{{" not in body and "sc-" not in body, re.findall(r".{40}(?:\{\{|sc-).{40}", body)[:5]
open("scenes.html", "w", encoding="utf8").write(body)
print("ok", len(body))
