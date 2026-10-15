"""Draw the Crooked Crow crow and wordmark into assets/.

Run once; the PNGs are kept in the project folder. Needs Pillow and the Ubuntu
font family (free licence), which ships with most Linux desktops.

    uv run --no-project --with pillow python make_logo.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
FONTS = Path("/usr/share/fonts/truetype/ubuntu")
SCALE = 4

FEATHER = "#4a5862"
FEATHER_DARK = "#2f3a42"
FEATHER_LIGHT = "#6f7f8b"
BEAK = "#e6c445"
PICKLE = "#7cb83a"
PICKLE_DARK = "#3f7a14"
PICKLE_LIGHT = "#a6d56a"
CREAM = "#16262e"


def pickle_layer(length: int, width: int) -> Image.Image:
    """Draw one upright pickle with bumps and a highlight.

    Args:
        length: Height of the pickle in pixels.
        width: Width of the pickle in pixels.

    Returns:
        A transparent RGBA image just big enough to hold the pickle.
    """
    layer = Image.new("RGBA", (width, length), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, width - 1, length - 1), radius=width // 2, fill=PICKLE)
    d.rounded_rectangle(
        (width * 0.18, length * 0.08, width * 0.36, length * 0.7), radius=width // 6,
        fill=PICKLE_LIGHT,
    )
    for i, (fx, fy) in enumerate(
        ((0.65, 0.16), (0.5, 0.3), (0.72, 0.42), (0.52, 0.56), (0.68, 0.7), (0.5, 0.82))
    ):
        r = width * 0.07
        cx, cy = width * fx, length * fy
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=PICKLE_DARK)
    return layer


def crow(size: tuple[int, int]) -> Image.Image:
    """Draw the mascot on a transparent canvas.

    Args:
        size: Final width and height in pixels.

    Returns:
        An RGBA image of a crow with a tilted head, holding a pickle in its beak.
    """
    w, h = size[0] * SCALE, size[1] * SCALE
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = w / 1024

    def box(cx: float, cy: float, rx: float, ry: float) -> tuple:
        return ((cx - rx) * u, (cy - ry) * u, (cx + rx) * u, (cy + ry) * u)

    d.polygon([(250 * u, 400 * u), (20 * u, 560 * u), (90 * u, 640 * u), (300 * u, 520 * u)],
              fill=FEATHER_DARK)
    d.polygon([(280 * u, 450 * u), (60 * u, 640 * u), (150 * u, 680 * u), (330 * u, 540 * u)],
              fill=FEATHER)
    for x in (400, 500):
        d.line([(x * u, 600 * u), (x * u, 680 * u)], fill=BEAK, width=int(14 * u))
        for dx in (-34, 0, 34):
            d.line([(x * u, 680 * u), ((x + dx) * u, 705 * u)], fill=BEAK, width=int(12 * u))
    d.ellipse(box(450, 430, 290, 200), fill=FEATHER)
    d.ellipse(box(520, 470, 190, 120), fill=FEATHER_DARK)
    d.ellipse(box(430, 360, 150, 60), fill=FEATHER_LIGHT)
    d.ellipse(box(690, 300, 135, 130), fill=FEATHER)
    d.ellipse(box(650, 240, 60, 40), fill=FEATHER_LIGHT)

    d.polygon([(790 * u, 255 * u), (1000 * u, 320 * u), (790 * u, 335 * u)], fill=BEAK)
    pickle = pickle_layer(int(250 * u), int(84 * u)).rotate(
        14, expand=True, resample=Image.BICUBIC
    )
    img.alpha_composite(
        pickle, (int(915 * u - pickle.width / 2), int(318 * u - pickle.height / 2))
    )
    d.polygon([(790 * u, 335 * u), (975 * u, 335 * u), (790 * u, 365 * u)], fill="#c9a52e")

    d.ellipse(box(732, 275, 30, 30), fill="white")
    d.ellipse(box(740, 280, 15, 15), fill="#111111")
    d.line([(690 * u, 232 * u), (770 * u, 258 * u)], fill="#262d33", width=int(14 * u))

    return img.resize(size, Image.LANCZOS)


def lockup() -> Image.Image:
    """Draw the crow beside the company name.

    Returns:
        An RGBA lockup image about four times wider than it is tall.
    """
    height = 300
    icon = crow((430, 300))
    canvas = Image.new("RGBA", (1300, height), (0, 0, 0, 0))
    canvas.alpha_composite(icon, (0, 0))
    d = ImageDraw.Draw(canvas)
    bold = str(FONTS / "Ubuntu-B.ttf")
    d.text((450, 40), "Crooked Crow", font=ImageFont.truetype(bold, 104), fill=CREAM)
    d.text((454, 160), "PICKLING CO.", font=ImageFont.truetype(bold, 84), fill="#4f8a1f")
    return canvas.crop(canvas.getbbox())


def main() -> None:
    """Write the icon and the lockup."""
    ASSETS.mkdir(exist_ok=True)
    crow((256, 180)).save(ASSETS / "crow-icon.png")
    lockup().save(ASSETS / "crow-lockup.png")


if __name__ == "__main__":
    main()
