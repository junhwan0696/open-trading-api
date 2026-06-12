from typing import Any, Dict, List, Optional, Tuple

from .api_client import KISApiClient
from .config import Config
from .logger import get_logger

BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
BALANCE_TR_ID = "TTTC8434R"


def _normalize_response_value(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ensure_list(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def query_account_balance(client: KISApiClient, config: Config) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    logger = get_logger()
    params = {
        "CANO": config.account,
        "ACNT_PRDT_CD": config.product_code,
        "AFHR_FLPR_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "FUND_STTL_ICLD_YN": "N",
        "INQR_DVSN": "01",
        "OFL_YN": "",
        "PRCS_DVSN": "01",
        "UNPR_DVSN": "01",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }

    response = client.request("GET", BALANCE_PATH, params=params, tr_id=BALANCE_TR_ID)
    if not response:
        raise RuntimeError("Account balance request failed: no response")

    if response.get("rt_cd") != "0":
        logger.warning(
            "Account balance request failed: rt_cd=%s msg=%s",
            response.get("rt_cd"),
            response.get("msg1"),
        )
        raise RuntimeError(
            f"Account balance request rejected: {response.get('msg1', 'unknown')}"
        )

    holdings = _ensure_list(response.get("output1") or response.get("output"))
    raw_cash = response.get("output2") or {}
    if isinstance(raw_cash, list) and len(raw_cash) == 1:
        cash_summary = raw_cash[0]
    elif isinstance(raw_cash, dict):
        cash_summary = raw_cash
    else:
        cash_summary = {}

    return holdings, cash_summary


def find_symbol_holding(holdings: List[Dict[str, Any]], symbol: str) -> Optional[Dict[str, Any]]:
    for row in holdings:
        if row.get("pdno") == symbol or row.get("PDNO") == symbol:
            return row
    return None


def parse_holdings_quantity(holding: Optional[Dict[str, Any]]) -> int:
    if not holding:
        return 0

    quantity = holding.get("hldg_qty") or holding.get("HLDG_QTY") or holding.get("ord_psbl_qty") or holding.get("ORD_PSBQTY")
    if quantity in (None, ""):
        return 0

    try:
        return int(float(quantity))
    except (TypeError, ValueError):
        return 0


def parse_available_cash(summary: Dict[str, Any]) -> Optional[float]:
    cash_value = summary.get("dnca_tot_amt") or summary.get("DNCA_TOT_AMT") or summary.get("ord_psbl_amt")
    return _normalize_response_value(cash_value)
