#!/usr/bin/env bash
# «Мир Августины»: подключение сервера, бота и ИИ. Запуск:  bash ~/alphaprime/deploy/kids-setup.sh
# Можно запускать повторно — пустой ответ оставляет старое значение.
set -euo pipefail
cd "$(dirname "$0")/.."
touch .env
setv(){ grep -v "^$1=" .env > .env.tmp || true; echo "$1=$2" >> .env.tmp; mv .env.tmp .env; chmod 600 .env; }
getv(){ grep "^$1=" .env | tail -1 | cut -d= -f2- || true; }

echo "=== Мир Августины: настройка ==="
KEY=$(getv KIDS_KEY)
if [ -z "$KEY" ]; then KEY="ava-$(openssl rand -hex 4)"; setv KIDS_KEY "$KEY"; fi

echo "Вставка в Web Console — Ctrl+Shift+V или правая кнопка мыши."
read -r -p "Токен нового бота от @BotFather (Enter — оставить как есть): " T
# убираем пробелы и невидимые символы, которые добавляет вставка в Web Console
T=$(printf %s "$T" | sed 's/\x1b\[20[01]~//g' | tr -cd 'A-Za-z0-9:_-'); [ -n "$T" ] && setv KIDS_BOT_TOKEN "$T"
read -r -p "Ключ Claude API (sk-ant-…, Enter — оставить как есть): " A
A=$(printf %s "$A" | sed 's/\x1b\[20[01]~//g' | tr -cd 'A-Za-z0-9_-'); [ -n "$A" ] && setv ANTHROPIC_API_KEY "$A"

echo "→ Собираю и запускаю (1–3 минуты)…"
docker compose up -d --build kids-api caddy
sleep 3
BOTNAME=""
T=$(getv KIDS_BOT_TOKEN | tr -cd 'A-Za-z0-9:_-'); [ -n "$T" ] && setv KIDS_BOT_TOKEN "$T"
if [ -n "$T" ]; then BOTNAME=$(curl -fsS "https://api.telegram.org/bot$T/getMe" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p' || true); fi

echo
echo "=== Готово ==="
echo "Семейный код:   $KEY"
echo "1) На iPad: «Для мамы» (PIN) → «Связь» → введи код → «Подключить»"
echo "2) Кабинет мамы на телефоне: https://kids.alpha-prime.group/#mama → тот же код"
if [ -n "$BOTNAME" ]; then
  echo "3) Telegram: открой @$BOTNAME и отправь:  /start $KEY"
else
  echo "3) Бот не подключён: токен не подошёл. Запусти скрипт ещё раз и вставь токен заново."
fi
[ -n "$(getv ANTHROPIC_API_KEY)" ] && echo "ИИ-проверка комнаты и комментарий к сводке: включены" || echo "ИИ не подключён (можно добавить позже, запустив скрипт ещё раз)"
