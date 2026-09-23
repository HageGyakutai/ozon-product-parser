# Ozon Product Parser

Тестовое задание: автоматическая авторизация в Ozon по номеру телефона с
получением кода через Gmail API и парсинг карточек товаров по списку SKU.

## Возможности

- вход на `data.ozon.ru` через номер телефона;
- поиск нового письма Ozon и получение кода через Gmail API;
- сохранение авторизованной сессии в локальный `cookies.json`;
- загрузка карточек `https://www.ozon.ru/product/{sku}/`;
- извлечение данных из HTML и встроенного JSON;
- сохранение результата в CSV или PostgreSQL;
- автоматический запуск Chrome CDP для обхода блокировки нового браузера;
- автоматический запуск локального PostgreSQL и применение миграций;
- повторная запись товара через PostgreSQL UPSERT по SKU;
- ежедневный запуск парсера через Airflow.

Парсер извлекает 12 полей:

`sku`, `title`, `price`, `rating`, `reviews_total`, `cover_image`,
`photos_seller`, `videos_seller`, `color`, `material`, `art_set`,
`has_rich_content`.

## Стек

Python 3.12, Playwright, Requests, BeautifulSoup, Gmail API, SQLAlchemy,
PostgreSQL 16, Alembic, Docker Compose, Airflow, pytest, Ruff и mypy.

## Требования

- Python 3.12.x;
- [uv](https://docs.astral.sh/uv/);
- Docker с Docker Compose;
- Google Chrome или Chromium;
- Gmail, на который Ozon отправляет код подтверждения.

## Установка

```bash
git clone git@github.com:HageGyakutai/ozon-product-parser.git
cd ozon-product-parser
uv python install 3.12
uv sync --locked
cp .env.example .env
```

Chrome должен быть установлен в системе. Скрипт автоматически ищет
`google-chrome-stable`, `google-chrome`, `chromium` или
`chromium-browser`. Если браузер установлен в другом месте, укажите полный
путь через `OZON_CHROME_EXECUTABLE`.

## Настройка Gmail API

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/).
2. Включите Gmail API.
3. Настройте OAuth consent screen.
4. Если приложение находится в режиме Testing, добавьте свой Gmail в Test users.
5. Создайте OAuth Client ID типа **Desktop application**.
6. Скачайте файл и сохраните его в корне проекта как `credentials.json`.

При первом запуске Google попросит войти в аккаунт и разрешить доступ
`gmail.readonly`. После подтверждения локально создастся `token.json`.

## Настройка окружения

Заполните `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon

OZON_PHONE=9230000000
OZON_COOKIES_FILE=cookies.json
OZON_BROWSER=chromium
OZON_BROWSER_CHANNEL=chrome
OZON_CDP_ENDPOINT=http://127.0.0.1:9222
OZON_CHROME_EXECUTABLE=
OZON_CHROME_PROFILE=
OZON_CHROME_STARTUP_DELAY=3
OZON_AIRFLOW_SKUS=2359066702,2829800382

GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json
GMAIL_QUERY=ozon
GMAIL_SENDER_DOMAINS=ozon.ru
```

Пустые `OZON_CHROME_EXECUTABLE` и `OZON_CHROME_PROFILE` означают
автоматический выбор. Отдельный профиль Chrome по умолчанию хранится в
`~/.cache/ozon-parser-chrome`.

Все секретные и локальные файлы исключены из Git: `.env`, OAuth credentials,
Gmail token, cookies и результаты парсинга.

## 1. Получение cookies

```bash
uv run python scripts/get_cookies.py
```

Скрипт:

1. проверяет параметры и Gmail API;
2. запускает Chrome с локальным CDP или подключается к работающему;
3. открывает Ozon и вводит номер телефона;
4. ждёт новое письмо Gmail;
5. извлекает и вводит код подтверждения;
6. сохраняет сессию в `cookies.json` с правами `600`.

При первой авторизации Gmail или появлении CAPTCHA потребуется действие
пользователя в открытом браузере. Код подтверждения и содержимое письма в лог
не выводятся.

Проверка:

```bash
test -f cookies.json && echo "cookies.json создан"
stat -c 'Права: %a' cookies.json
```

## 2. Парсинг в CSV

```bash
uv run python scripts/parse_ozon.py \
  2359066702 2829800382 \
  --transport browser \
  --output csv
```

