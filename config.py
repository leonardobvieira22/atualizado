import os
from dotenv import load_dotenv

load_dotenv()

# Chaves API
REAL_API_KEY = os.getenv('REAL_API_KEY', "VGQ0dhdCcHjDhEjj0Xuue3ZtyIZHiG9NK8chA4ew0HMQMywydjrVrLTWeN8nnZ9e")
REAL_API_SECRET = os.getenv('REAL_API_SECRET', "jHrPFutd2fQH2AECeABbG6mDvbJqhEYBt1kuYmiWfcBjJV22Fwtykqx8mDFle3dO")
DRY_RUN_API_KEY = os.getenv('DRY_RUN_API_KEY', "VGQ0dhdCcHjDhEjj0Xuue3ZtyIZHiG9NK8chA4ew0HMQMywydjrVrLTWeN8nnZ9e")
DRY_RUN_API_SECRET = os.getenv('DRY_RUN_API_SECRET', "jHrPFutd2fQH2AECeABbG6mDvbJqhEYBt1kuYmiWfcBjJV22Fwtykqx8mDFle3dO")

# Pares de negociação
SYMBOLS = ["XRPUSDT", "DOGEUSDT", "TRXUSDT"]

# Timeframes expandidos para análise múltipla
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

DRY_RUN = True

CONFIG = {
    'leverage': 20,
    'margin_type': 'ISOLATED',
    'risk_per_trade': 1.0,
    'dry_run': DRY_RUN,
    'mercado': 'futures',
    'timeout_ordem': 30,
    'max_trades_simultaneos': 100,  # Aumentado para permitir mais ordens
    'price_cache_duration': 5,
    'backtest_funding_rate': 0.0001,
    'learning_enabled': True,
    'learning_update_interval': 3600,
    'atr_enabled': True,
    'atr_period': 14,
    'atr_tp_multiplier': 2.0,
    'atr_sl_multiplier': 1.0,
    'sentiment_enabled': False,
    'sentiment_api_key': os.getenv('SENTIMENT_API_KEY', ""),
    'sentiment_source': 'lunarcrush',
    'realtime_signals_enabled': True,  # Habilitado para todos os timeframes
    'timeframe_settings': {  # Novas configurações por timeframe
        '1m': {'realtime_enabled': True, 'weight': 1.0},
        '5m': {'realtime_enabled': True, 'weight': 1.0},
        '15m': {'realtime_enabled': True, 'weight': 1.0},
        '1h': {'realtime_enabled': True, 'weight': 1.2},
        '4h': {'realtime_enabled': True, 'weight': 1.2},
        '1d': {'realtime_enabled': True, 'weight': 1.3}
    },
    'quantity_in_usdt': 10.0,  # Adicionado para corrigir o erro de quantidade
    'indicators': {
        'rsi': {'ativo': True, 'periodo': 14, 'sobrecomprado': 60, 'sobrevendido': 30, 'score': 20, 'tp_percent': 1.8, 'sl_percent': 0.9},  # Ajustado sobrecomprado para 60
        'vwap': {'ativo': True},
        'bollinger': {'ativo': True, 'periodo': 20, 'desvio': 2},
        'ema': {'ativo': True, 'periodo_rapido': 12, 'periodo_lento': 50, 'score': 60, 'tp_percent': 2.5, 'sl_percent': 1.2},  # Ajustado períodos para 12 e 50
        'volume': {'ativo': True, 'periodo_medio': 20, 'score': 20, 'tp_percent': 2.0, 'sl_percent': 1.0},
        'fibonacci': {'ativo': True, 'levels': [0.236, 0.382, 0.5, 0.618, 0.786]},
        'estocastico': {'ativo': True, 'k_period': 14, 'd_period': 3},
        'sentimento': {'ativo': False, 'fonte': 'lunarcrush'},
        'sma': {'ativo': True, 'periodo_rapido': 10, 'periodo_lento': 50, 'score': 60, 'tp_percent': 2.5, 'sl_percent': 1.2},
        'macd': {'ativo': True, 'fast': 12, 'slow': 26, 'signal': 9, 'score': 30, 'tp_percent': 2.0, 'sl_percent': 1.0},
        'adx': {'ativo': True, 'window': 14, 'threshold': 20, 'score': 25, 'tp_percent': 2.0, 'sl_percent': 1.0}
    },
    'composite_indicators': {
        'swing_trade_composite': {
            'indicators': ['ema', 'adx', 'macd', 'rsi', 'volume'],
            'calculation': 'weighted_average',
            'weights': {'ema': 0.2, 'adx': 0.2, 'macd': 0.2, 'rsi': 0.2, 'volume': 0.2}
        }
    },
    'stop_padrao': {
        'tp_percent': 2.0,
        'sl_percent': 1.0,
        'trailing_stop': False,
        'callback_rate': 0.5
    },
    'api_config': {
        'recvWindow': 60000,
        'timeout': 10
    },
    'backtest_config': {
        'timeframes': TIMEFRAMES,
        'candle_count': 200,  # Aumentado para evitar "dados insuficientes"
        'entry_value_usdt': 10.0,
        'slippage_percent': 0.1,
        'fee_percent': 0.04,
        'signal_strategies': [
            {"name": "sma_only", "indicators": ["sma"]},
            {"name": "ema_only", "indicators": ["ema"]},
            {"name": "rsi_only", "indicators": ["rsi"]},
            {"name": "macd_only", "indicators": ["macd"]},
            {"name": "adx_only", "indicators": ["adx"]},
            {"name": "volume_only", "indicators": ["volume"]},
            {"name": "sma_rsi", "indicators": ["sma", "rsi"]},
            {"name": "ema_macd", "indicators": ["ema", "macd"]},
            {"name": "rsi_macd", "indicators": ["rsi", "macd"]},
            {"name": "ema_adx", "indicators": ["ema", "adx"]},
            {"name": "all", "indicators": ["sma", "ema", "rsi", "macd", "adx", "volume"]},
            {"name": "swing_trade_composite", "indicators": ["rsi", "macd", "ema"], "type": "movimento_longo", "timeframes": ["1h", "4h", "1d"], "min_target_percent": 3.0, "stop_loss_percent": 1.0, "leverage": 5, "enabled": True}
        ]
    },
    'limits_by_timeframe': {
        '1m': {'LONG': 1, 'SHORT': 1},
        '5m': {'LONG': 1, 'SHORT': 1},
        '15m': {'LONG': 1, 'SHORT': 1},
        '1h': {'LONG': 1, 'SHORT': 1},
        '4h': {'LONG': 1, 'SHORT': 1},
        '1d': {'LONG': 1, 'SHORT': 1}
    },
    'reset_password': '123456',  # Senha para resetar ordens e estatísticas
    'modes': {
        'dry_run': True,
        'real': False,
        'backtest': False
    }
}

if DRY_RUN and (not DRY_RUN_API_KEY or not DRY_RUN_API_SECRET):
    raise ValueError("Chaves de Dry Run não configuradas corretamente!")
if not DRY_RUN and (not REAL_API_KEY or not REAL_API_SECRET):
    raise ValueError("Chopper, você não configurou as chaves de produção corretamente!")