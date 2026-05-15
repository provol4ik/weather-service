# Weather Aggregator Service

Python-сервис для агрегации данных о погоде из OpenWeatherMap. Опрашивает список городов раз в час, кэширует результаты и предоставляет собственный HTTP API. В комплекте — Tkinter-клиент для администрирования.

## Возможности

- Периодический опрос OpenWeatherMap (на границе часа UTC)
- Ротация пула API-ключей (по 50 запросов на ключ, счётчики сбрасываются раз в час)
- Управление городами и ключами через HTTP API или Tkinter-клиент
- Кэш в JSON, переживает рестарт (атомарная запись через `.tmp` + rename)
- Журнал HTTP-запросов (in-memory, до 1000 записей)
- Опциональная авторизация по bearer-токену для мутирующих эндпоинтов
- Готов к Docker

## Структура

```
weather-service/
├── data/
│   ├── cities.csv          # Список городов (city, country)
│   ├── apis.csv            # API-ключи OpenWeatherMap (column: api_key)
│   └── weather_cache.json  # Автогенерируется
├── src/
│   ├── main.py             # Точка входа + scheduler
│   ├── config.py
│   ├── api_rotator.py
│   ├── city_manager.py
│   ├── weather_collector.py
│   ├── storage.py
│   ├── request_log.py
│   └── server.py
├── client/                 # Tkinter-клиент (отдельный процесс)
│   ├── __main__.py
│   ├── api.py
│   ├── app.py
│   └── config.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Настройка

### Переменные окружения

Скопируйте `.env.example` в `.env` и заполните (файл `.env` в `.gitignore`, не коммитится):

```bash
cp .env.example .env
```

```
OWM_API_KEYS=key1,key2,key3
ADMIN_TOKEN=<длинная-случайная-строка>
```

- `OWM_API_KEYS` используется **только для первого запуска**, чтобы засеять `data/apis.csv`. Если CSV уже не пуст — переменная игнорируется, источник правды — CSV.
- `ADMIN_TOKEN` (опционально, но рекомендуется): если задан, мутирующие эндпоинты `/apis*` требуют `Authorization: Bearer <token>`, а `GET /apis` маскирует ключи неавторизованным. Если пуст — сервис работает без авторизации.

Получить ключ OpenWeatherMap: https://openweathermap.org/api

### Список городов

Заполнить вручную либо через `POST /cities`. `data/cities.csv`:

```csv
city,country
London,GB
Moscow,RU
Tokyo,JP
```

## Запуск

### Локально

```bash
pip install -r requirements.txt
python -m src.main
```

Сервер слушает `0.0.0.0:8181` (см. `SERVER_PORT`).

### Docker

```bash
services:
  weather:
    build:
      context: https://github.com/provol4ik/weather-service.git#main
    image: weather-service:latest
    pull_policy: build
    container_name: weather-service
    ports:
      - "8181:8181"
    volumes:
      - ./data:/app/data
    environment:
      - LOG_LEVEL=INFO
      - POLL_INTERVAL_HOURS=1
      - REQUESTS_PER_KEY=50
      - ADMIN_TOKEN=${ADMIN_TOKEN:-}
      - OWM_API_KEYS=${OWM_API_KEYS:-}
    restart: unless-stopped
```

Добавьте .env поместив туда свои Admin_Token и API, пример в .env.example

#### Первый запуск

```bash
# 1. Подготовьте окружение
cp .env.example .env
# отредактируйте .env: впишите OWM_API_KEYS и ADMIN_TOKEN

# 2. (опционально) положите свой data/cities.csv
#    Если пропустить — контейнер создаст пустой CSV сам.

# 3. Соберите и поднимите
docker compose up -d --build

