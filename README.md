# Ozon Product Parser

Подробное соответствие заданию и незавершённые проверки: [аудит](docs/task-audit.md).

Учебное тестовое решение: авторизованная сессия Ozon, извлечение встроенного JSON из HTML карточек и явный выбор сохранения результата в PostgreSQL либо CSV.

**Статус:** 23 сентября 2026 года на реальном аккаунте подтверждён полный вход: Ozon ID запросил код по номеру телефона, Gmail API нашёл новое письмо, скрипт ввёл код и сохранил cookies. Из-за Ozon AntiBot проверка выполнена через подключение Playwright к отдельному обычному Chrome по CDP; запуск нового автоматизированного браузера может быть заблокирован. Реальный HTML карточки также успешно разобран `extractor.py` и записан в PostgreSQL с повторным UPSERT. Live-загрузка карточек остаётся зависимой от антибот-защиты Ozon. GitHub Actions временно не запускается из-за исчерпанного лимита Actions, поэтому актуальная проверка выполняется локально.

## Установка

Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker Compose. Из корня проекта:

```bash
uv sync --locked
uv run playwright install chromium
cp .env.example .env
```

Пароль в `.env.example` предназначен только для локального контейнера; задайте собственные значения для других окружений. Файл `.env` исключён из Git.

### Что заполнить в `.env`

| Переменная | Значение |
|---|---|
| `OZON_PHONE` | **Ваш** номер для входа в Ozon: 10–15 цифр, допускается начальный `+`. Не подставляйте номер другого человека. |
| `GMAIL_CREDENTIALS_FILE` | Скачанный из Google Cloud OAuth Desktop JSON, обычно `credentials.json` в корне проекта. |
| `GMAIL_TOKEN_FILE` | Обычно `token.json`; создаётся после разрешения доступа к выбранному Gmail. При смене ящика авторизуйте другой токен. |
| `GMAIL_QUERY` | Поисковое слово в письме, по умолчанию `ozon`. |
| `GMAIL_SENDER_DOMAINS` | Домены адреса отправителя через запятую, по умолчанию `ozon.ru`; сверяйте с реальным письмом. |
| `OZON_COOKIES_FILE` | Локальный файл сессии, обычно `cookies.json`; создаётся после входа. |
| `OZON_BROWSER` | Движок Playwright: `chromium` по умолчанию, также поддерживаются `firefox` и `webkit`. |
| `OZON_BROWSER_CHANNEL` | Для системного Chrome укажите `chrome`; оставьте пустым для браузера Playwright. |
| `OZON_CDP_ENDPOINT` | Локальный endpoint общего Chrome, по умолчанию `http://127.0.0.1:9222`. |
| `OZON_CHROME_EXECUTABLE` | Необязательный полный путь к Chrome, если он не найден автоматически. |
| `OZON_CHROME_PROFILE` | Необязательный каталог отдельного профиля; по умолчанию `~/.cache/ozon-parser-chrome`. |
| `DATABASE_URL` | При локальном запуске адрес PostgreSQL на `localhost:5432` из `.env.example`. Контейнеры Compose используют свой `DATABASE_URL` из `compose.yaml`. |

Порядок первого запуска: настройте Gmail → проверьте `check_gmail.py` → подготовьте PostgreSQL → получите cookies через `get_cookies.py` → выполните `parse_ozon.py` с нужными SKU. Каждый шаг описан ниже. Файлы с токенами и cookies не коммитьте.

## PostgreSQL

Docker Compose используется только для инфраструктуры: PostgreSQL и отдельного
ручного сервиса миграций. Основной парсер остаётся обычным Python-скриптом, чтобы
его можно было позднее вызывать из Airflow.

При выборе PostgreSQL:

```bash
uv run python scripts/parse_ozon.py \
  2359066702 2829800382 \
  --transport browser \
  --output database
```

Скрипт выполняет последовательность автоматически:

1. проверяет соединение с PostgreSQL запросом `SELECT 1`;
2. если база недоступна, запускает `docker compose up -d --wait postgres`;
3. дожидается успешного healthcheck контейнера;
4. применяет `alembic upgrade head`;
5. повторно проверяет соединение и сохраняет товары с UPSERT по SKU.

Если PostgreSQL уже работает, Docker повторно не запускается. Миграции всё равно
приводятся к актуальной версии перед записью.

Для будущего Airflow или другого окружения, где инфраструктура управляется
отдельно, автоматический запуск Docker можно запретить:

