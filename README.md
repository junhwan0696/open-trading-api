# Samsung Auto Trader

한국투자증권(KIS) Open API를 활용해 삼성전자(005930)를 자동매매하는 Python 시스템입니다.

## 자동매매 로직 개요

이 시스템은 기준가(base price)를 중심으로 양방향 지정가 주문(매수/매도)을 배치하고,
한쪽이 체결되면 반대 주문을 취소한 뒤 새로운 기준가로 다음 사이클을 시작하는 구조입니다.

핵심 아이디어:

1. 기준가 설정
2. 기준가 - 마진으로 매수 주문
3. 기준가 + 마진으로 매도 주문(보유 수량이 있을 때)
4. 미체결/체결 상태를 조회해 분기 처리
5. 체결 발생 시 반대편 주문 취소 후 기준가 리셋
6. 거래 종료 시점(15:30 KST)에는 미체결 주문 전체 취소

## 전체 실행 흐름

```text
main.py
   -> load_config()               (config.py)
   -> get_token()                 (auth.py)
   -> KISApiClient(...)           (api_client.py)
   -> SamsungAutoTrader.run()     (trader.py)

run() 루프 내부
   -> 거래시간 확인 (KST 기준)
   -> _execute_cycle()
       -> base_price 없음
            -> _set_base_price()              (market_data.get_current_price)
            -> _place_grid_orders()           (orders.place_limit_buy/sell)
       -> base_price 있음
            -> _check_and_handle_execution()  (orders.query_pending_orders, cancel_order, query_filled_orders)
   -> poll_interval_seconds 만큼 대기
   -> 종료 시 _cancel_all_pending_orders()
```

## 자동매매 로직 상세

### 1) 거래시간 게이트

- 기준: 한국시간(KST)
- 시작 전: 최대 60초 단위로 대기
- 종료 이후: 미체결 주문 전체 취소 후 종료

구현 위치: `SamsungAutoTrader.run()`

### 2) 첫 사이클: 기준가 설정 + 그리드 주문 배치

- `base_price`가 없으면 현재가를 조회해 기준가 설정
- 매수 주문가: `base_price - price_margin` (최소 1원)
- 매도 주문가: `base_price + price_margin` (보유 수량이 1주 이상일 때만)
- 주문 응답에서 주문번호(`ODNO`)와 지점/원주문조직번호(`ORD_SEAT`/`KRX_FWDG_ORD_ORGNO`) 저장

구현 위치:

- 기준가 설정: `SamsungAutoTrader._set_base_price()`
- 주문 배치: `SamsungAutoTrader._place_grid_orders()`

### 3) 이후 사이클: 체결 상태 점검 및 분기

- `query_pending_orders()`로 미체결 주문 목록 조회
- 저장해둔 주문번호(`buy_order_number`, `sell_order_number`)가 미체결 목록에 없으면 체결 후보로 판단
- 체결 케이스별 처리:
   - 매수만 체결: 매도 주문 취소 -> 새 기준가 설정
   - 매도만 체결: 매수 주문 취소 -> 새 기준가 설정
   - 둘 다 미체결: 유지
   - 둘 다 체결 후보: 재조회 + 체결내역 조회(`query_filled_orders`)로 확인 후 기준가 리셋

구현 위치: `SamsungAutoTrader._check_and_handle_execution()`

### 4) 종료 시 정리

- 종료 시점에 종목의 미체결 주문을 순회하며 취소 요청
- 주문번호/브랜치 누락 시 해당 주문은 건너뛰고 로그 경고

구현 위치: `SamsungAutoTrader._cancel_all_pending_orders()`

## 핵심 클래스/함수/변수 정리

### 핵심 클래스

- `SamsungAutoTrader` (`trader.py`)
   - 자동매매 상태와 사이클 전체를 관리하는 오케스트레이터
- `KISApiClient` (`api_client.py`)
   - KIS API 공통 호출 래퍼(헤더/TR_ID 정규화/재시도/백오프/HashKey)
- `Config` (`config.py`)
   - 실행 파라미터를 캡슐화하는 설정 데이터 클래스

### 핵심 함수

- 진입점
   - `main.main()`
- 인증
   - `auth.get_token()`
- 시세
   - `market_data.get_current_price()`
- 계좌
   - `account.query_account_balance()`
   - `account.find_symbol_holding()`
   - `account.parse_holdings_quantity()`
- 주문
   - `orders.place_limit_buy()`
   - `orders.place_limit_sell()`
   - `orders.query_pending_orders()`
   - `orders.query_filled_orders()`
   - `orders.cancel_order()`
