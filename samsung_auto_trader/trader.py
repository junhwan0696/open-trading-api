import time as time_module
from datetime import datetime, timedelta, timezone
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
from .orders import place_limit_buy, place_limit_sell, query_pending_orders, cancel_order


class SamsungAutoTrader:
    def __init__(self, config: Config, client: KISApiClient) -> None:
        self.config = config
        self.client = client
        self.logger = get_logger()
        self.base_price: Optional[float] = None
        self.buy_order_number: Optional[str] = None
        self.sell_order_number: Optional[str] = None
        self.buy_order_branch: Optional[str] = None
        self.sell_order_branch: Optional[str] = None

    def run(self) -> None:
        self.logger.info(
            "Starting Samsung Auto Trader for %s between %s and %s",
            self.config.symbol,
            self.config.trading_start,
            self.config.trading_end,
        )


        while True:
            now = datetime.now()
            kst_timezone = timezone(timedelta(hours=9))
            # 1. 현재 시간을 무조건 UTC 기반의 'Aware datetime'으로 가져옵니다.
            utc_now = datetime.now(timezone.utc)
            # 2. UTC 시간을 KST(한국 시간)로 변환합니다.
            kst_now = utc_now.astimezone(kst_timezone)
            # 3. KST 기준의 '시간(time)'만 뽑아냅니다.
            current_kst_time = kst_now.time()
                
            # 15:30 이후 종료 로직
            if current_kst_time >= self.config.trading_end:
                self.logger.info("Trading window ended at %s. Cancelling all pending orders and shutting down.", self.config.trading_end)
                try:
                    self._cancel_all_pending_orders()
                except Exception as exc:
                    self.logger.exception("Error cancelling pending orders during shutdown: %s", exc)
                self.logger.info("Shutdown complete.")
                break

            # 시작 시간 이전 대기
            if current_kst_time < self.config.trading_start:
                wait_seconds = (datetime.combine(now.date(), self.config.trading_start) - now).total_seconds()
                sleep_seconds = min(wait_seconds, 60)
                self.logger.info("Waiting for trading window to open at %s", self.config.trading_start)
                time_module.sleep(sleep_seconds)
                continue

            # 트레이딩 사이클 실행
            try:
                self._execute_cycle()
            except Exception as exc:
                self.logger.exception("Unhandled error during trading cycle: %s", exc)

            # 사이클 후 종료 시간 다시 확인
            if current_kst_time >= self.config.trading_end:
                self.logger.info("Trading window ended after cycle. Cancelling all pending orders and shutting down.")
                try:
                    self._cancel_all_pending_orders()
                except Exception as exc:
                    self.logger.exception("Error cancelling pending orders during shutdown: %s", exc)
                break

            self.logger.info("Sleeping for %s seconds before next cycle.", self.config.poll_interval_seconds)
            time_module.sleep(self.config.poll_interval_seconds)

    def _execute_cycle(self) -> None:
        """그리드 매매 핵심 로직:
        1. 기준가가 없으면 설정
        2. 기준가가 있으면 주문 미체결내역 조회
        3. 체결 여부에 따라 처리
        """
        if self.base_price is None:
            self._set_base_price()
            if self.base_price is None:
                return
            self._place_grid_orders()
            return
        
        # 주문 체결 상태 확인 및 처리
        self._check_and_handle_execution()

    def _set_base_price(self) -> None:
        """기준가 설정: 현재가를 조회하여 새로운 기준가로 설정"""
        price = get_current_price(self.client, self.config.symbol)
        if price is None:
            self.logger.warning("Unable to obtain current price for %s. Skipping base price setup.", self.config.symbol)
            return
        
        self.base_price = price
        self.buy_order_number = None
        self.sell_order_number = None
        self.buy_order_branch = None
        self.sell_order_branch = None
        
        self.logger.info("Base price set to %s KRW for %s", self.base_price, self.config.symbol)

    def _place_grid_orders(self) -> None:
        """그리드 주문 배치: 매수/매도 주문을 동시에 (또는 순차적으로) 제출"""
        if self.base_price is None:
            self.logger.warning("Cannot place grid orders without base price")
            return
        
        # 계좌 정보 조회
        try:
            holdings, cash_summary = query_account_balance(self.client, self.config)
            symbol_holding = find_symbol_holding(holdings, self.config.symbol)
            held_quantity = parse_holdings_quantity(symbol_holding)
        except Exception as exc:
            self.logger.warning("Unable to query account balance: %s", exc)
            return
        
        # 매수 주문: 기준가 대비 N% 하락한 가격
        buy_price = max(self.base_price - self.config.price_margin, 1)
        self.logger.info(
            "Placing buy order for %s quantity=1 at %s KRW (base_price=%s, margin=%s)",
            self.config.symbol,
            buy_price,
            self.base_price,
            self.config.price_margin,
        )
        try:
            buy_response = place_limit_buy(self.client, self.config, self.config.symbol, 1, buy_price)
            self.buy_order_number = buy_response.get("output", {}).get("ODNO")
            self.buy_order_branch = buy_response.get("output", {}).get("ORD_SEAT")
            self.logger.info("Buy order placed: order_number=%s", self.buy_order_number)
        except Exception as exc:
            self.logger.warning("Failed to place buy order: %s", exc)
            return
        
        # 매도 주문: 기준가 대비 N% 상승한 가격 (단, 계좌에 보유 수량이 있을 때만)
        if held_quantity > 0:
            sell_price = self.base_price + self.config.price_margin
            self.logger.info(
                "Placing sell order for %s quantity=%s at %s KRW (base_price=%s, margin=%s)",
                self.config.symbol,
                held_quantity,
                sell_price,
                self.base_price,
                self.config.price_margin,
            )
            try:
                sell_response = place_limit_sell(self.client, self.config, self.config.symbol, held_quantity, sell_price)
                self.sell_order_number = sell_response.get("output", {}).get("ODNO")
                self.sell_order_branch = sell_response.get("output", {}).get("ORD_SEAT")
                self.logger.info("Sell order placed: order_number=%s", self.sell_order_number)
            except Exception as exc:
                self.logger.warning("Failed to place sell order: %s", exc)
        else:
            self.logger.info("No holdings for sell order (held_quantity=0)")

    def _check_and_handle_execution(self) -> None:
        """주문 체결 상태 확인:
        - 상황 A: 매수 체결 -> 미체결 매도 취소, 새로운 기준가 설정
        - 상황 B: 매도 체결 -> 미체결 매수 취소, 새로운 기준가 설정
        - 상황 C: 모두 미체결 -> 대기
        """
        try:
            pending_orders = query_pending_orders(self.client, self.config, self.config.symbol)
        except Exception as exc:
            self.logger.warning("Unable to query pending orders: %s", exc)
            return
        
        # 미체결 주문 번호 수집
        pending_order_numbers = [order.get("ODNO") for order in pending_orders]
        
        # 매수 체결 여부 확인
        buy_filled = self.buy_order_number and self.buy_order_number not in pending_order_numbers
        # 매도 체결 여부 확인
        sell_filled = self.sell_order_number and self.sell_order_number not in pending_order_numbers
        
        self.logger.info(
            "Order status check: buy_filled=%s sell_filled=%s buy_order=%s sell_order=%s pending_count=%s",
            buy_filled,
            sell_filled,
            self.buy_order_number,
            self.sell_order_number,
            len(pending_orders),
        )
        
        # 상황 A: 매수 체결
        if buy_filled and not sell_filled:
            self.logger.info("Buy order filled. Cancelling sell order.")
            if self.sell_order_number and self.sell_order_branch:
                try:
                    cancel_order(self.client, self.config, self.sell_order_number, self.sell_order_branch, 1)
                except Exception as exc:
                    self.logger.warning("Failed to cancel sell order: %s", exc)
            
            # 매수가를 새로운 기준가로 설정
            price = get_current_price(self.client, self.config.symbol)
            if price is not None:
                self.base_price = price
                self.logger.info("New base price set to %s (buy execution price)", self.base_price)
                self.buy_order_number = None
                self.sell_order_number = None
                self.buy_order_branch = None
                self.sell_order_branch = None
        
        # 상황 B: 매도 체결
        elif sell_filled and not buy_filled:
            self.logger.info("Sell order filled. Cancelling buy order.")
            if self.buy_order_number and self.buy_order_branch:
                try:
                    cancel_order(self.client, self.config, self.buy_order_number, self.buy_order_branch, 1)
                except Exception as exc:
                    self.logger.warning("Failed to cancel buy order: %s", exc)
            
            # 매도가를 새로운 기준가로 설정
            price = get_current_price(self.client, self.config.symbol)
            if price is not None:
                self.base_price = price
                self.logger.info("New base price set to %s (sell execution price)", self.base_price)
                self.buy_order_number = None
                self.sell_order_number = None
                self.buy_order_branch = None
                self.sell_order_branch = None
        
        # 상황 C: 모두 미체결
        elif not buy_filled and not sell_filled:
            self.logger.info("No orders filled. Waiting for execution.")
        
        # 상황 D: 둘 다 체결 (에지 케이스)
        elif buy_filled and sell_filled:
            self.logger.info("Both orders filled. Resetting and setting new base price.")
            price = get_current_price(self.client, self.config.symbol)
            if price is not None:
                self.base_price = price
                self.logger.info("New base price set to %s", self.base_price)
                self.buy_order_number = None
                self.sell_order_number = None
                self.buy_order_branch = None
                self.sell_order_branch = None

    def _cancel_all_pending_orders(self) -> None:
        """모든 미체결 주문 취소 (종료 시점에 호출)"""
        try:
            pending_orders = query_pending_orders(self.client, self.config, self.config.symbol)
        except Exception as exc:
            self.logger.warning("Unable to query pending orders for cancellation: %s", exc)
            return
        
        for order in pending_orders:
            order_number = order.get("ODNO")
            order_branch = order.get("ORD_SEAT")
            quantity = int(order.get("ORD_QTY", 0))
            
            if not order_number or not order_branch:
                self.logger.warning("Skipping order without number or branch: %s", order)
                continue
            
            try:
                self.logger.info("Cancelling order: order_number=%s quantity=%s", order_number, quantity)
                cancel_order(self.client, self.config, order_number, order_branch, quantity)
            except Exception as exc:
                self.logger.warning("Failed to cancel order %s: %s", order_number, exc)

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