```bash
uv run python scripts/parse_ozon.py \
  2359066702 2829800382 \
  --output database \
  --no-start-database
```

В этом режиме недоступная база приводит к понятной ошибке, а не к запуску Docker.

Поднять PostgreSQL вручную можно командой:

```bash
docker compose up -d --wait postgres
```

Отдельно применить миграции в контейнере:

```bash
docker compose up --build --exit-code-from migrate migrate
```

При локальном запуске в `.env` используется
`DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon`.
PostgreSQL 16, SQLAlchemy 2, psycopg 3; миграция создаёт `products` с уникальным
индексом `sku`. Повторное сохранение выполняет `ON CONFLICT (sku) DO UPDATE`.

## Авторизация и Gmail

В `.env` заполните `OZON_PHONE` и пути к файлам Gmail OAuth. **До настройки убедитесь, что Ozon отправляет код входа именно на выбранный Gmail:** привязка Gmail сама по себе этого не гарантирует. Создайте проект в Google Cloud, включите Gmail API, создайте OAuth Client ID типа Desktop и сохраните его как `credentials.json`. API key и Service Account не заменяют OAuth Desktop Client. На первом запуске владелец ящика разрешает `gmail.readonly` через браузер. Файлы `credentials.json`, `token.json` и `cookies.json` исключены из Git.

Проверка Gmail отдельно от Ozon (в WSL, если проект запускается в WSL):

1. В своём Google Cloud проекте включите Gmail API, настройте экран согласия OAuth и добавьте свой Gmail как тестового пользователя, если приложение в режиме Testing. Создайте OAuth Client ID **Desktop application**, скачайте JSON в корень репозитория под именем `credentials.json`.
2. Выполните `uv sync --locked`, затем `uv run python scripts/check_gmail.py`. В WSL скрипт выводит одну ссылку для входа: откройте её вручную в браузере на том же компьютере и оставьте терминал работающим до завершения входа. В остальных средах скрипт попробует открыть браузер сам. Войдите именно в Gmail, на который приходит код Ozon, и разрешите доступ на чтение писем. Скрипт вызовет `users.getProfile` и подтвердит, что токен работает, не показывая адрес ящика. `token.json` создаётся локально для следующих запусков.
3. Когда реально запрашивается **новый** код Ozon, можно проверить весь путь чтения командой `uv run python scripts/check_gmail.py --wait-for-code --timeout 180`. Она учитывает только письма, доставленные **после запуска ожидания**, проверяет адрес отправителя и наличие кода, но не выводит код или письмо в терминал. Без нового письма команда закончится таймаутом. Эта команда не запрашивает код у Ozon и не заменяет `get_cookies.py`.

Для первого Desktop OAuth входа нужен браузер с доступом к локальному порту запущенного скрипта. В WSL можно использовать браузер Windows на том же компьютере, если он открывает адрес `localhost` из OAuth перенаправления. Для проверки на своём аккаунте нужны собственные `credentials.json` и действие владельца Gmail; ни один из этих файлов не передавайте в чат.

Если Ozon присылает код на другой почтовый сервис, `check_gmail.py` сможет проверить доступ к Gmail, но **не сможет получить письмо Ozon**. По этому ТЗ нужен именно Gmail; возможность изменить способ получения кода следует согласовать с заказчиком.

`GMAIL_QUERY` задаёт поисковый запрос Gmail (по умолчанию `ozon`), а `GMAIL_SENDER_DOMAINS` — допустимые домены адреса отправителя через запятую (по умолчанию `ozon.ru`, включая поддомены). Отбор по адресу и времени получения выполняется дополнительно после поиска Gmail. Реальный домен отправителя подтвердите на письме своего аккаунта и при необходимости настройте; содержимое писем и коды не журналируются.

Секретные `credentials.json`, `token.json`, `cookies.json` и `.env` храните только локально и не отправляйте вместе с проектом. Новая версия файла cookies содержит `user_agent` и cookies с доменом, путём, флагом `secure` и сроком действия. `requests.Session` использует сохранённый User-Agent и пропускает истёкшие cookies; старый формат списка cookies читается без восстановления браузерного User-Agent. Существование файла cookies не подтверждает успешный вход: защищённая проверка ещё не реализована.

```bash
uv run python scripts/get_cookies.py
```

