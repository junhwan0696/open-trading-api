from typing import Any, Dict, Optional

from .api_client import KISApiClient
from .logger import get_logger

PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
PRICE_TR_ID = "FHKST01010100"
MARKET_DIV = "J"
PRICE_KEYS = ("stck_prpr", "STCK_PRPR", "prpr", "PRPR")


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_current_price(client: KISApiClient, symbol: str) -> Optional[float]:
    logger = get_logger()
    params = {
        "FID_COND_MRKT_DIV_CODE": MARKET_DIV,
        "FID_INPUT_ISCD": symbol,
    }
    response = client.request("GET", PRICE_PATH, params=params, tr_id=PRICE_TR_ID)
    if not response:
        logger.warning("Price request returned no response for %s", symbol)
        return None

    if response.get("rt_cd") != "0":
        logger.warning(
            "Price request failed for %s: rt_cd=%s message=%s",
            symbol,
            response.get("rt_cd"),
            response.get("msg1"),
        )
        return None

    output = response.get("output") or response.get("output1")
    if isinstance(output, list):
        output = output[0] if output else {}
    if not isinstance(output, dict):
        logger.warning("Unexpected price response format: %s", output)
        return None

    for key in PRICE_KEYS:
        value = output.get(key)
        price = _safe_float(value)
        if price is not None:
            return price

    logger.warning("Unable to parse current price from response: %s", output)
    return None
