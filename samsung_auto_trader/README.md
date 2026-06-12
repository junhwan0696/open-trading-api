# Samsung Auto Trader

🤖 한국투자증권(KIS) Open API를 활용한 **삼성전자(005930) 자동매매 시스템**

모의투자 계좌에서 ±2,000 KRW 지정가 주문으로 자동 거래하는 간단한 Python 기반 시스템입니다.

## 🎯 특징

- **자동 거래**: 09:10~15:30 거래시간 내에서 자동 주문 실행
- **지정가 전략**: 현재가 기준 ±2,000 KRW에서 1주씩 매수/매도
- **토큰 캐싱**: 동일 계정 재인증 최소화로 API 요청 절감
- **15분 폴링**: 900초(15분) 간격으로 시장가 조회 및 계좌 잔고 확인
- **GitHub Secrets 자동로드**: Codespace에서 환경변수 자동 설정
- **GitHub Actions 지원**: 스케줄 실행 또는 수동 트리거

## 📋 사전 요구사항

- Python 3.8+
- 한국투자증권 Open API 계정 (모의투자/실거래 모두 가능)
- 계정: APPKEY, APPSECRET, 계좌번호(Account)

## 🚀 설치

### 1. 의존성 설치

```bash
cd /workspaces/open-trading-api
pip install -r requirements.txt
```

### 2. 환경변수 설정

#### 옵션 A: 로컬 환경변수 설정

```bash
export GH_APPKEY="your_app_key"
export GH_APPSECRET="your_app_secret"
export GH_ACCOUNT="your_account_number"
```

#### 옵션 B: GitHub Secrets 설정 (Codespace)

GitHub 저장소 > Settings > Secrets and variables > Actions에서 다음 생성:
- `GH_APPKEY`: 발급받은 Application Key
- `GH_APPSECRET`: 발급받은 Application Secret
- `GH_ACCOUNT`: 거래 계좌번호

Codespace에서 실행 시 `gh` CLI를 통해 자동으로 로드됩니다.

### 3. API 환경 선택 (필수)

#### 모의투자 (기본값)
```bash
# 기본적으로 모의투자 서버로 설정됨
python -m samsung_auto_trader.main
```

#### 실거래
```bash
export GH_API_ROOT="https://openapi.koreainvestment.com:9443"
python -m samsung_auto_trader.main
```

## 💻 사용 방법

### 로컬 실행

```bash
cd /workspaces/open-trading-api

# 환경변수 설정
export GH_APPKEY="your_key"
export GH_APPSECRET="your_secret"
export GH_ACCOUNT="your_account"

# 실행
python -m samsung_auto_trader.main
```

### GitHub Actions 실행

1. GitHub 저장소에 Secrets 추가 (위 참고)
2. Actions 탭 > "Run Samsung Auto Trader" 선택
3. "Run workflow" 클릭
4. 로그에서 실행 결과 확인

## 📊 거래 전략

### 매매 로직

```
1. 현재가 조회 (15분 간격)
   ↓
2. 계좌 조회 (보유 종목, 사용가능 현금)
   ↓
3. 결정:
   - 보유하지 않음 + 미주문 → 매수 (현재가 - 2,000 KRW)
   - 보유함 + 미주문 → 매도 (현재가 + 2,000 KRW)
   - 주문 완료 → 대기
   ↓
4. 주문 체결 확인
   ↓
5. 900초(15분) 대기 후 반복
```

### 주요 매개변수

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| `symbol` | 005930 | 삼성전자 종목코드 |
| `price_margin` | 2,000 KRW | 현재가 기준 매수/매도 호가 |
| `order_quantity` | 1주 | 한 번의 주문 수량 |
| `poll_interval_seconds` | 900 | 시장가 조회 간격 |
| `trading_start` | 09:10 | 거래 시작 시간 |
| `trading_end` | 15:30 | 거래 종료 시간 |

## 📁 프로젝트 구조

