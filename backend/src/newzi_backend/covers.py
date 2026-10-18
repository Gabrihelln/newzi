"""Cover art of a daily edition as a PNG, for the media notification and the lock screen.

The app draws the same cover on screen (mobile/src/components/EditionCover.tsx): the stacked sheets of the
Newzi icon over a sky gradient with a sun, the period ("RESUMO DA TARDE"), the day, "N notícias · X min" and
the app seal. Android's media notification and iOS's Now Playing load artwork from a plain URL without the
user's token, so this image is public and carries no personal data: only the period, the day and two numbers.
"""
from datetime import date
from functools import lru_cache
from io import BytesIO

from .paths import PROJECT_ROOT

SIZE = 512
PERIODS = {
    "morning": ("RESUMO DA MANHÃ", ("#FF9B5E", "#B8789E", "#3D5FD6"), "#FFD27A"),
    "afternoon": ("RESUMO DA TARDE", ("#5FB2FF", "#4A86E8", "#2F4FC4"), "#FFE7A3"),
    "night": ("RESUMO DA NOITE", ("#5B4BC4", "#33307F", "#141B4D"), "#C9D6FF"),
}
WEEKDAYS = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
FONT = PROJECT_ROOT / "mobile" / "assets" / "fonts" / "Inter.ttf"
APP_ICON = PROJECT_ROOT / "mobile" / "assets" / "icon.png"


def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _font(size, weight=800):
    from PIL import ImageFont
    try:
        font = ImageFont.truetype(str(FONT), size)
        try:
            # Inter is a variable font with two axes: optical size, then weight.
            font.set_variation_by_axes([max(14, min(32, size / 2)), weight])
        except Exception:
            pass
        return font
    except OSError:
        return ImageFont.load_default()


def parse_cover_request(period, day, items, minutes):
    """Validated arguments, or ValueError: the endpoint is public, so nothing free-form reaches the image."""
    if period not in PERIODS:
        raise ValueError("period must be morning, afternoon or night")
    when = date.fromisoformat(str(day))
    items, minutes = int(items), int(minutes)
    if not 0 <= items <= 50 or not 0 <= minutes <= 180:
        raise ValueError("items or minutes out of range")
    return period, when.isoformat(), items, minutes


@lru_cache(maxsize=256)
def render_cover(period, day, items, minutes):
    """PNG bytes of the cover; identical requests reuse the rendered image."""
    from PIL import Image, ImageDraw, ImageFilter
    k = 2  # drawn at twice the size and scaled down, for smooth edges
    big = SIZE * k
    label, sky, sun = PERIODS[period]
    top, middle, bottom = (_rgb(color) for color in sky)
    # The diagonal sky gradient is computed on a small grid and smoothly enlarged.
    grid = Image.new("RGB", (32, 32))
    for y in range(32):
        for x in range(32):
            t = min(1.0, max(0.0, (y + x * .35) / (32 * 1.35)))
            a, b, u = (top, middle, t / .55) if t < .55 else (middle, bottom, (t - .55) / .45)
            grid.putpixel((x, y), tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3)))
    image = grid.resize((big, big), Image.BICUBIC).convert("RGBA")

    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((big * .26, big * .54, big * .74, big * 1.02), fill=_rgb(sun) + (235,))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(34 * k)))

    # Stacked sheets: two faded ones behind, the front one with "text" lines.
    def sheet(alpha, angle, dx, lines):
        w, h, pad = int(big * .36), int(big * .4), 30 * k
        layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle((pad, pad, pad + w, pad + h), radius=int(w * .2), fill=(255, 255, 255, alpha))
        if lines:
            draw.rounded_rectangle((pad + w * .14, pad + h * .16, pad + w * .62, pad + h * .23), radius=6 * k, fill=(31, 127, 234, 255))
            for row, width in enumerate((.86, .74, .8, .5)):
                y = pad + h * (.34 + row * .13)
                draw.rounded_rectangle((pad + w * .14, y, pad + w * (.14 + width * .72), y + h * .055), radius=5 * k, fill=(214, 226, 242, 255))
        layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
        x = int(big / 2 - layer.width / 2 + dx)
        y = int(big * .52 - layer.height / 2)
        if lines:
            mask = Image.new("L", image.size, 0)
            mask.paste(layer.split()[3], (x + 4 * k, y + 16 * k))
            shadow = Image.new("RGBA", image.size, (11, 26, 68, 0))
            shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(14 * k)).point(lambda v: int(v * .3)))
            image.alpha_composite(shadow)
        image.alpha_composite(layer, (x, y))

    sheet(97, -8, big * .1, False)
    sheet(153, -4, big * .05, False)
    sheet(255, 5, -big * .02, True)

    draw = ImageDraw.Draw(image)
    when = date.fromisoformat(day)
    draw.text((40 * k, 36 * k), label, font=_font(21 * k, 800), fill=(255, 255, 255, 230))
    draw.text((38 * k, 62 * k), f"{WEEKDAYS[when.weekday()]}, {when.day} {MONTHS[when.month - 1]}", font=_font(50 * k, 800), fill=(255, 255, 255, 255))

    pill = f"{items} {'notícia' if items == 1 else 'notícias'}" + (f" · {minutes} min" if minutes else "")
    pill_font = _font(23 * k, 700)
    width = draw.textlength(pill, font=pill_font)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle((34 * k, big - 86 * k, 34 * k + width + 40 * k, big - 38 * k), radius=24 * k, fill=(255, 255, 255, 72))
    image.alpha_composite(overlay)
    draw = ImageDraw.Draw(image)
    draw.text((54 * k, big - 76 * k), pill, font=pill_font, fill=(255, 255, 255, 255))

    try:
        seal_size = 56 * k
        seal = Image.open(APP_ICON).convert("RGBA").resize((seal_size, seal_size), Image.LANCZOS)
        mask = Image.new("L", seal.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, seal_size - 1, seal_size - 1), radius=13 * k, fill=255)
        base = Image.new("RGBA", (64 * k, 64 * k), (0, 0, 0, 0))
        ImageDraw.Draw(base).rounded_rectangle((0, 0, 64 * k - 1, 64 * k - 1), radius=16 * k, fill=(255, 255, 255, 255))
        base.paste(seal, (4 * k, 4 * k), mask)
        image.alpha_composite(base, (big - 98 * k, big - 98 * k))
    except OSError:
        pass

    image = image.resize((SIZE, SIZE), Image.LANCZOS)
    out = BytesIO()
    image.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