- 트레이딩 제어
   - `SamsungAutoTrader.run()`
   - `SamsungAutoTrader._execute_cycle()`
   - `SamsungAutoTrader._set_base_price()`
   - `SamsungAutoTrader._place_grid_orders()`
   - `SamsungAutoTrader._check_and_handle_execution()`
   - `SamsungAutoTrader._cancel_all_pending_orders()`

### 핵심 상태 변수

- `base_price`: 현재 그리드의 기준 가격
- `buy_order_number`, `sell_order_number`: 현재 추적 중인 매수/매도 주문번호
- `buy_order_branch`, `sell_order_branch`: 취소 요청 시 필요한 주문 조직/지점 정보

### 핵심 설정 변수 (`Config`)

- `symbol`: 기본 거래 종목 (`005930`)
- `price_margin`: 기준가 대비 주문 간격 (기본 `2000`)
- `order_quantity`: 기본 주문 수량 (현재 로직에서 매수는 1주 사용)
- `poll_interval_seconds`: 사이클 간 대기 (기본 `300`초)
- `trading_start`, `trading_end`: 거래 허용 시간 (`09:10`~`15:30`, KST)

## 파일 간 유기적 연동

### 1) 시작 계층

- `main.py`는 전체 실행의 조립자(composer) 역할을 수행
- 설정(`config`) -> 인증(`auth`) -> API 클라이언트(`api_client`) -> 전략 실행기(`trader`) 순으로 의존성 주입

### 2) 전략 계층

- `trader.py`는 도메인 로직의 중심
- 외부 호출은 직접 API를 때리지 않고, 기능별 모듈 함수를 호출
   - 시세: `market_data.py`
   - 잔고/보유: `account.py`
   - 주문/정정취소/체결조회: `orders.py`

### 3) 인프라 계층

- `api_client.py`가 HTTP 상세 구현을 담당
   - 모의/실전 환경에 따른 TR_ID 정규화(T* -> V*)
   - 429/5xx 재시도와 exponential backoff+jitter
   - 주문 API의 hashkey 자동 처리
- `auth.py`는 토큰 발급과 캐시 파일(`token_cache.json`) 수명주기 관리

### 4) 공통 계층

- `logger.py`는 단일 로거 이름(`samsung_auto_trader`)로 전 모듈 로그 포맷 통일

즉, `trader.py`가 비즈니스 의사결정을 담당하고, 나머지 파일은 시세/계좌/주문/통신/인증을 역할별로 분리해 지원하는 구조입니다.

## 주요 API/TR ID

| 기능 | TR_ID | 메서드 | 엔드포인트 |
|------|-------|--------|-----------|
| 토큰 발급 | - | POST | `/oauth2/tokenP` |
| 현재가 조회 | FHKST01010100 | GET | `/uapi/domestic-stock/v1/quotations/inquire-price` |
| 현금 매수 주문 | TTTC0802U | POST | `/uapi/domestic-stock/v1/trading/order-cash` |
| 현금 매도 주문 | TTTC0801U | POST | `/uapi/domestic-stock/v1/trading/order-cash` |
| 주문취소 | TTTC0803U | POST | `/uapi/domestic-stock/v1/trading/order-cash` |
| 일별 주문조회(체결/미체결) | TTTC8001R | GET | `/uapi/domestic-stock/v1/trading/inquire-daily-ccld` |
| 잔고 조회 | TTTC8434R | GET | `/uapi/domestic-stock/v1/trading/inquire-balance` |

참고: 모의투자 서버(`openapivts`)에서는 `KISApiClient`가 TR_ID를 자동 변환해 사용합니다.

## 실행 방법

python -m samsung_auto_trader.main

# 실거래
 export GH_API_ROOT="https://openapi.koreainvestment.com:9443"
 python -m samsung_auto_trader.main


# 실제 거래 기록
### 아래는 터미널 로그 기록입니다
<img width="1403" height="772" alt="image" src="https://github.com/user-attachments/assets/73d83712-1510-4459-91d3-cd3958dc86b4" />

### 아래는 한투 모의투자 화면에서 체결 주문 화면입니다.
처음 실행의 결과로 base_price가 353,000원으로 설정되었고, 로직에 따라 현재 가지고 있던 3개의 주식이 모두 355,000원에 매도 주문이 들어갔고, 새로 1개를 351,000원에 매수 주문했습니다. 

<img width="430" height="582" alt="image" src="https://github.com/user-attachments/assets/87701718-fa58-4add-a627-44030a1263d6" />, <img width="440" height="582" alt="image" src="https://github.com/user-attachments/assets/24cfc94e-fdf3-492f-a1bc-f4844496af9f" />




## 주의사항

1. 기본 API Root는 모의투자 서버입니다.
2. 거래시간 종료 시 미체결 취소를 수행하지만, 네트워크/API 상태에 따라 예외가 발생할 수 있으므로 로그 확인이 필요합니다.