Для Chromium рекомендуется общий Chrome CDP. Оба скрипта — `get_cookies.py`
и `parse_ozon.py --transport browser` — используют один механизм. Они сначала
проверяют `OZON_CDP_ENDPOINT`. Если Chrome не запущен, программа сама находит
Google Chrome/Chromium, запускает его с отдельным профилем, ждёт готовности
порта и затем продолжает работу. Вручную запускать команду Chrome больше не
нужно.

Рекомендуемые настройки:

```dotenv
OZON_BROWSER=chromium
OZON_BROWSER_CHANNEL=chrome
OZON_CDP_ENDPOINT=http://127.0.0.1:9222
```

Если Chrome установлен нестандартно, укажите полный путь:

```dotenv
OZON_CHROME_EXECUTABLE=/полный/путь/к/google-chrome
```

Профиль по умолчанию хранится в `~/.cache/ozon-parser-chrome`. CDP слушает
только loopback-адрес; не публикуйте порт `9222` в сеть. Если Ozon покажет
CAPTCHA или проверку браузера, её по-прежнему необходимо пройти вручную в
автоматически открытом окне. После этого тот же профиль повторно используется
для входа и парсинга.

Скрипт автоматизирует основной сценарий: открывает `data.ozon.ru`, вводит `OZON_PHONE`, запрашивает новый код, считывает его через Gmail API, вводит в Ozon ID и сохраняет cookies после возврата. Полный сценарий подтверждён на реальном аккаунте через Chrome CDP. Ручное действие по-прежнему требуется для первой OAuth-авторизации Gmail и для CAPTCHA/проверки браузера, которую может потребовать Ozon. Код и номер не записываются в логи. Вход только через `requests` не реализован, поскольку Ozon ID/SSO и антибот требуют браузерный контекст.

## Парсинг

### Проверка с cookies из обычного браузера

Если автоматизированный вход остановился на проверке браузера, можно отдельно проверить **парсинг карточек** с собственной сессией. Войдите в Ozon обычным браузером и сохраните cookies для `ozon.ru` и его поддоменов как локальный JSON-массив объектов с `name`, `value`, `domain`, `path`, `secure` и `expirationDate` (или `expires`). Не используйте `document.cookie`: он не видит HttpOnly cookies. Сохраните экспорт как `browser-cookies.json` в корне проекта. В консоли того же браузера выполните `navigator.userAgent` и скопируйте значение:

```bash
uv run python scripts/import_browser_cookies.py browser-cookies.json --user-agent 'строка navigator.userAgent'
uv run python scripts/parse_ozon.py 2359066702 2829800382 \
  --output csv --csv output/products.csv
```

Экспорт и `cookies.json` держите только локально, никому не отправляйте; после проверки удалите экспорт.

Если импорт завершился сообщением, что `cookies.json` является каталогом, сначала проверьте путь командой `ls -ld cookies.json`. Такой каталог мог остаться после ранней версии Compose, где файловый bind mount использовал короткий синтаксис и Docker мог создать отсутствующий host path как каталог. Текущий `compose.yaml` использует `create_host_path: false`, поэтому новый каталог автоматически создаваться не должен. Скрипт не удаляет каталоги автоматически, чтобы не потерять данные. Если это действительно случайно созданный **пустой** каталог, удалите его командой `rmdir cookies.json` и повторите импорт. Не используйте `rm -rf` без проверки содержимого. Скрипт фильтрует домены Ozon и проверяет срок cookies перед сохранением с правами доступа владельца. Даже настоящие cookies могут не дать доступ через `requests.Session`, если Ozon проверяет браузер: парсер сообщит об ошибке. Успешный парсинг через импорт подтвердит вторую часть ТЗ, но вход по телефону и Gmail-коду останется отдельной проверкой.

Live-проверка с импортированными cookies уже показала, что файл сессии корректно читается клиентом, но первый запрос карточки завершился до extractor. Диагностика различает случаи: HTTP 401 означает неавторизованную/истёкшую сессию; HTTP 403 не считается доказательством плохих cookies, потому что Ozon может запрещать именно автоматический HTTP-клиент; antibot-страница сообщается отдельно. В этих случаях запись в PostgreSQL ожидаемо не выполняется.

На текущей live-проверке `requests.Session` получил HTTP 403 при корректно загруженных cookies. Поэтому для честной проверки карточки добавлен отдельный браузерный transport через Playwright. Он использует тот же `cookies.json`, тот же сохранённый User-Agent и тот же `extract_product()`; это не подтверждает автоматический вход через Gmail, а только вторую часть задания с уже готовой авторизованной сессией.

