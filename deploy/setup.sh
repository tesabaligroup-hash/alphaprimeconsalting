#!/usr/bin/env bash
# Первичная настройка сервера Alpha Prime. Запуск:  bash ~/alphaprime/deploy/setup.sh
# Можно запускать повторно — существующий .env не перезаписывается без вашего согласия.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Alpha Prime: настройка сервера ==="

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
  echo "→ Устанавливаю Docker (1–2 минуты)…"
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
echo "✓ Docker установлен"

# 2. Файрвол: только SSH, HTTP и HTTPS
if command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
  echo "✓ Файрвол настроен"
fi

# 3. Файл настроек .env
write_env=yes
if [ -f .env ]; then
  read -r -p "Файл .env уже есть. Создать заново? (y/N) " ans
  [ "${ans:-n}" = "y" ] || write_env=no
fi

if [ "$write_env" = "yes" ]; then
  echo
  echo "Вставьте значения (в Web Console вставка — Ctrl+Shift+V или правая кнопка мыши)."
  read -r -p "Домен приложения [app.alpha-prime.group]: " DOMAIN; DOMAIN=${DOMAIN:-app.alpha-prime.group}
  read -r -p "Токен бота от @BotFather: " BOT_TOKEN
  read -r -p "Имя бота без @ (например AlphaPrimeBot): " BOT_USERNAME
  read -r -p "Токен Kommo (долгосрочный): " KOMMO_TOKEN
  read -r -p "Адрес Kommo [https://baliprimeconsalting.kommo.com]: " KOMMO_BASE_URL; KOMMO_BASE_URL=${KOMMO_BASE_URL:-https://baliprimeconsalting.kommo.com}
  while true; do
    read -r -s -p "Придумайте пароль для админки (от 10 символов): " ADMIN_PASSWORD; echo
    [ ${#ADMIN_PASSWORD} -ge 10 ] && break
    echo "Слишком короткий, попробуйте ещё раз."
  done
  read -r -p "Telegram компании для связи, ник без @ (можно пусто): " COMPANY_TELEGRAM
  read -r -p "Instagram компании, ник без @ (можно пусто): " COMPANY_INSTAGRAM

  umask 077
  cat > .env <<EOF
APP_DOMAIN=$DOMAIN
PUBLIC_URL=https://$DOMAIN
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
ADMIN_PASSWORD=$ADMIN_PASSWORD
BOT_TOKEN=$BOT_TOKEN
BOT_USERNAME=$BOT_USERNAME
KOMMO_BASE_URL=$KOMMO_BASE_URL
KOMMO_TOKEN=$KOMMO_TOKEN
KOMMO_MOCK=false
COMPANY_WHATSAPP=628113979669
COMPANY_TELEGRAM=$COMPANY_TELEGRAM
COMPANY_INSTAGRAM=$COMPANY_INSTAGRAM
DEV_MODE=false
EOF
  chmod 600 .env
  echo "✓ Настройки сохранены в .env (доступ только у администратора сервера)"
fi

# 4. Запуск
echo "→ Собираю и запускаю приложение (первый раз 3–5 минут)…"
docker compose up -d --build
echo
docker compose ps
DOMAIN=$(grep '^APP_DOMAIN=' .env | cut -d= -f2)
IP=$(curl -fsS -4 https://api.ipify.org 2>/dev/null || echo "?")
echo
echo "=== Готово ==="
echo "Админка:      https://$DOMAIN/admin"
echo "IP сервера:   $IP  (DNS-запись A «app» должна указывать сюда)"
echo "Если сайт ещё не открывается — подождите, пока обновится DNS: сертификат HTTPS выпустится сам."
echo
echo "Проверка полей Kommo (пришлите результат разработчику):"
echo "   cd ~/alphaprime && docker compose exec api python -m app.kommo.inspect"
