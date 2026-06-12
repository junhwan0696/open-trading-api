import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .config import Config
from .logger import get_logger


TOKEN_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _read_token_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        return json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        get_logger().warning("Unable to read token cache: %s", exc)
        return {}


def _write_token_cache(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _parse_expiration(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    for parser in (datetime.fromisoformat, lambda text: datetime.strptime(text, TOKEN_DATE_FORMAT)):
        try:
            return parser(value)
        except (ValueError, TypeError):
            continue

    return None


def _is_token_valid(token_data: Dict[str, Any]) -> bool:
    access_token = token_data.get("access_token")
    expires_at = token_data.get("expires_at")
    if not access_token or not expires_at:
        return False

    expiration = _parse_expiration(expires_at)
    if not expiration:
        return False

    return datetime.utcnow() < expiration


def _request_token(config: Config) -> Dict[str, Any]:
    url = config.token_url
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "charset": "UTF-8",
        "User-Agent": "Mozilla/5.0",
    }
    payload = {
        "grant_type": "client_credentials",
        "appkey": config.app_key,
        "appsecret": config.app_secret,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def get_token(config: Config) -> str:
    logger = get_logger()
    token_data = _read_token_cache(config.token_cache_path)
    if _is_token_valid(token_data):
        logger.info("Reusing cached token from %s", config.token_cache_path)
        return token_data["access_token"]

    logger.info("Requesting new authentication token")
    response_data = _request_token(config)
    access_token = response_data.get("access_token")
    if not access_token:
        raise RuntimeError("Token response did not include access_token")

    expires_at_value = response_data.get("access_token_token_expired")
    expiration = _parse_expiration(expires_at_value)
    if expiration is None and response_data.get("expires_in") is not None:
        expires_in = int(response_data.get("expires_in", 0))
        expiration = datetime.utcnow() + timedelta(seconds=max(expires_in - 30, 0))

    if expiration is None:
        expiration = datetime.utcnow() + timedelta(hours=23)

    cache_data = {
        "access_token": access_token,
        "expires_at": expiration.isoformat(),
    }
    _write_token_cache(config.token_cache_path, cache_data)
    logger.info("Saved new token; expires at %s UTC", expiration.isoformat())
    return access_token
