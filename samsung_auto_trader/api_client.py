import json
import time
from typing import Any, Dict, Optional

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config
from .logger import get_logger


class KISApiClient:
    def __init__(self, config: Config, token: str) -> None:
        self.config = config
        self.token = token
        self.session = Session()
        # Configure requests session with retries/backoff for transient network errors
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        # Request timeout in seconds (used for both GET and POST)
        self.request_timeout = 60
        self.logger = get_logger()

    def _normalize_tr_id(self, tr_id: str) -> str:
        if self.config.api_root.startswith("https://openapivts") and tr_id.startswith("T"):
            return f"V{tr_id[1:]}"
        return tr_id

    def _headers(self, tr_id: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User-Agent": "Mozilla/5.0",
            "tr_id": self._normalize_tr_id(tr_id),
            "custtype": "P",
            "tr_cont": "",
        }

    def _request_hash_key(self, tr_id: str, payload: Dict[str, Any]) -> str:
        hash_url = f"{self.config.api_root}/uapi/hashkey"
        headers = self._headers(tr_id)
        response = self.session.post(hash_url, headers=headers, json=payload, timeout=self.request_timeout)
        response.raise_for_status()
        data = response.json()
        hash_value = data.get("HASH")
        if not hash_value:
            raise RuntimeError("Hash key response did not include HASH")
        return hash_value

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        tr_id: str = "",
        post: bool = False,
        hash_key: bool = False,
    ) -> Dict[str, Any]:
        url = f"{self.config.api_root}{path}"
        headers = self._headers(tr_id)
        attempt = 0

        while attempt < 3:
            attempt += 1
            try:
                self.logger.debug("Sending request %s %s attempt %d", method, url, attempt)
                if post:
                    if hash_key:
                        headers["hashkey"] = self._request_hash_key(tr_id, params or {})
                    response = self.session.post(
                        url,
                        headers=headers,
                        json=params or {},
                        timeout=self.request_timeout,
                    )
                else:
                    response = self.session.get(
                        url,
                        headers=headers,
                        params=params or {},
                        timeout=self.request_timeout,
                    )

                if response.status_code != 200:
                    self.logger.warning(
                        "API call %s returned status %s", url, response.status_code
                    )
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                self.logger.error("Request failed for %s: %s", url, exc)
                if attempt >= 3:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Unable to complete API request")