```
samsung_auto_trader/
├── __init__.py              # 패키지 마커
├── config.py                # 설정 로드 (환경변수 → GitHub Secrets)
├── logger.py                # 중앙식 로깅
├── auth.py                  # 토큰 발급 및 캐싱
├── api_client.py            # KIS API 요청 래퍼
├── market_data.py           # 현재가 조회
├── account.py               # 계좌 조회 (잔고, 보유)
├── orders.py                # 주문 실행 (매수/매도)
├── trader.py                # 거래 로직 오케스트레이션
├── main.py                  # 진입점
├── token_cache.json         # 토큰 캐시 (자동 생성)
└── README.md                # 이 파일
```

## 🔌 KIS Open API 엔드포인트

| 기능 | TR_ID | 메서드 | 엔드포인트 |
|------|-------|--------|-----------|
| 토큰 발급 | - | POST | `/oauth2/tokenP` |
| 현재가 조회 | FHKST01010100 | GET | `/uapi/domestic-stock/v1/quotations/inquire-price` |
| 매수 주문 | TTTC0802U | POST | `/uapi/domestic-stock/v1/trading/order-cash` |
| 매도 주문 | TTTC0801U | POST | `/uapi/domestic-stock/v1/trading/order-cash` |
| 잔고 조회 | TTTC8434R | GET | `/uapi/domestic-stock/v1/trading/inquire-balance` |

## 🔑 토큰 캐싱 메커니즘

- 발급받은 토큰을 `token_cache.json`에 저장
- 토큰 유효시간(기본 23시간) 내에서 재사용
- 유효시간 만료 시 자동 갱신
- 일일 API 요청 수 최소화

## 🐛 로깅

모든 작업이 `samsung_auto_trader` 로거로 기록됩니다:

```
2026-06-12 14:30:45 INFO Current price: 70,500 KRW
2026-06-12 14:30:46 INFO Holdings: 1 share
2026-06-12 14:30:47 INFO Placing sell order at 72,500 KRW
2026-06-12 14:30:50 INFO Order placed successfully
```

## ⚙️ 설정 커스터마이징

`config.py`의 `load_config()` 함수에서 기본값 변경 가능:

```python
return Config(
    symbol="005930",              # 종목코드 변경 가능
    price_margin=2000,            # 호가 간격 조정
    order_quantity=1,             # 주문 수량 변경
    poll_interval_seconds=900,    # 폴링 간격 조정
    trading_start=time(9, 10),    # 거래 시작시간
    trading_end=time(15, 30),     # 거래 종료시간
)
```

## 🔒 보안

- **credential 관리**: 모든 인증정보는 환경변수 또는 GitHub Secrets에서만 로드
- **하드코딩 금지**: 소스코드에 appkey/appsecret 없음
- **HTTPS 전용**: 모든 API 통신은 HTTPS
- **Hashkey 서명**: 주문 요청은 KIS Hashkey로 서명

## 📈 다음 단계

- [ ] 전략 개선: 단순 ±2,000 KRW → 이동평균 기반 전략
- [ ] 다중 종목 지원: 현재 삼성전자(005930)만 지원
- [ ] 손실제한(Stop Loss) 추가
- [ ] 매매 리포트 생성
- [ ] Slack/Discord 알림 연동

## ⚠️ 주의사항

1. **모의투자 확인**: 기본값은 모의투자 서버입니다. 실거래를 원할 시 `GH_API_ROOT` 변경 필수
2. **거래시간**: 09:10~15:30 외 거래 불가
3. **API 한도**: 한국투자증권의 API Rate Limit 준수
4. **손실 책임**: 자동매매로 발생하는 손실은 사용자 책임

## 🆘 문제 해결

### "GH_APPKEY not found" 에러

```bash
# 환경변수 설정 확인
echo $GH_APPKEY

# GitHub Secrets 설정 확인 (Codespace)
gh secret get GH_APPKEY
```

### 주문이 체결되지 않음

- 거래시간 확인: 09:10 ~ 15:30
- 지정가가 현재가에서 벗어났는지 확인
- 계좌 잔금 또는 주식 보유 확인

### 토큰 만료 에러

자동으로 갱신됩니다. 수동 갱신을 원할 시:

```bash
rm samsung_auto_trader/token_cache.json
python -m samsung_auto_trader.main
```

## 📞 지원

한국투자증권 Open API 포털: https://apiportal.koreainvestment.com/

## 📄 라이선스

한국투자증권 샘플 코드 라이선스 참고

---

**Happy Trading! 🚀**
