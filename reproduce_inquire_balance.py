from samsung_auto_trader.config import load_config
from samsung_auto_trader.api_client import KISApiClient
from samsung_auto_trader.account import query_account_balance
from samsung_auto_trader.logger import get_logger

logger = get_logger()

if __name__ == '__main__':
    cfg = load_config()
    # token는 token_cache.json에서 읽거나 빈 문자열로 두면 서버 반응 확인 가능
    try:
        with open(cfg.token_cache_path, 'r') as f:
            import json
            token = json.load(f).get('access_token', '')
    except Exception:
        token = ''

    client = KISApiClient(cfg, token)
    try:
        holdings, cash = query_account_balance(client, cfg)
        logger.info('Holdings count=%s cash=%s', len(holdings), cash)
    except Exception as e:
        logger.exception('Reproduction attempt failed: %s', e)