Запуск браузерного транспорта:

```bash
uv run playwright install chromium
uv run python scripts/parse_ozon.py 2359066702 \
  --transport browser \
  --debug-html-dir output/debug
```

По умолчанию браузер видимый, чтобы не скрывать возможную проверку Ozon. Для headless режима добавьте `--browser-headless`. Используются `OZON_BROWSER` и `OZON_BROWSER_CHANNEL` из окружения; например, при доступном системном Chrome можно задать `OZON_BROWSER=chromium` и `OZON_BROWSER_CHANNEL=chrome`. Если Playwright также получает antibot/403, это фиксируется как ограничение live-доступа, а не маскируется под ошибку extractor.

Live-проверка Playwright-launched Chromium также вернула HTTP 403 до extractor. Для следующей диагностики поддерживается подключение к **внешнему обычному Chrome** через Chrome DevTools Protocol (CDP). Playwright официально поддерживает `connect_over_cdp()`; в этом режиме Chrome запускается отдельно, а parser подключается к существующему default context, добавляет cookies из `cookies.json` и использует тот же extractor. Это по-прежнему не подтверждает автоматический login через Gmail.

Пример запуска отдельного Chrome с remote debugging на Windows (PowerShell; используйте отдельный временный профиль, не основной профиль Chrome):

```powershell
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chrome)) {
    $chrome = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
}
& $chrome --remote-debugging-port=9222 --user-data-dir="$env:TEMP\ozon-parser-cdp"
```

Пока этот Chrome открыт, проверьте из среды запуска parser, что endpoint доступен, затем задайте:

```bash
OZON_CDP_ENDPOINT=http://127.0.0.1:9222 \
OZON_BROWSER=chromium \
uv run python scripts/parse_ozon.py 2359066702 \
  --transport browser \
  --debug-html-dir output/debug
```

Если WSL не видит Windows endpoint через `127.0.0.1`, не открывайте debug-порт наружу без необходимости. Сначала используйте обычные локальные способы WSL/Windows networking либо запустите parser в той же ОС, где запущен Chrome. CDP endpoint предоставляет полный контроль над браузером, поэтому его нельзя публиковать или оставлять доступным из внешней сети.

На проверенной Windows-машине внешний Chrome запускался с `--remote-debugging-port=9222`, но порт не открывался. Диагностика показала системную Chrome policy `HKLM\\Software\\Policies\\Google\\Chrome\\RemoteDebuggingAllowed = 0`. При такой политике CDP недоступен независимо от WSL networking. Проект не пытается обходить системную политику. В этом окружении для проверки extractor используйте HTML реальной карточки, сохранённый вручную из обычного Chrome, и offline режим `--html-file`. Такой тест подтверждает разбор реальной структуры карточки и запись в PostgreSQL, но не подтверждает автоматизированную загрузку карточки.

Безопасный offline-порядок:
1. В обычном Chrome откройте нужную реальную карточку Ozon и дождитесь полной загрузки.
2. Сохраните HTML локально как `real-product.html` (не добавляйте файл в Git и не отправляйте его без ручной проверки на персональные данные).
3. Перенесите файл в рабочую директорию WSL.
4. Выполните `uv run python scripts/parse_ozon.py <SKU> --html-file real-product.html`.
5. Проверьте строку в PostgreSQL.

На реальном HTML SKU `2359066702` подтверждены успешный INSERT и повторный UPSERT: сохранился тот же `id` и `created_at`, а `updated_at` изменился. После DOM-fallback дополнительно подтверждены `color=Темно-розовый` и `material=Бумага`. Сейчас на реальном HTML подтверждены одиннадцать полей: `sku`, `title`, `price`, `rating`, `reviews_total`, `cover_image`, `photos_seller=19`, `videos_seller=2`, `color=Темно-розовый`, `material=Бумага`, `has_rich_content=true`. `photos_seller` и `videos_seller` получены из реального `state-webGallery-*/data-state` (`images=19`, `videos=2`), а `has_rich_content=true` подтверждён наличием изображений внутри `webDescription`. Для этого SKU `art_set` отсутствует; extractor уже умеет читать его из `Артикул производителя` / `Art set` / `Комплектация` / `Состав набора`, но нужен другой реальный SKU с такой характеристикой, если требуется подтверждение непустого значения.

Для безопасного анализа структуры реального HTML без вывода значений используйте:

