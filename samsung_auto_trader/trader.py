import time as time_module
from datetime import datetime
from typing import Optional

from .api_client import KISApiClient
from .account import (
    find_symbol_holding,
    parse_available_cash,
    parse_holdings_quantity,
    query_account_balance,
)
from .config import Config
from .logger import get_logger
from .market_data import get_current_price
from .orders import place_limit_buy, place_limit_sell


class SamsungAutoTrader:
    def __init__(self, config: Config, client: KISApiClient) -> None:
        self.config = config
        self.client = client
        self.logger = get_logger()
        self.buy_order_placed = False
        self.sell_order_placed = False

    def run(self) -> None:
        self.logger.info(
            "Starting Samsung Auto Trader for %s between %s and %s",
            self.config.symbol,
            self.config.trading_start,
            self.config.trading_end,
        )

        while True:
            now = datetime.now()
            if now.time() > self.config.trading_end:
                self.logger.info("Trading window ended at %s. Stopping.", self.config.trading_end)
                break

            if now.time() < self.config.trading_start:
                wait_seconds = (datetime.combine(now.date(), self.config.trading_start) - now).total_seconds()
                sleep_seconds = min(wait_seconds, 60)
                self.logger.info("Waiting for trading window to open at %s", self.config.trading_start)
                time_module.sleep(sleep_seconds)
                continue

            try:
                self._execute_cycle()
            except Exception as exc:
                self.logger.exception("Unhandled error during trading cycle: %s", exc)

            if datetime.now().time() >= self.config.trading_end:
                self.logger.info("Trading window ended after cycle. Stopping.")
                break

            self.logger.info("Sleeping for %s seconds before next price check.", self.config.poll_interval_seconds)
            time_module.sleep(self.config.poll_interval_seconds)

    def _execute_cycle(self) -> None:
        price = get_current_price(self.client, self.config.symbol)  #현재가 가져옴
        if price is None:
            self.logger.warning("Unable to obtain current price for %s. Skipping cycle.", self.config.symbol)
            return

        self.logger.info("Current price for %s is %s KRW", self.config.symbol, price)

        holdings, cash_summary = query_account_balance(self.client, self.config)
        symbol_holding = find_symbol_holding(holdings, self.config.symbol)
        held_quantity = parse_holdings_quantity(symbol_holding)
        available_cash = parse_available_cash(cash_summary)

        self.logger.info(
            "Holdings: qty=%s available_cash=%s summary=%s",
            held_quantity,
            available_cash,
            cash_summary,
        )

        if held_quantity > 0 and not self.sell_order_placed:  # 주식이 있고 매도 주문을 안 넣었으면 
            sell_price = price + self.config.price_margin  # 정해진 마진 붙여 매도 주문 넣음
            self.logger.info(
                "Placing sell order for %s quantity=%s at %s KRW",
                self.config.symbol,
                held_quantity,
                sell_price,
            )
            place_limit_sell(self.client, self.config, self.config.symbol, held_quantity, sell_price)
            self.sell_order_placed = True
            self._log_post_order_status()
            return

        if held_quantity == 0 and not self.buy_order_placed:  # 주식이 없고 매수 주문 안 넣었으면
            buy_price = max(price - self.config.price_margin, 1)  # 현재 가격에서 마진 빼서 주문
            self.logger.info(
                "Placing buy order for %s quantity=%s at %s KRW",
                self.config.symbol,
                self.config.order_quantity,
                buy_price,
            )
            place_limit_buy(self.client, self.config, self.config.symbol, self.config.order_quantity, buy_price)
            self.buy_order_placed = True
            self._log_post_order_status()
            return

        if held_quantity == 0 and self.buy_order_placed:
            self.logger.info(
                "Buy order already placed and not filled yet for %s. Waiting.",
                self.config.symbol,
            )
            return

        if held_quantity > 0 and self.sell_order_placed:
            self.logger.info(
                "Sell order already placed for %s. Waiting for execution.",
                self.config.symbol,
            )
            return

        self.logger.info("No trading action required at this time.")

    def _log_post_order_status(self) -> None:
        try:
            holdings, cash_summary = query_account_balance(self.client, self.config)
            symbol_holding = find_symbol_holding(holdings, self.config.symbol)
            held_quantity = parse_holdings_quantity(symbol_holding)
            available_cash = parse_available_cash(cash_summary)
            self.logger.info(
                "Post-order status: held_quantity=%s available_cash=%s holdings=%s",
                held_quantity,
                available_cash,
                symbol_holding,
            )
        except Exception as exc:
            self.logger.warning("Unable to refresh account status after order: %s", exc)
