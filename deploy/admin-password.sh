#!/usr/bin/env bash
# Новый пароль админки — придумывается автоматически, вводить ничего не нужно.
# Запуск:  bash ~/alphaprime/deploy/admin-password.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PW="Alpha-$(LC_ALL=C tr -dc "a-z" </dev/urandom | head -c 4 || true)-$(LC_ALL=C tr -dc "0-9" </dev/urandom | head -c 4 || true)"

touch .env
grep -v '^ADMIN_PASSWORD=' .env > .env.tmp || true
printf 'ADMIN_PASSWORD=%s\n' "$PW" >> .env.tmp
mv .env.tmp .env && chmod 600 .env

echo "→ Перезапускаю приложение…"
docker compose up -d --force-recreate api >/dev/null
sleep 3
echo
echo "========================================"
echo "  Новый пароль админки:  $PW"
echo "========================================"
echo "  Вход: https://app.alpha-prime.group/admin"
echo "  Имя — любое (например, Tesa), пароль — строка выше."
echo "  Сохраните его в заметках. Забудете — просто запустите эту команду ещё раз."
