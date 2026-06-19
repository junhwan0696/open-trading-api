import subprocess
from dataclasses import dataclass
from datetime import time
from os import getenv
from pathlib import Path

from .logger import get_logger


@dataclass(frozen=True)
class Config:
    app_key: str
    app_secret: str
    account: str
    product_code: str
    api_root: str
    token_url: str
    symbol: str
    price_margin: int
    order_quantity: int
    poll_interval_seconds: int
    trading_start: time
    trading_end: time
    token_cache_path: Path


def _load_from_github_secrets(secret_name: str) -> str:
    """Load a secret from GitHub Secrets using gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "secret", "get", secret_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def load_config() -> Config:
    logger = get_logger()
    
    app_key = getenv("GH_APPKEY", "").strip()
    app_secret = getenv("GH_APPSECRET", "").strip()
    account = getenv("GH_ACCOUNT", "").strip()
    
    if not app_key:
        logger.info("GH_APPKEY not in environment; attempting to load from GitHub Secrets")
        app_key = _load_from_github_secrets("GH_APPKEY")
    
    if not app_secret:
        logger.info("GH_APPSECRET not in environment; attempting to load from GitHub Secrets")
        app_secret = _load_from_github_secrets("GH_APPSECRET")
    
    if not account:
        logger.info("GH_ACCOUNT not in environment; attempting to load from GitHub Secrets")
        account = _load_from_github_secrets("GH_ACCOUNT")
    
    if not app_key or not app_secret or not account:
        raise ValueError(
            "Environment variables GH_APPKEY, GH_APPSECRET, and GH_ACCOUNT must be set "
            "or available as GitHub Secrets."
        )

    product_code = getenv("GH_PRODUCT_CODE", "01").strip() or "01"
    api_root = getenv(
        "GH_API_ROOT", "https://openapivts.koreainvestment.com:29443"
    ).strip()
    token_url = f"{api_root}/oauth2/tokenP"
    token_cache_path = Path(__file__).resolve().parent / "token_cache.json"

    return Config(
        app_key=app_key,
        app_secret=app_secret,
        account=account,
        product_code=product_code,
        api_root=api_root,
        token_url=token_url,
        symbol="005930",
        price_margin=2000,
        order_quantity=1,
        poll_interval_seconds=900,
        trading_start=time(9, 10),   # 한국 시간 09:10
        trading_end=time(15, 30),    # 한국 시간 15:30
        token_cache_path=token_cache_path,
    )
