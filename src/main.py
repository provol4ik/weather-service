import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import config
from .api_rotator import APIRotator
from .city_manager import CityManager
from .request_log import RequestLog
from .server import create_app
from .storage import WeatherStorage
from .weather_collector import collect_all


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def hourly_poll(
    cities: CityManager,
    rotator: APIRotator,
    storage: WeatherStorage,
    request_log: RequestLog,
) -> None:
    log = logging.getLogger(__name__)
    log.info("Starting hourly poll")
    rotator.reload_from_csv()
    rotator.reset_counters()
    fresh = cities.load_cities()
    collect_all(fresh, rotator, storage, request_log=request_log)
    storage.save_to_disk()


def main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)

    storage = WeatherStorage()
    storage.load_from_disk()

    cities = CityManager()
    rotator = APIRotator()
    request_log = RequestLog(capacity=1000)

    log.info("Performing initial weather poll")
    collect_all(cities.list_cities(), rotator, storage, request_log=request_log)
    storage.save_to_disk()

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        hourly_poll,
        trigger=CronTrigger(minute=0),
        args=[cities, rotator, storage, request_log],
        id="hourly_poll",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        storage.save_to_disk,
        trigger=IntervalTrigger(minutes=config.CACHE_SAVE_MINUTES),
        id="cache_save",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("Scheduler started")

    app = create_app(storage, cities, rotator, request_log)
    try:
        app.run(host=config.SERVER_HOST, port=config.SERVER_PORT, use_reloader=False)
    finally:
        scheduler.shutdown(wait=False)
        storage.save_to_disk()


if __name__ == "__main__":
    main()
