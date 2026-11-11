#!/usr/bin/env bash
# Смена пароля админки. Запуск:  bash ~/alphaprime/deploy/admin-password.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Новый пароль для https://app.alpha-prime.group/admin ==="
echo "Только латинские буквы, цифры и знаки ! @ . _ -  (от 8 символов)."
echo "Проверьте, что на клавиатуре включена английская раскладка."
echo
while true; do
  read -r -p "Новый пароль (он будет виден на экране): " PW
  if [ ${#PW} -lt 8 ]; then echo "Слишком короткий — нужно от 8 символов."; continue; fi
  if ! printf '%s' "$PW" | grep -Eq '^[A-Za-z0-9!@._-]+$'; then
    echo "Есть недопустимые символы (русские буквы, пробелы и т.п.). Попробуйте ещё раз."; continue
  fi
  break
done

touch .env
grep -v '^ADMIN_PASSWORD=' .env > .env.tmp || true
printf 'ADMIN_PASSWORD=%s\n' "$PW" >> .env.tmp
mv .env.tmp .env && chmod 600 .env

echo "→ Перезапускаю приложение…"
docker compose up -d --force-recreate api >/dev/null
echo
echo "✓ Готово. Пароль админки: $PW"
echo "  Вход: https://app.alpha-prime.group/admin  (имя — любое, пароль — этот)"