```bash
uv run python scripts/inspect_product_html.py real-product.html 2359066702
```

Инспектор выводит только JSON-пути, имена ключей, типы контейнеров, названия целевых характеристик и безопасные структурные счётчики внутри product/media widgets; значения полей не печатаются.

На реальной карточке инспектор подтвердил DOM-метки `Цвет` и `Материал`. Extractor теперь использует DOM-fallback для `color`, `material` и `art_set`, если эти поля отсутствуют в выбранном JSON product state. JSON остаётся приоритетным источником. Для media/rich-content требуется дальнейшая проверка внутреннего Ozon state; обновлённый инспектор выводит целевые `SCRIPT_KEYS`, `DOM_WIDGETS` и сводные маркеры без значений.

Для media extractor дополнительно читает JSON из `div[id^="state-webGallery-"][data-state]`: длина массива `images` используется как `photos_seller`, `videos` — как `videos_seller`, если явные поля отсутствуют в основном product state. На реальном SKU `2359066702` этот путь подтверждён: `images=19`, `videos=2`, и те же значения сохранены в PostgreSQL. `has_rich_content` получает DOM-fallback только при наличии медиа/таблиц/списков внутри `webDescription`; на той же карточке `webDescription` содержит 4 изображения, поэтому в PostgreSQL сохранено `has_rich_content=true`.

```bash
uv run python scripts/parse_ozon.py 2359066702 2829800382
uv run python scripts/parse_ozon.py 2359066702 2829800382 --csv output/products.csv
```

Для локального запуска сначала примените миграцию командой `docker compose up --build --exit-code-from migrate migrate`, затем настройте `.env` и выполните `uv run python scripts/parse_ozon.py ...`. Для запуска контейнера с уже подготовленными cookies используйте команду `docker compose run --build --rm parser ...` из раздела PostgreSQL. Локальный `--csv output/products.csv` сохраняет файл на хосте; контейнеру для экспорта на хост потребуется отдельный bind mount.

Один `requests.Session` загружает сохранённые cookies и делает запросы карточек. В режиме `--output database` успешно распознанные товары записываются в PostgreSQL. В режиме `--output csv` база не нужна, а результат сохраняется в указанный файл (по умолчанию `output/products.csv`). При ошибке хотя бы одного SKU команда завершается с кодом 1 и пишет ошибку в лог.

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

Workflow CI настроен на сборку образа, миграцию и тесты на отдельной PostgreSQL-базе. **Последние запуски CI не прошли**: GitHub не запускает job из-за проблемы с платежами или лимитом расходов аккаунта. После исправления в Billing & plans повторно запустите workflow на текущем коммите. Локально для тестов БД поднимите отдельную пустую базу:

```bash
docker compose up -d --wait postgres
docker compose exec postgres createdb -U ozon ozon_test
TEST_DATABASE_URL=postgresql+psycopg://ozon:local_only_change_me@localhost:5432/ozon_test uv run pytest -q
```

Если `ozon_test` уже существует, пропустите команду `createdb`. Тесты требуют PostgreSQL-базу с именем, заканчивающимся на `_test`. Схема создаётся Alembic, изменения каждого теста откатываются отдельной транзакцией. Основную БД использовать нельзя. Проверяются миграция, INSERT, повторный SKU, Decimal/price, rating/reviews, NULL, rich content, media counts, created_at и восстановление после ошибки записи.

## Финальная проверка перед сдачей

При доступной разрешённой авторизации нужно последовательно: получить OAuth token Gmail на привязанном аккаунте; запустить `uv run python scripts/get_cookies.py`; убедиться в успешном входе по защищённому ресурсу; применить миграцию; выполнить парсер по доступному SKU; повторить запуск того же SKU; через `SELECT` проверить поля, обновление строки и отсутствие дубля. Сначала проверьте формат реального HTML на обезличенной локальной копии через `--html-file`, затем выполните полный live-прогон и проверьте, что в логах и Git нет секретов. До этих шагов результат синтетических тестов не доказывает корректную работу на живом Ozon.

## Ограничения

Парсер не обходит антибот-защиту и CAPTCHA. Извлечение дополнительных полей зависит от фактического формата JSON авторизованной страницы. Авторизацию, получение Gmail-кода, извлечение всех 12 полей из Ozon и end-to-end тест с PostgreSQL нужно проверить на реальных SKU перед отправкой. Airflow и DataLens пока не добавлены.
