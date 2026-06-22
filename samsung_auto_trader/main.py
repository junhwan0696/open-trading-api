import sys

from .config import load_config
from .auth import get_token
from .api_client import KISApiClient
from .logger import get_logger, setup_logger
from .orders import BUY_TR_ID, SELL_TR_ID, PENDING_ORDER_TR_ID, CANCEL_ORDER_TR_ID
from .trader import SamsungAutoTrader


def _mask_account(account: str) -> str:
    if not account:
        return "<empty>"
    if len(account) <= 3:
        return "*" * len(account)
    return f"{account[:3]}***"


def _log_startup_diagnostics(client: KISApiClient) -> None:
    logger = get_logger()
    config = client.config
    is_simulation = config.api_root.startswith("https://openapivts")
    mode = "simulation" if is_simulation else "real"

    logger.info(
        "Startup diagnostics: mode=%s api_root=%s account=%s product_code=%s",
        mode,
        config.api_root,
        _mask_account(config.account),
        config.product_code,
    )

    logger.info(
        "Startup diagnostics: tr_id_mapping buy=%s->%s sell=%s->%s pending=%s->%s cancel=%s->%s",
        BUY_TR_ID,
        client._normalize_tr_id(BUY_TR_ID),
        SELL_TR_ID,
        client._normalize_tr_id(SELL_TR_ID),
        PENDING_ORDER_TR_ID,
        client._normalize_tr_id(PENDING_ORDER_TR_ID),
        CANCEL_ORDER_TR_ID,
        client._normalize_tr_id(CANCEL_ORDER_TR_ID),
    )


def main() -> None:
    setup_logger()
    logger = get_logger()

    try:
        config = load_config()
        token = get_token(config)
        client = KISApiClient(config, token)
        _log_startup_diagnostics(client)
        trader = SamsungAutoTrader(config, client)
        trader.run()
    except Exception as exc:
        logger.exception("Auto trader stopped with error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
