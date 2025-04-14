import pandas as pd
import numpy as np
import uuid
import json  # Importação adicionada para resolver os erros
from utils import logger
from trade_manager import generate_combination_key, save_signal, save_signal_log, save_indicator_stats, save_report
from indicators import calculate_indicators

def run_backtest(client, config, binance_utils, learning_engine, start_date, end_date, pairs, timeframes, strategies, get_historical_data, get_quantity, get_funding_rate, generate_signal, simulate_trade_backtest):
    logger.info(f"Iniciando backtest de {start_date} a {end_date}...")
    active_trades = []
    indicator_stats = {}
    df_sinais = pd.DataFrame()

    for pair in pairs:
        for tf in timeframes:
            historical_data = get_historical_data(client, pair, tf, start_date, end_date, limit=1000)
            if historical_data.empty:
                logger.warning(f"Sem dados históricos para {pair} ({tf}). Pulando...")
                continue

            historical_data = calculate_indicators(historical_data, binance_utils)
            for strategy in strategies:
                if not strategy.get("enabled", True):
                    continue

                logger.info(f"Backtesting estratégia {strategy['name']} para {pair} ({tf})...")
                for idx in range(50, len(historical_data)):
                    df_slice = historical_data.iloc[:idx + 1]
                    direction, score, details, contributing_indicators, strategy_name = generate_signal(
                        df_slice, tf, strategy, config, learning_engine, binance_utils
                    )
                    if not direction:
                        continue

                    signal_id = str(uuid.uuid4())
                    current_price = df_slice.iloc[-1]['close']
                    quantity = get_quantity(config, pair, current_price)
                    funding_rate = get_funding_rate(client, pair, config, mode="backtest")

                    signal_data = {
                        "signal_id": signal_id,
                        "timestamp": df_slice.iloc[-1]['timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
                        "par": pair,
                        "timeframe": tf,
                        "direcao": direction,
                        "preco_entrada": current_price,
                        "quantity": quantity,
                        "score_tecnico": score,
                        "motivos": json.dumps(details["reasons"]),
                        "funding_rate": funding_rate,
                        "localizadores": json.dumps(details["locators"]),
                        "parametros": json.dumps({
                            "tp_percent": config["tp_percent"],
                            "sl_percent": config["sl_percent"],
                            "leverage": config["leverage"]
                        }),
                        "timeframes_analisados": json.dumps([tf]),
                        "contributing_indicators": contributing_indicators,
                        "strategy_name": strategy_name,
                        "combination_key": generate_combination_key(pair, direction, strategy_name, contributing_indicators, tf),
                        "historical_win_rate": details.get("historical_win_rate", 0.0),
                        "avg_pnl": details.get("avg_pnl", 0.0),
                        "estado": "aberto",
                        "side_performance": json.dumps({"LONG": 0.0, "SHORT": 0.0}),
                        "timeframe_weight": 1.0 / (timeframes.index(tf) + 1)
                    }

                    save_signal(signal_data, accepted=True, mode="backtest")
                    save_signal_log(signal_data, accepted=True, mode="backtest")

                    if simulate_trade_backtest(signal_data, config, historical_data, active_trades, indicator_stats, binance_utils, get_funding_rate):
                        df_new = pd.DataFrame([signal_data])
                        df_sinais = pd.concat([df_sinais, df_new], ignore_index=True)

    save_indicator_stats(indicator_stats)
    save_report(start_date, end_date, df_sinais, indicator_stats)
    logger.info("Backtest concluído.")
    return df_sinais