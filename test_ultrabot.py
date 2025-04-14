import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from main import generate_signal, simulate_trade, get_current_price, load_config, run_backtest, check_active_trades
from binance_utils import BinanceUtils
from learning_engine import LearningEngine
from order_executor import OrderExecutor
import uuid
import json  # Importação adicionada para resolver o erro

class TestUltraBot(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.client = None  # Mock client for testing
        self.binance_utils = BinanceUtils(self.client, self.config)
        self.learning_engine = LearningEngine()
        self.order_executor = OrderExecutor(self.client, self.config)

    def test_generate_signal(self):
        # Mock historical data
        data = {
            'timestamp': [datetime.now() - pd.Timedelta(minutes=i) for i in range(100)],
            'close': np.random.uniform(1.9, 2.1, 100),
            'sma10': np.random.uniform(1.9, 2.1, 100),
            'sma50': np.random.uniform(1.9, 2.1, 100),
            'ema9': np.random.uniform(1.9, 2.1, 100),
            'ema21': np.random.uniform(1.9, 2.1, 100),
            'rsi': np.random.uniform(20, 80, 100),
            'macd': np.random.uniform(-0.1, 0.1, 100),
            'macd_signal': np.random.uniform(-0.1, 0.1, 100)
        }
        df = pd.DataFrame(data)
        df['sma10'][-1] = df['sma50'][-1] + 0.1  # Simula cruzamento LONG
        df['ema9'][-1] = df['ema21'][-1] + 0.05
        df['rsi'][-1] = 25  # Sobrevendido
        df['macd'][-1] = 0.01
        df['macd_signal'][-1] = -0.01

        strategy = {"name": "all", "indicators": ["sma", "ema", "rsi", "macd"], "enabled": True}
        direction, score, details, indicators, strategy_name = generate_signal(
            df, '1m', strategy, self.config, self.learning_engine, self.binance_utils
        )
        self.assertEqual(direction, "LONG")
        self.assertGreater(score, 0)
        self.assertTrue(len(details['reasons']) > 0)
        self.assertTrue('RSI' in indicators)

    def test_simulate_trade(self):
        # Mock signal data
        signal_data = {
            "signal_id": str(uuid.uuid4()),
            "par": "XRPUSDT",
            "direcao": "LONG",
            "preco_entrada": 2.0,
            "quantity": 1.0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timeframe": "1m",
            "parametros": json.dumps({"tp_percent": 2.0, "sl_percent": 1.0, "leverage": 10}),
            "estado": "aberto",
            "resultado": "N/A",
            "contributing_indicators": "RSI;MACD",
            "strategy_name": "all"
        }
        active_trades = []
        
        # Mock get_current_price
        def mock_get_current_price(client, pair, config):
            return 2.05  # Acima do TP (2.0 * 1.02 = 2.04)

        global get_current_price
        original_get_current_price = get_current_price
        get_current_price = mock_get_current_price

        simulate_trade(None, signal_data, self.config, active_trades, self.binance_utils, self.order_executor, {})
        self.assertEqual(signal_data["estado"], "fechado")
        self.assertEqual(signal_data["resultado"], "TP")
        self.assertGreater(signal_data["pnl_realizado"], 0)

        get_current_price = original_get_current_price

    def test_check_active_trades_opposite_direction(self):
        active_trades = [
            {
                "signal_id": str(uuid.uuid4()),
                "par": "XRPUSDT",
                "timeframe": "1m",
                "direcao": "LONG",
                "strategy_name": "all",
                "contributing_indicators": "SMA;EMA",
                "estado": "aberto"
            }
        ]
        result = check_active_trades(
            pair="XRPUSDT",
            timeframe="1m",
            direction="SHORT",  # Sentido contrário
            strategy_name="all",
            contributing_indicators="SMA;EMA",
            active_trades=active_trades,
            mode="dry_run"
        )
        self.assertFalse(result)  # Deve permitir ordens em sentido contrário

if __name__ == '__main__':
    unittest.main()