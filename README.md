# Weather Aggregator Service

Python-сервис для агрегации данных о погоде из OpenWeatherMap. Опрашивает список городов раз в час, кэширует результаты и предоставляет собственный HTTP API.

## Возможности

- Периодический опрос OpenWeatherMap (раз в час, на границе часа UTC)
- Управление пулом API-ключей (по 50 запросов на ключ, сброс счётчиков каждый час)
- Динамическое добавление городов через HTTP API или вручную в CSV
- Persistance: кэш сохраняется в JSON, переживает рестарт
- Готов к Docker

## Структура

```
weather-service/
├── data/
│   ├── cities.csv          # Список городов
│   ├── apis.csv            # Список API-ключей
│   └── weather_cache.json  # Автогенерируется
├── src/
│   ├── main.py             # Точка входа
│   ├── config.py
│   ├── api_rotator.py
│   ├── city_manager.py
│   ├── weather_collector.py
│   ├── storage.py
│   └── server.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Настройка

### 1. Заполните API-ключи

`data/apis.csv`:
```csv
api_key
abc123yourkey1
def456yourkey2
```

Получить ключ: https://openweathermap.org/api

### 2. Заполните список городов

`data/cities.csv`:
```csv
city,country
London,GB
Moscow,RU
Tokyo,JP
```

## Запуск

### Локально

```bash
cd weather-service
pip install -r requirements.txt
python -m src.main
```

### Docker

```bash
cd weather-service
docker compose up --build
```

## API Endpoints

### `GET /health`
Состояние сервиса, количество городов, статистика по ключам.

### `GET /weather`
Все собранные данные о погоде.

```bash
curl http://localhost:8000/weather
```

### `GET /weather/<city>?country=XX`
Погода конкретного города. Если города нет в кэше — синхронно запрашивает у OpenWeatherMap и добавляет в список.

```bash
curl http://localhost:8000/weather/Paris?country=FR
```

### `GET /cities`
Список отслеживаемых городов.

### `POST /cities`
Добавить город вручную.

```bash
curl -X POST http://localhost:8000/cities \
  -H "Content-Type: application/json" \
  -d '{"city": "Paris", "country": "FR"}'
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATA_DIR` | `./data` | Путь к папке с CSV/кэшем |
| `POLL_INTERVAL_HOURS` | `1` | Интервал опроса |
| `REQUESTS_PER_KEY` | `50` | Лимит запросов на ключ |
| `CACHE_SAVE_MINUTES` | `5` | Частота сохранения кэша |
| `SERVER_HOST` | `0.0.0.0` | Хост Flask |
| `SERVER_PORT` | `8000` | Порт Flask |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

## Поведение

- **Старт:** загружает кэш, читает CSV, делает первый опрос всех городов, запускает планировщик и Flask
- **Каждый час (на границе часа UTC):** сбрасывает счётчики ключей, перечитывает `cities.csv`, опрашивает все города, сохраняет кэш
- **Каждые 5 минут:** сохраняет кэш на диск
- **Запрос нового города:** добавляется в `cities.csv` (через `add_city`), делается запрос, результат кэшируется
- **Все ключи исчерпаны:** новые запросы возвращают `503`, hourly poll прерывается до следующего сброса