# 4. Проверьте, что сервис жив
curl http://localhost:8181/health
docker compose logs -f weather
```

После старта `OWM_API_KEYS` из `.env` будет один раз записан в `data/apis.csv`. Дальше CSV — источник правды.

#### Обновление

`build.context` указывает на GitHub, поэтому свежий код подтягивается при пересборке:

```bash
docker compose build --pull
docker compose up -d
```

или одной командой:

```bash
docker compose up -d --build
```

Флаг `pull_policy: build` в `docker-compose.yml` запрещает compose тянуть образ с Docker Hub (его там нет) — сервис всегда собирается локально.

#### Управление

```bash
docker compose ps                 # статус
docker compose logs -f weather    # логи
docker compose restart weather    # перезапуск
docker compose down               # остановить и удалить контейнер
docker compose down -v            # то же + удалить тома (data/ останется, она bind-mount)
```

#### Безопасность

Порт `8181` пробрасывается на хост в `0.0.0.0` — если машина смотрит в интернет, обязательно задайте `ADMIN_TOKEN` в `.env`. Без токена любой получит ваши OpenWeatherMap-ключи через `GET /apis`.

### Tkinter-клиент

```bash
python -m client
python -m client --host 127.0.0.1 --port 8181 --token <ADMIN_TOKEN>
```

Последние `host` / `port` / `token` сохраняются в `~/.weather-client.json`.

## HTTP API

База: `http://localhost:8181`. Без `ADMIN_TOKEN` все эндпоинты публичны; с токеном — мутирующие `/apis*` требуют заголовок `Authorization: Bearer <token>`.

### Публичные

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Статус, число городов, статистика по ключам, размер лога |
| `GET` | `/weather` | Все кэшированные данные |
| `GET` | `/weather/<city>?country=XX` | Погода города. Cache miss → live-запрос + город добавляется в `cities.csv` |
| `GET` | `/log?limit=N` | Последние N записей журнала запросов |

### Города (без авторизации)

| Метод | Путь | Тело |
|-------|------|------|
| `GET` | `/cities` | — |
| `POST` | `/cities` | `{"city": "Paris", "country": "FR"}` |
| `PUT` | `/cities/<city>` | `{"country": "FR"}` |
| `DELETE` | `/cities/<city>` | — |

### API-ключи

| Метод | Путь | Авторизация | Описание |
|-------|------|-------------|----------|
| `GET` | `/apis` | публично | без токена — маскированные ключи |
| `POST` | `/apis` | admin | `{"key": "..."}` |
| `PUT` | `/apis/<old>` | admin | `{"key": "<new>"}` |
| `DELETE` | `/apis/<key>` | admin | — |
| `POST` | `/apis/reload` | admin | перечитать `apis.csv` с диска |

### Примеры

```bash
curl http://localhost:8181/weather/Paris?country=FR

curl -X POST http://localhost:8181/cities \
  -H "Content-Type: application/json" \
  -d '{"city": "Paris", "country": "FR"}'

curl -X POST http://localhost:8181/apis \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "abc123..."}'
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATA_DIR` | `./data` | Путь к папке с CSV и кэшем |
| `OWM_API_KEYS` | — | CSV-список ключей, используется только для сидинга пустого `apis.csv` |
| `ADMIN_TOKEN` | — | Bearer-токен для мутирующих `/apis*` |
| `POLL_INTERVAL_HOURS` | `1` | Зарезервировано; фактически опрос всегда на границе часа UTC |
| `REQUESTS_PER_KEY` | `50` | Лимит запросов на ключ внутри часа |
| `CACHE_SAVE_MINUTES` | `5` | Частота сохранения кэша на диск |
| `SERVER_HOST` | `0.0.0.0` | Хост Flask |
| `SERVER_PORT` | `8181` | Порт Flask |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

## Поведение

- **Старт:** загружает кэш, читает `cities.csv` и `apis.csv` (или сидит из `OWM_API_KEYS`, если CSV пуст), делает первый блокирующий опрос всех городов, запускает scheduler и Flask.
- **Раз в час (минута :00 UTC):** перезагружает ключи, сбрасывает счётчики, перечитывает `cities.csv`, опрашивает все города, сохраняет кэш.
- **Раз в `CACHE_SAVE_MINUTES` минут:** сохраняет кэш на диск.
- **Запрос неизвестного города через `GET /weather/<city>`:** город добавляется в `cities.csv`, делается live-запрос, результат кэшируется — далее город участвует в часовых опросах.
- **Все ключи исчерпаны:** новые `/weather/<city>` отдают `503`, hourly poll прерывается до следующего сброса счётчиков.
- **Безопасность:** на открытом порту обязательно задайте `ADMIN_TOKEN` — иначе ключи OpenWeatherMap доступны всем через `GET /apis`.
