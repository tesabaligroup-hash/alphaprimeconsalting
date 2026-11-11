"""Выводит воронки, этапы и поля Kommo — чтобы сверить app/kommo/mapping.py с реальной CRM.

Запуск на сервере:  docker compose exec api python -m app.kommo.inspect
"""
from ..config import get_settings
from .mapping import CONTACT_FIELDS, LEAD_FIELDS, norm
from .real import RealKommo


def main() -> None:
    s = get_settings()
    k = RealKommo(s.kommo_base_url, s.kommo_token)
    print("=== Воронки и этапы ===")
    for p in k.pipelines():
        print(f"\n[{p['id']}] {p['name']}")
        for st in (p.get("_embedded") or {}).get("statuses", []):
            print(f"   {st['id']:>10}  {st['name']}")
    for entity, wanted in (("leads", LEAD_FIELDS), ("contacts", CONTACT_FIELDS)):
        fields = k.custom_fields(entity)
        names = {norm(f["name"]) for f in fields}
        print(f"\n=== Поля: {entity} ===")
        for f in fields:
            if f["type"] == "tracking_data":
                continue  # рекламные метки — не нужны
            print(f"   {f['id']:>10}  {f['type']:<12} {f['name']}")
            enums = [e["value"] for e in (f.get("enums") or [])]
            for i in range(0, len(enums), 6):  # варианты списка — по 6 в строке, чтобы влезали в экран
                print("                 · " + ", ".join(enums[i:i + 6]))
        print("\n   Проверка mapping.py:")
        for key, name in wanted.items():
            print(f"   {'✓' if norm(name) in names else '✗ НЕ НАЙДЕНО'}  {key} = «{name}»")


if __name__ == "__main__":
    main()
