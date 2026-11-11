# Alpha Prime — Telegram-приложение

Личный кабинет клиента + партнёрская программа в Telegram (Mini App), с админкой и интеграцией с Kommo.

- **Mini App** — `https://app.alpha-prime.group` (открывается из бота)
- **Админка** — `https://app.alpha-prime.group/admin`
- **Бот** — привязка клиента по номеру телефона, ссылки партнёров, уведомления

## Как устроено

```
backend/   FastAPI: API для приложения, админка, бот (aiogram), синхронизация с Kommo
frontend/  Mini App (React + Vite)
deploy/    Caddy — HTTPS
docker-compose.yml   db (PostgreSQL) · api · worker (бот + синхронизация) · caddy · backup
```

Сделки, этапы, оплаты и файлы клиентов берутся из Kommo — в базе приложения их нет.
В базе: пользователи Telegram, партнёры, рекомендации, начисления, новости, стоп-слова.

Соответствие полей и этапов Kommo — в `backend/app/kommo/mapping.py`. Проверить его с реальной CRM:

```bash
docker compose exec api python -m app.kommo.inspect
```

## Запуск сервера (один раз)

Нужен VPS: Ubuntu 22.04/24.04, 2 ГБ памяти (Hetzner, DigitalOcean и т.п.).

1. **DNS.** В настройках домена `alpha-prime.group` добавьте запись `A`: имя `app` → IP сервера.
2. **Docker на сервере:**
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
3. **Код и настройки:**
   ```bash
   git clone https://github.com/tesabaligroup-hash/alphaprimeconsalting ~/alphaprime
   cd ~/alphaprime
   cp .env.example .env && nano .env      # заполнить все поля
   docker compose up -d --build
   ```
   Через 1–2 минуты откроется `https://app.alpha-prime.group/admin`.
4. **Бот.** В @BotFather: `/mybots` → бот → *Bot Settings* → *Configure Mini App* → URL `https://app.alpha-prime.group`.

### Автоматическая выкладка из GitHub

После каждого изменения в ветке `main` GitHub прогоняет тесты и обновляет сервер.

1. На сервере создайте ключ: `ssh-keygen -t ed25519 -f ~/.ssh/deploy -N ""` и `cat ~/.ssh/deploy.pub >> ~/.ssh/authorized_keys`.
2. В GitHub → репозиторий → *Settings → Secrets and variables → Actions*:
   - секреты `SSH_HOST` (IP сервера), `SSH_USER` (пользователь), `SSH_KEY` (содержимое `~/.ssh/deploy`);
   - во вкладке *Variables* — `DEPLOY_ENABLED` = `true`.

## Разработка

```bash
cd backend && pip install -r requirements.txt pytest
DEV_MODE=true KOMMO_MOCK=true ADMIN_PASSWORD=secret uvicorn app.main:app --reload   # тестовые данные
python -m pytest -q
cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

В режиме `DEV_MODE` приложение открывается в браузере без Telegram (тестовый пользователь «Анна»).

## Резервные копии

Контейнер `backup` раз в сутки сохраняет базу в `~/alphaprime/backups` (хранятся 30 дней).
Восстановление: `gunzip -c backups/db-ДАТА.sql.gz | docker compose exec -T db psql -U alphaprime alphaprime`.
