import sys

from .config import load_config
from .auth import get_token
from .api_client import KISApiClient
from .logger import get_logger, setup_logger
from .trader import SamsungAutoTrader


def main() -> None:
    setup_logger()
    logger = get_logger()

    try:
        config = load_config()
        token = get_token(config)
        client = KISApiClient(config, token)
        trader = SamsungAutoTrader(config, client)
        trader.run()
    except Exception as exc:
        logger.exception("Auto trader stopped with error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
