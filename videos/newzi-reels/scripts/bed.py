# 20s bed, 104 BPM: clock ticks + low drone under the pain beats (0-4.9s),
# pad + arpeggio bloom when NEWZI appears (4.9s), resolves on the CTA (17s).
import numpy as np, soundfile as sf
SR, DUR, BPM, OPEN, END = 44100, 20.6, 104, 4.9, 17.0
beat = 60 / BPM
t = np.arange(int(SR * DUR)) / SR
mf = lambda m: 440 * 2 ** ((m - 69) / 12)
chords = [[50, 57, 61, 64, 66], [47, 54, 57, 62, 66], [43, 55, 59, 62, 66], [45, 52, 57, 61, 64]]
bar = beat * 4

def env(s, L, a=0.6, r=0.9):
    return np.clip((t - s) / a, 0, 1) * np.clip((s + L + r - t) / r, 0, 1) * (t >= s)

def lowpass(x, cut):
    a = np.exp(-2 * np.pi * cut / SR); y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc; y[i] = acc
    return y

mix = np.zeros(len(t))
# pain: ticks + tense drone
st = 0.05
while st < OPEN - 0.1:
    idx = (t >= st) & (t < st + 0.05); tt = t[idx] - st
    mix[idx] += np.sin(2 * np.pi * 2600 * tt) * np.exp(-tt * 160) * 0.35
    st += beat / 2
drone = (np.sin(2 * np.pi * mf(38) * t) + 0.4 * np.sin(2 * np.pi * mf(45) * t * 1.002)) * 0.12
mix += drone * np.interp(t, [0, 0.3, OPEN - 0.3, OPEN + 0.2], [0, 1, 1, 0])
# swell into the reveal
mix += np.sin(2 * np.pi * mf(74) * t) * 0.05 * np.interp(t, [OPEN - 1.2, OPEN, OPEN + 0.3], [0, 1, 0])
# pad from the reveal
pad = np.zeros(len(t)); s = OPEN; n = 0
while s < DUR:
    ch = chords[n % 4] if s < END else chords[0]
    L = bar if s < END else DUR - s
    e = env(s, L, a=0.5 if n else 0.25, r=0.8)
    for m in ch[1:]:
        f = mf(m)
        pad += e * (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t + 1)) * 0.06
    pad += e * np.sin(2 * np.pi * mf(ch[0] - 12) * t) * 0.15
    s += L; n += 1
mix += lowpass(pad, 1600) * np.interp(t, [OPEN, END, END + 0.3, DUR - 1.5, DUR], [1, 1, 1.15, 1, 0])
# arpeggio 16ths-feel in 8ths
arp = np.zeros(len(t)); k = 0; st = OPEN
while st < END:
    ch = chords[int((st - OPEN) // bar) % 4]
    note = ch[1:][[0, 2, 1, 3, 2, 4, 3, 2][k % 8] % 4] + 12
    idx = t >= st; tt = t[idx] - st
    arp[idx] += np.sin(2 * np.pi * mf(note) * tt) * np.exp(-tt * 7) * 0.08 * (1 - np.exp(-tt * 400))
    k += 1; st += beat / 2
mix += arp
# soft thump on beats through the lifestyle run
st = 8.6
while st < END:
    idx = (t >= st) & (t < st + 0.35); tt = t[idx] - st
    mix[idx] += np.sin(2 * np.pi * (55 + 60 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 10) * 0.22
    st += beat
out = np.stack([mix, np.roll(mix, int(SR * 0.008))], 1)
out /= np.max(np.abs(out)) / 0.5
sf.write("audio/bed.wav", out, SR)
print("ok")
