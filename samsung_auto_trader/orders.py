from typing import Any, Dict, Optional

from .api_client import KISApiClient
from .config import Config
from .logger import get_logger

ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
BUY_TR_ID = "TTTC0802U"
SELL_TR_ID = "TTTC0801U"


def _build_order_payload(config: Config, symbol: str, quantity: int, price: float) -> Dict[str, Any]:
    return {
        "CANO": config.account,
        "ACNT_PRDT_CD": config.product_code,
        "PDNO": symbol,
        "ORD_DVSN": "00",
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(int(round(price))),
        "CTAC_TLNO": "",
        "SLL_TYPE": "01",
        "ALGO_NO": "",
    }


def _order_response_success(response: Dict[str, Any]) -> bool:
    return response.get("rt_cd") == "0"


def _order_response_message(response: Dict[str, Any]) -> str:
    return response.get("msg1") or response.get("msg2") or ""


def place_limit_buy(client: KISApiClient, config: Config, symbol: str, quantity: int, price: float) -> Dict[str, Any]:
    logger = get_logger()
    payload = _build_order_payload(config, symbol, quantity, price)
    response = client.request(
        "POST",
        ORDER_PATH,
        params=payload,
        tr_id=BUY_TR_ID,
        post=True,
        hash_key=True,
    )
    if not response:
        raise RuntimeError("Buy order request failed: no response")

    if not _order_response_success(response):
        message = _order_response_message(response)
        logger.warning("Buy order rejected: %s", message)
        raise RuntimeError(f"Buy order rejected: {message}")

    logger.info("Buy order placed for %s qty=%s price=%s", symbol, quantity, price)
    return response


def place_limit_sell(client: KISApiClient, config: Config, symbol: str, quantity: int, price: float) -> Dict[str, Any]:
    logger = get_logger()
    payload = _build_order_payload(config, symbol, quantity, price)
    response = client.request(
        "POST",
        ORDER_PATH,
        params=payload,
        tr_id=SELL_TR_ID,
        post=True,
        hash_key=True,
    )
    if not response:
        raise RuntimeError("Sell order request failed: no response")

    if not _order_response_success(response):
        message = _order_response_message(response)
        logger.warning("Sell order rejected: %s", message)
        raise RuntimeError(f"Sell order rejected: {message}")

    logger.info("Sell order placed for %s qty=%s price=%s", symbol, quantity, price)
    return response