Результат: `output/products.csv`.

Другой путь можно передать явно:

```bash
uv run python scripts/parse_ozon.py \
  2359066702 2829800382 \
  --transport browser \
  --output csv \
  --csv output/my-products.csv
```

CSV-режим не запускает PostgreSQL.

## 3. Парсинг в PostgreSQL

```bash
uv run python scripts/parse_ozon.py \
  2359066702 2829800382 \
  --transport browser \
  --output database
```

Перед записью скрипт:

1. проверяет PostgreSQL запросом `SELECT 1`;
2. при недоступной базе выполняет
   `docker compose up -d --wait postgres`;
3. применяет `alembic upgrade head`;
4. сохраняет товары с UPSERT по SKU.

Проверка результата:

```bash
docker compose exec -T postgres psql -U ozon -d ozon -c "
SELECT sku, title, price, rating, reviews_total, updated_at
FROM products
ORDER BY updated_at DESC;
"
```

Если инфраструктура управляется отдельно, автоматический запуск Docker можно
запретить:

```bash
uv run python scripts/parse_ozon.py \
  2359066702 \
  --transport browser \
  --output database \
  --no-start-database
```

## Requests transport

В задании требуется работа с cookies и `requests.Session`, поэтому доступен
также HTTP-транспорт:

```bash
uv run python scripts/parse_ozon.py \
  2359066702 \
  --transport requests \
  --output csv
```

Ozon может вернуть HTTP 403 автоматическому HTTP-клиенту даже с действительными
cookies. В таком случае используйте проверенный `--transport browser`.

## 4. Ежедневный запуск через Airflow

Airflow установлен в отдельной группе зависимостей и не нужен для обычного
ручного запуска парсера:

```bash
uv sync --locked --group airflow
```

Перед первым запуском Airflow один раз получите cookies:

```bash
uv run python scripts/get_cookies.py
```

Список товаров для ежедневного запуска задаётся в `.env` через запятую или
пробел:

```dotenv
OZON_AIRFLOW_SKUS=2359066702,2829800382
```

Запустите локальный Airflow:

```bash
export AIRFLOW_HOME="$PWD/.airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/dags"
uv run --group airflow airflow standalone
```

Откройте адрес, указанный Airflow в терминале, и включите DAG
`ozon_products_daily`. Он запускается ежедневно в 06:00 UTC, использует
browser-транспорт и сохраняет результат в PostgreSQL. Первый запуск можно
выполнить вручную из интерфейса Airflow.

DAG не запрашивает код авторизации ежедневно. Он использует сохранённый
`cookies.json`. Если сессия Ozon истекла, задача завершится ошибкой: повторно
запустите `get_cookies.py`, после чего перезапустите задачу Airflow.

## Проверки качества

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src scripts
uv run pytest -q
```

Тесты PostgreSQL запускаются только против отдельной базы, имя которой
заканчивается на `_test`:

```bash
docker compose up -d --wait postgres

docker compose exec -T postgres sh -c \
  'psql -U ozon -tAc "SELECT 1 FROM pg_database WHERE datname='\''ozon_test'\''" |
   grep -q 1 || createdb -U ozon ozon_test'

TEST_DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon_test \
  uv run pytest -q
```

## Структура

```text
dags/
  ozon_products_daily.py ежедневный DAG Airflow
scripts/
  get_cookies.py       авторизация и сохранение cookies
  parse_ozon.py        парсинг SKU и выбор хранилища
src/ozon_parser/
  browser_client.py    загрузка карточек через Chrome
  cdp_browser.py       запуск и проверка Chrome CDP
  client.py            requests.Session с cookies
  gmail.py             Gmail OAuth и получение кода
  extractor.py         извлечение 12 полей
  storage.py           SQLAlchemy и UPSERT
  database_runtime.py  healthcheck PostgreSQL и Alembic
  airflow_task.py       запуск существующего CLI из Airflow
alembic/               миграции PostgreSQL
tests/                 автоматические тесты
```

## Безопасность

Не добавляйте в Git и не передавайте другим людям:

- `.env`;
- `credentials.json`;
- `token.json`;
- `cookies.json`;
- содержимое писем и коды подтверждения.

CDP слушает только локальный адрес `127.0.0.1`. Проект не обходит CAPTCHA и
не должен использоваться для нарушения правил Ozon.
