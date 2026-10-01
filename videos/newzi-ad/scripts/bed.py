# Soft ambient bed, 34s, ~96 BPM: pad + gentle arpeggio pulse from 5.5s, resolves on the logo at 28s.
import numpy as np, soundfile as sf
SR, DUR, BPM = 44100, 34.0, 96
beat = 60 / BPM
t = np.arange(int(SR * DUR)) / SR
mf = lambda m: 440 * 2 ** ((m - 69) / 12)
chords = [[50, 57, 61, 64, 66], [47, 54, 57, 62, 66], [43, 55, 59, 62, 66], [45, 52, 57, 61, 64]]  # Dmaj9 Bm7(11) Gmaj7 A
bar = beat * 4
out = np.zeros((len(t), 2))

def env(start, length, a=0.8, r=1.2):
    e = np.clip((t - start) / a, 0, 1) * np.clip((start + length + r - t) / r, 0, 1)
    return e * (t >= start)

def lowpass(x, cut):
    a = np.exp(-2 * np.pi * cut / SR); y = np.zeros_like(x); acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc; y[i] = acc
    return y

# pad: two bars per chord
pad = np.zeros(len(t))
n = 0; s = 0.0
while s < DUR:
    ch = chords[n % 4] if s < 28 else chords[0]
    L = bar * 2 if s < 28 else DUR - s
    e = env(s, L, a=1.2, r=1.4)
    for m in ch[1:]:
        f = mf(m)
        pad += e * (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t + 1) + 0.25 * np.sin(4 * np.pi * f * t)) * 0.06
    pad += e * np.sin(2 * np.pi * mf(ch[0] - 12) * t) * 0.14
    s += L; n += 1
pad = lowpass(pad, 1400)
lvl = np.interp(t, [0, 5.3, 5.8, 27.5, 28.2, 32, 34], [0.55, 0.6, 1.0, 1.0, 1.1, 0.9, 0])
pad *= lvl

# arpeggio pulse, 8th notes, 5.5s → 28s
arp = np.zeros(len(t))
k = 0; st = 5.5
while st < 28:
    ch = chords[int((st - 5.5) // (bar * 2)) % 4]
    note = ch[1:][[0, 2, 1, 3, 2, 4, 3, 2][k % 8] % 4] + 12
    idx = (t >= st)
    tt = t[idx] - st
    arp[idx] += np.sin(2 * np.pi * mf(note) * tt) * np.exp(-tt * 6) * 0.09 * (1 - np.exp(-tt * 400))
    k += 1; st += beat / 2
arp *= np.interp(t, [5.5, 7, 26, 28], [0, 1, 1, 0])

# soft kick-like thump on beats 9.0s → 27.5s
thump = np.zeros(len(t)); st = 9.0
while st < 27.5:
    idx = (t >= st) & (t < st + 0.4); tt = t[idx] - st
    thump[idx] += np.sin(2 * np.pi * (55 + 60 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9) * 0.22
    st += beat
out[:, 0] = pad + arp * 0.8 + thump
out[:, 1] = pad + np.roll(arp, int(SR * 0.012)) + thump
out /= np.max(np.abs(out)) / 0.5
fade = np.clip(t / 0.4, 0, 1)[:, None]
sf.write("audio/bed.wav", out * fade, SR)
print("ok", DUR)
