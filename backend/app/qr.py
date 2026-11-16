"""QR-код партнёра для скачивания и печати: белый фон, золотая полоса, кодовое слово крупно под кодом."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
INK, GOLD, GOLD_INK, MUTED = "#1C1A16", "#C9A24B", "#7A5C17", "#6B655A"
CHANNELS = {"tg": "Telegram", "wa": "WhatsApp", "ig": "Instagram"}


@lru_cache
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / "fonts" / name), size)


def _center(d: ImageDraw.ImageDraw, y: int, text: str, font: ImageFont.FreeTypeFont, fill: str, width: int) -> None:
    d.text(((width - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def partner_qr_png(link: str, word: str, channel: str) -> bytes:
    """PNG 1200×1560: логотип, QR (≈1000 px — чётко печатается до A4), «Я от СЛОВО», мессенджер."""
    W, H = 1200, 1560
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=GOLD)

    logo = Image.open(ASSETS / "logo.png").convert("RGBA").resize((120, 120))
    img.paste(logo, (100, 60), logo)
    d.text((240, 82), "ALPHA PRIME", font=_font("Manrope-ExtraBold.ttf", 44), fill=INK)
    d.text((240, 138), "Визы, KITAS и компании на Бали", font=_font("Manrope-SemiBold.ttf", 28), fill=MUTED)

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    code = qr.make_image(fill_color=INK, back_color="white").convert("RGB").resize((960, 960), Image.NEAREST)
    img.paste(code, ((W - 960) // 2, 230))

    _center(d, 1215, f"Я от {word}", _font("Manrope-ExtraBold.ttf", 84), INK, W)
    hint = ("Наведите камеру — откроется Direct Alpha Prime в Instagram" if channel == "ig"
            else f"Наведите камеру — откроется {CHANNELS.get(channel, channel)} менеджеров Alpha Prime")
    _center(d, 1335, hint, _font("Manrope-SemiBold.ttf", 32), GOLD_INK, W)
    _center(d, 1395, "Напишите эти слова в Direct" if channel == "ig" else "или напишите нам эти слова в любой мессенджер", _font("Manrope-SemiBold.ttf", 28), MUTED, W)
    d.rectangle([0, H - 14, W, H], fill=GOLD)

    buf = BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
