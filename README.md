# Ozon Product Parser

Подробное соответствие заданию и незавершённые проверки: [аудит](docs/task-audit.md).

Учебное тестовое решение: авторизованная сессия Ozon, извлечение встроенного JSON из HTML карточек, сохранение товаров в PostgreSQL с UPSERT по SKU. CSV доступен дополнительно.

**Статус:** структура JSON в реальных карточках, авторизация и полный запуск с PostgreSQL пока не подтверждены. Без проверки с авторизованной сессией этот проект нельзя считать готовым к сдаче работодателю. В WSL Ozon возвращает `Antibot Challenge Page` как Chromium, так и Firefox ещё до авторизации; HTML карточки не получен. Обработчик JSON покрыт локальными примерами Schema.org Product, проверяет совпадение SKU и не сохраняет HTML блокировки как товар. Отдельные поля `photos_seller` и `videos_seller` могут отсутствовать в Schema.org: число картинок в `image` не обязательно соответствует числу фотографий продавца. Эти поля следует сверить с реальным Ozon JSON перед сдачей.

## Установка

Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker Compose. Из корня проекта:

```bash
uv sync --locked
uv run playwright install chromium
cp .env.example .env
```

Пароль в `.env.example` предназначен только для локального контейнера; задайте собственные значения для других окружений. Файл `.env` исключён из Git.

## PostgreSQL

Один запуск **после появления действительного `cookies.json`**: Compose поднимет PostgreSQL, дождётся статуса healthy, выполнит Alembic и только затем запустит парсер. Коды SKU передаются последними аргументами:

```bash
docker compose run --build --rm parser 2359066702 2829800382
```

Если cookies пока нет, можно одной командой подготовить только PostgreSQL и таблицу `products`:

```bash
docker compose up --build --exit-code-from migrate migrate
```

При запуске парсера контейнер читает локальный `cookies.json` только для чтения. Файл не копируется в Docker-образ. Без действительных cookies или при отказе Ozon парсер завершится ошибкой.

При локальном запуске Python вне Compose в `.env` установите `DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon`. PostgreSQL 16, SQLAlchemy 2, psycopg 3; миграция создаёт `products` с уникальным индексом `sku`, NUMERIC для цены и рейтинга, nullable характеристиками и timestamptz для дат. Повторное сохранение выполняет `ON CONFLICT (sku) DO UPDATE`.

## Авторизация и Gmail

В `.env` заполните `OZON_PHONE` и пути к файлам Gmail OAuth. Создайте проект в Google Cloud, включите Gmail API, создайте OAuth Client ID типа Desktop и сохраните его как `credentials.json`. На первом запуске официальная библиотека Google попросит разрешить доступ `gmail.readonly` через браузер. Файлы `credentials.json`, `token.json` и `cookies.json` исключены из Git.

`GMAIL_QUERY` задаёт поисковый запрос Gmail (по умолчанию `ozon`), а `GMAIL_SENDER_DOMAINS` — допустимые домены адреса отправителя через запятую (по умолчанию `ozon.ru`, включая поддомены). Отбор по адресу и времени получения выполняется дополнительно после поиска Gmail. Реальный домен отправителя подтвердите на письме своего аккаунта и при необходимости настройте; содержимое писем и коды не журналируются.

```bash
uv run python scripts/get_cookies.py
```

Для проверки входа в установленном на Windows Google Chrome укажите в `.env` `OZON_BROWSER_CHANNEL=chrome` и запустите ту же команду из Windows. Chrome должен быть установлен на Windows. Это отдельный автоматизированный сеанс браузера.

Для Firefox установите браузер командой `uv run playwright install firefox`, затем задайте в `.env` `OZON_BROWSER=firefox` и уберите `OZON_BROWSER_CHANNEL`. Также поддерживаются `chromium` (по умолчанию) и `webkit`; это позволяет запускать скрипт в Windows, Linux и macOS при наличии браузера и системных зависимостей. Доступность страницы Ozon проверяется отдельно для каждой среды.

Скрипт открывает `data.ozon.ru`, переходит к авторизации, вводит `OZON_PHONE`, запрашивает новый код, считывает его через Gmail API и вводит в браузер. Cookies сохраняются только после возврата на `data.ozon.ru`; это подтверждение перехода, но окончательную пригодность cookies проверяет загрузка карточки. Код и номер не записываются в логи. Ожидаемые элементы формы и реальный сценарий входа **пока не подтверждены**: Ozon блокирует браузеры Playwright до авторизации. Если Ozon отказывает браузеру, программа прекращает вход без сохранения cookies; уточните разрешённый способ доступа у заказчика или в поддержке Ozon.

## Парсинг

```bash
uv run python scripts/parse_ozon.py 2359066702 2829800382
uv run python scripts/parse_ozon.py 2359066702 2829800382 --csv output/products.csv
```

Один `requests.Session` загружает сохранённые cookies и делает запросы карточек. Только успешно распознанные товары записываются в PostgreSQL. При ошибке хотя бы одного SKU команда завершается с кодом 1 и пишет ошибку в лог. CSV содержит успешно записанные товары из данного запуска.

Для работы с уже сохранённой HTML-карточкой без подключения к Ozon и без `cookies.json` укажите ровно один SKU. Используются тот же `extract_product()` и та же запись в PostgreSQL; база должна быть доступна и миграция применена:

```bash
uv run python scripts/parse_ozon.py 2359066702 --html-file captured.html
```

В обычном режиме HTML страницы не сохраняется. При диагностике можно явно включить сохранение копии после успешной загрузки карточки:

```bash
uv run python scripts/parse_ozon.py 2359066702 --debug-html-dir output/debug
```

Диагностическая копия удаляет формы, неиспользуемые скрипты, атрибуты и типичные ключи с токенами, cookies, телефонами и email. Это **не гарантия полной анонимизации**: произвольные личные данные внутри JSON или текста могут остаться. Проверяйте файл вручную перед передачей и не добавляйте HTML с живой сессией в Git. Каталог `output/` и файлы `*.html` исключены из Git.

Проверить данные:

```bash
docker compose exec postgres psql -U ozon -d ozon -c 'SELECT sku, title, price, rating, reviews_total, updated_at FROM products ORDER BY updated_at DESC;'
```

## Тесты

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

CI автоматически собирает образ, дожидается PostgreSQL, применяет миграцию, проверяет появление `products` и запускает pytest на отдельной PostgreSQL-базе. Локально тест записи в PostgreSQL требует отдельную пустую БД. Создайте её и выполните:

```bash
docker compose exec postgres createdb -U ozon ozon_test
TEST_DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon_test uv run pytest -q
```

Тесты требуют PostgreSQL-базу с именем, заканчивающимся на `_test`. Схема создаётся Alembic, изменения каждого теста откатываются отдельной транзакцией. Основную БД использовать нельзя. Проверяются миграция, INSERT, повторный SKU, Decimal/price, rating/reviews, NULL, rich content, media counts, created_at и восстановление после ошибки записи.

## Ограничения

Парсер не обходит антибот-защиту и CAPTCHA. Извлечение дополнительных полей зависит от фактического формата JSON авторизованной страницы. Авторизацию, получение Gmail-кода, извлечение всех 12 полей из Ozon и end-to-end тест с PostgreSQL нужно проверить на реальных SKU перед отправкой. Airflow и DataLens пока не добавлены.
