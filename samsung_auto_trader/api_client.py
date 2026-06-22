import json
import random
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
        # Retry only connection-level failures at adapter layer.
        # HTTP status retries are handled explicitly in request().
        retries = Retry(
            total=3,
            connect=3,
            read=3,
            status=0,
            backoff_factor=1,
            status_forcelist=[],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        # Request timeout in seconds (used for both GET and POST)
        self.request_timeout = 60
        self.max_attempts = 5
        self.base_backoff_seconds = 1.0
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
        retriable_statuses = {429, 500, 502, 503, 504}

        for attempt in range(1, self.max_attempts + 1):
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

                if response.status_code in retriable_statuses:
                    self.logger.warning(
                        "API call %s returned retriable status %s (attempt %d/%d)",
                        url,
                        response.status_code,
                        attempt,
                        self.max_attempts,
                    )
                    if attempt < self.max_attempts:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            sleep_seconds = float(retry_after)
                        else:
                            sleep_seconds = self.base_backoff_seconds * (2 ** (attempt - 1))
                            sleep_seconds += random.uniform(0.0, 0.3)
                        time.sleep(sleep_seconds)
                        continue

                if response.status_code != 200:
                    self.logger.warning("API call %s returned status %s", url, response.status_code)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                self.logger.error("Request failed for %s: %s", url, exc)
                if attempt >= self.max_attempts:
                    raise
                sleep_seconds = self.base_backoff_seconds * (2 ** (attempt - 1))
                sleep_seconds += random.uniform(0.0, 0.3)
                time.sleep(sleep_seconds)

        raise RuntimeError("Unable to complete API request")
