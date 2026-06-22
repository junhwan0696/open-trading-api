from typing import Any, Dict, List, Optional

from .api_client import KISApiClient
from .config import Config
from .logger import get_logger

ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
PENDING_ORDER_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
CANCEL_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
# Use production TR IDs as canonical values.
# KISApiClient normalizes T* -> V* automatically when GH_API_ROOT is the VTS(simulation) host.
BUY_TR_ID = "TTTC0802U"
SELL_TR_ID = "TTTC0801U"
PENDING_ORDER_TR_ID = "TTTC8001R"
CANCEL_ORDER_TR_ID = "TTTC0803U"


def _normalize_price_to_tick(price: float) -> int:
    """호가 단위(price tick) 규칙에 맞게 가격을 조정합니다.
    
    한국 주식 거래소의 호가 단위:
    - 1원 이상 1,000원 미만: 1원 단위
    - 1,000원 이상 5,000원 미만: 5원 단위
    - 5,000원 이상 10,000원 미만: 10원 단위
    - 10,000원 이상 50,000원 미만: 50원 단위
    - 50,000원 이상 100,000원 미만: 100원 단위
    - 100,000원 이상 500,000원 미만: 500원 단위
    - 500,000원 이상: 1,000원 단위
    """
    price = int(round(price))
    
    if price < 1000:
        tick = 1
    elif price < 5000:
        tick = 5
    elif price < 10000:
        tick = 10
    elif price < 50000:
        tick = 50
    elif price < 100000:
        tick = 100
    elif price < 500000:
        tick = 500
    else:
        tick = 1000
    
    # 호가 단위로 내림 (보수적 접근)
    return (price // tick) * tick


def _build_order_payload(config: Config, symbol: str, quantity: int, price: float) -> Dict[str, Any]:
    return {
        "CANO": config.account,
        "ACNT_PRDT_CD": config.product_code,
        "PDNO": symbol,
        "ORD_DVSN": "00",
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(int(price)),
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
    normalized_price = _normalize_price_to_tick(price)
    logger.info(
        "Normalizing buy price: original=%s -> normalized=%s",
        price,
        normalized_price,
    )
    payload = _build_order_payload(config, symbol, quantity, normalized_price)
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

    logger.info("Buy order placed for %s qty=%s price=%s", symbol, quantity, normalized_price)
    return response


def place_limit_sell(client: KISApiClient, config: Config, symbol: str, quantity: int, price: float) -> Dict[str, Any]:
    logger = get_logger()
    normalized_price = _normalize_price_to_tick(price)
    logger.info(
        "Normalizing sell price: original=%s -> normalized=%s",
        price,
        normalized_price,
    )
    payload = _build_order_payload(config, symbol, quantity, normalized_price)
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

    logger.info("Sell order placed for %s qty=%s price=%s", symbol, quantity, normalized_price)
    return response


def _query_daily_ccld_orders(
    client: KISApiClient,
    config: Config,
    symbol: str,
    ccld_dvsn: str,
) -> List[Dict[str, Any]]:
    """inquire-daily-ccld 조회 공통 함수.

    ccld_dvsn:
    - 01: 체결
    - 02: 미체결
    """
    logger = get_logger()
    from datetime import datetime

    today = datetime.now().strftime("%Y%m%d")

    params = {
        "CANO": config.account,
        "ACNT_PRDT_CD": config.product_code,
        "INQR_STRT_DT": today,  # 시작 날짜
        "INQR_END_DT": today,   # 종료 날짜
        "SLL_BUY_DVSN_CD": "00", # 매도/매수 전체
        "INQR_DVSN": "00",       # 역순
        "PDNO": symbol,
        "CCLD_DVSN": ccld_dvsn,   # 00=전체, 01=체결, 02=미체결
        "ORD_GNO_BRNO": "",
        "ODNO": "",
        "INQR_DVSN_3": "00",
        "INQR_DVSN_1": "",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    
    response = client.request("GET", PENDING_ORDER_PATH, params=params, tr_id=PENDING_ORDER_TR_ID)
    if not response:
        raise RuntimeError("Pending orders query returned no response")

    if response.get("rt_cd") != "0":
        raise RuntimeError(f"Pending orders query failed: {response.get('msg1')}")

    # output1 또는 output2에 미체결 주문 데이터가 있을 수 있음
    output = response.get("output1", [])
    if not output:
        output = response.get("output2", [])

    if isinstance(output, dict):
        output = [output] if output else []
    elif not isinstance(output, list):
        output = []

    state_text = "filled" if ccld_dvsn == "01" else "pending" if ccld_dvsn == "02" else "daily-ccld"
    logger.info("Found %d %s orders for %s", len(output), state_text, symbol)

    return output


def query_pending_orders(client: KISApiClient, config: Config, symbol: str) -> List[Dict[str, Any]]:
    """주문미체결내역 조회 - inquire-daily-ccld API 사용"""
    return _query_daily_ccld_orders(client, config, symbol, ccld_dvsn="02")


def query_filled_orders(client: KISApiClient, config: Config, symbol: str) -> List[Dict[str, Any]]:
    """주문체결내역 조회 - inquire-daily-ccld API 사용"""
    return _query_daily_ccld_orders(client, config, symbol, ccld_dvsn="01")


def cancel_order(client: KISApiClient, config: Config, order_number: str, order_branch: str, quantity: int) -> Dict[str, Any]:
    """주문 취소"""
    logger = get_logger()
    payload = {
        "CANO": config.account,
        "ACNT_PRDT_CD": config.product_code,
        "KRX_FWDG_ORD_ORGNO": order_branch,
        "ORGN_ODNO": order_number,
        "ORD_DVSN": "00",
        "ORD_QTY": "0",
        "QTY_ALL_ORD_YN": "Y",
        "CTAC_TLNO": "",
        "SLL_TYPE": "01",
        "ALGO_NO": "",
    }
    
    response = client.request(
        "POST",
        CANCEL_ORDER_PATH,
        params=payload,
        tr_id=CANCEL_ORDER_TR_ID,
        post=True,
        hash_key=True,
    )
    
    if not response:
        raise RuntimeError("Cancel order request failed: no response")
    
    if not _order_response_success(response):
        message = _order_response_message(response)
        logger.warning("Cancel order rejected: %s", message)
        raise RuntimeError(f"Cancel order rejected: {message}")
    
    logger.info("Order cancelled: order_number=%s quantity=%s", order_number, quantity)
    return response
