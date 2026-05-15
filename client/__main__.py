import argparse

from . import config as client_config
from .app import WeatherClientApp


def main() -> None:
    parser = argparse.ArgumentParser(prog="weather-client")
    parser.add_argument("--host", help="Server host (overrides saved config)")
    parser.add_argument("--port", type=int, help="Server port (overrides saved config)")
    parser.add_argument("--token", help="Admin token (overrides saved config)")
    args = parser.parse_args()

    overrides_present = any(v is not None for v in (args.host, args.port, args.token))
    if overrides_present:
        cfg = client_config.load()
        if args.host is not None:
            cfg["host"] = args.host
        if args.port is not None:
            cfg["port"] = args.port
        if args.token is not None:
            cfg["admin_token"] = args.token
        client_config.save(cfg)

    WeatherClientApp().run()


if __name__ == "__main__":
    main()
