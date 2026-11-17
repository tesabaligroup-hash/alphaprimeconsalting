"""Проверка почты: какие письма с ITK/визами там есть. НИЧЕГО не меняет ни в почте, ни в Kommo.

    python -m app.mail_scan            # последние 3 года, все папки
    python -m app.mail_scan --days 365
"""
import argparse
import email
import imaplib
import re
from collections import Counter
from datetime import date, timedelta
from email.header import decode_header, make_header

from .config import get_settings

KEYWORDS = re.compile(
    r"\b(itk|itas|kitas|kitap|e-?visa|evisa|visa|виза|китас|izin tinggal|imigrasi|immigration|voa|"
    r"c31[0-9]|d1|e2[0-9]|e3[0-9][a-z]?)\b", re.I)
FILE_EXT = (".pdf", ".jpg", ".jpeg", ".png")


def _dec(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return str(v or "")


def looks_like_visa(subject: str, sender: str, filenames: list[str]) -> bool:
    files = [f for f in filenames if f.lower().endswith(FILE_EXT)]
    if not files:
        return False
    return bool(KEYWORDS.search(subject) or KEYWORDS.search(sender) or any(KEYWORDS.search(f.replace("_", " ")) for f in files))


def _folders(m: imaplib.IMAP4_SSL) -> list[str]:
    _, data = m.list()
    out = []
    for raw in data or []:
        line = raw.decode(errors="ignore")
        if "\\Noselect" in line or "\\Trash" in line or "\\Junk" in line:
            continue
        name = line.rsplit(' "|" ', 1)[-1] if ' "|" ' in line else line.rsplit(' "/" ', 1)[-1]
        out.append(name.strip())
    return out


def main(days: int) -> None:
    s = get_settings()
    if not s.mail_user or not s.mail_password:
        print("В .env нет MAIL_USER / MAIL_PASSWORD — сначала добавьте их.")
        return
    m = imaplib.IMAP4_SSL(s.mail_imap_host)
    m.login(s.mail_user, s.mail_password)
    print(f"✅ Вход в почту {s.mail_user} выполнен")
    since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
    found, senders, total = [], Counter(), 0
    for folder in _folders(m):
        if m.select(folder, readonly=True)[0] != "OK":
            continue
        _, ids = m.search(None, "SINCE", since)
        ids = ids[0].split() if ids and ids[0] else []
        total += len(ids)
        for i in ids:
            _, data = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)] BODYSTRUCTURE)")
            head = b"".join(x[1] for x in data if isinstance(x, tuple))
            raw = b"".join(b"".join(x) if isinstance(x, tuple) else x for x in data if x)
            hdr = email.message_from_bytes(head)
            subject, sender = _dec(hdr.get("Subject")), _dec(hdr.get("From"))
            files = [_dec(f) for f in re.findall(rb'"(?:filename|name)" "([^"]+)"', raw, re.I) for f in [f.decode(errors="ignore")]]
            if looks_like_visa(subject, sender, files):
                found.append((hdr.get("Date", "")[:16], sender[:40], subject[:60], ", ".join(files)[:80]))
                senders[sender] += 1
    m.logout()
    print(f"Писем за {days} дн. просмотрено: {total}. Похожи на ITK/визы (с вложением): {len(found)}\n")
    print("Чаще всего от:")
    for snd, n in senders.most_common(8):
        print(f"  {n:4}  {snd}")
    print("\nПримеры (последние 25):")
    for row in found[-25:]:
        print("  " + " | ".join(row))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3 * 365)
    main(ap.parse_args().days)
