# Ozon Product Parser

Учебное тестовое решение: авторизованная сессия Ozon, извлечение встроенного JSON из HTML карточек, сохранение товаров в PostgreSQL с UPSERT по SKU. CSV доступен дополнительно.

**Статус:** структура JSON в реальных карточках, авторизация и полный запуск с PostgreSQL пока не подтверждены. Без проверки с авторизованной сессией этот проект нельзя считать готовым к сдаче работодателю. Доступ к Ozon из среды разработки возвращал повторяющиеся редиректы вместо HTML товара; обработчик JSON покрыт локальными примерами Schema.org Product. Отдельные поля `photos_seller` и `videos_seller` могут отсутствовать в Schema.org: число картинок в `image` не обязательно соответствует числу фотографий продавца. Эти поля следует сверить с реальным Ozon JSON перед сдачей.

## Установка

Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker Compose. Из корня проекта:

```bash
uv sync --locked
uv run playwright install chromium
cp .env.example .env
```

Пароль в `.env.example` предназначен только для локального контейнера; задайте собственные значения для других окружений. Файл `.env` исключён из Git.

## PostgreSQL

```bash
docker compose up -d postgres
# дождитесь статуса healthy: docker compose ps
uv run alembic upgrade head
```

В `.env` установите `DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon`. PostgreSQL 16, SQLAlchemy 2, psycopg 3; миграция создаёт `products` с уникальным индексом `sku`, NUMERIC для цены и рейтинга, nullable характеристиками и timestamptz для дат. Повторное сохранение выполняет `ON CONFLICT (sku) DO UPDATE`.

## Авторизация и Gmail

```bash
uv run python scripts/get_cookies.py
# опционально: uv run python scripts/get_cookies.py --gmail
```

В открытом браузере самостоятельно пройдите вход по номеру телефона и подтвердите вход. Затем вернитесь в терминал и нажмите Enter. Скрипт сохранит cookies в `cookies.json` с доступом только владельцу. Успех входа определяется пользователем; скрипт проверяет лишь наличие cookies домена Ozon.

Для `--gmail`: создайте проект в Google Cloud, включите Gmail API, создайте OAuth Client ID типа Desktop, скачайте JSON в `credentials.json`. При первом запуске подтвердите доступ `gmail.readonly` через Google OAuth. Код из нового письма Ozon будет показан в локальном терминале; в браузер его нужно ввести самостоятельно. `credentials.json`, `token.json` и `cookies.json` не коммитятся. Gmail API может потребовать настройки тестового пользователя на экране согласия OAuth.

## Парсинг

```bash
uv run python scripts/parse_ozon.py 2359066702 2829800382
uv run python scripts/parse_ozon.py 2359066702 2829800382 --csv output/products.csv
```

Один `requests.Session` загружает сохранённые cookies и делает запросы карточек. Только успешно распознанные товары записываются в PostgreSQL. При ошибке хотя бы одного SKU команда завершается с кодом 1 и пишет ошибку в лог. CSV содержит успешно записанные товары из данного запуска.

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

Тест записи в PostgreSQL требует отдельную пустую БД. Создайте её и выполните:

```bash
docker compose exec postgres createdb -U ozon ozon_test
TEST_DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon_test uv run pytest -q
```

Тест удаляет созданную таблицу `products` после выполнения; **не используйте основную БД** для `TEST_DATABASE_URL`.

## Ограничения

Парсер не обходит антибот-защиту и CAPTCHA. Извлечение дополнительных полей зависит от фактического формата JSON авторизованной страницы. Авторизацию, получение Gmail-кода, извлечение всех 12 полей из Ozon и end-to-end тест с PostgreSQL нужно проверить на реальных SKU перед отправкой. Airflow и DataLens пока не добавлены.
