from app.mail_scan import looks_like_visa


def test_looks_like_visa():
    assert looks_like_visa("Your KITAS is ready", "imigrasi", ["ITK_IVAN.pdf"])
    assert looks_like_visa("документы", "x", ["e-Visa C312 Ivanov.pdf"])
    assert not looks_like_visa("KITAS", "x", [])  # без вложения
    assert not looks_like_visa("Счёт за аренду", "x", ["invoice.pdf"])
