# trade_simulator.py
import time
import threading
from datetime import datetime
import pandas as pd
import json
from utils import logger, CsvWriter

def simulate_trade(client, signal_data, config, active_trades, binance_utils, order_executor, active_orders_by_combination, get_current_price, get_funding_rate):
    """
    Simula uma ordem no modo dry_run, monitorando TP, SL e timeout.
    """
    try:
        signal_id = signal_data['signal_id']
        pair = signal_data['par']
        direction = signal_data['direcao']
        entry_price = float(signal_data['preco_entrada'])
        quantity = float(signal_data['quantity'])
        timeframe = signal_data['timeframe']
        strategy_name = signal_data['strategy_name']
        tp_percent = float(config.get('tp_percent', 0.5))
        sl_percent = float(config.get('sl_percent', 0.3))
        leverage = float(config.get('leverage', 1))
        
        timeout_map = {
            '1m': 30,    # 30 segundos para testes rápidos
            '5m': 150,   # 2.5 minutos
            '15m': 450,  # 7.5 minutos
            '1h': 1800,  # 30 minutos
            '4h': 7200,  # 2 horas
            '1d': 14400  # 4 horas
        }
        timeout = timeout_map.get(timeframe, 7200)

        tp_price = entry_price * (1 + tp_percent / 100) if direction == "LONG" else entry_price * (1 - tp_percent / 100)
        sl_price = entry_price * (1 - sl_percent / 100) if direction == "LONG" else entry_price * (1 + sl_percent / 100)

        logger.info(f"Simulação para {pair} ({direction}) - Entry: {entry_price:.8f}, TP: {tp_price:.8f}, SL: {sl_price:.8f}, Timeout: {timeout}s")

        start_time = time.time()
        while True:
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                logger.warning(f"Simulação para sinal {signal_id} ({pair}) excedeu o tempo limite ({elapsed_time:.2f}s/{timeout}s). Encerrando.")
                mark_price = get_current_price(client, pair, config)
                if mark_price is None:
                    logger.error(f"Preço atual não obtido para {pair}. Usando preço de entrada: {entry_price:.8f}")
                    mark_price = entry_price
                result = "Timeout"
                lucro_percentual = 0.0
                break

            current_price = get_current_price(client, pair, config)
            if current_price is None:
                logger.warning(f"Preço atual não obtido para {pair}. Tentando novamente...")
                time.sleep(0.01)
                continue

            current_price = float(current_price)
            logger.debug(f"Verificando preços para {pair}: Current: {current_price:.8f}, TP: {tp_price:.8f}, SL: {sl_price:.8f}")

            if direction == "LONG":
                if current_price >= tp_price:
                    result = "TP"
                    lucro_percentual = tp_percent * leverage
                    mark_price = current_price
                    logger.info(f"TP atingido para {pair}: {current_price:.8f} >= {tp_price:.8f}")
                    break
                elif current_price <= sl_price:
                    result = "SL"
                    lucro_percentual = -sl_percent * leverage
                    mark_price = current_price
                    logger.info(f"SL atingido para {pair}: {current_price:.8f} <= {sl_price:.8f}")
                    break
            else:
                if current_price <= tp_price:
                    result = "TP"
                    lucro_percentual = tp_percent * leverage
                    mark_price = current_price
                    logger.info(f"TP atingido para {pair}: {current_price:.8f} <= {tp_price:.8f}")
                    break
                elif current_price >= sl_price:
                    result = "SL"
                    lucro_percentual = -sl_percent * leverage
                    mark_price = current_price
                    logger.info(f"SL atingido para {pair}: {current_price:.8f} >= {sl_price:.8f}")
                    break

            time.sleep(0.01)

        signal_data['preco_saida'] = mark_price
        signal_data['lucro_percentual'] = lucro_percentual
        signal_data['pnl_realizado'] = lucro_percentual * quantity
        signal_data['resultado'] = result
        signal_data['timestamp_saida'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        signal_data['estado'] = "fechado"

        csv_writer = CsvWriter(
            filename="sinais_detalhados.csv",
            columns=[
                'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
                'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
                'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
                'motivos', 'timeframe', 'aceito', 'parametros'
            ]
        )
        csv_writer.write_row(signal_data)
        logger.info(f"Simulação {signal_id} para {pair} finalizada: {result}, Lucro/Perda: {lucro_percentual:.2f}%")

        combination_key = (strategy_name, timeframe, direction)
        if combination_key in active_orders_by_combination:
            active_orders_by_combination[combination_key] -= 1
            if active_orders_by_combination[combination_key] <= 0:
                del active_orders_by_combination[combination_key]
                logger.debug(f"Contagem zerada para combinação {combination_key}")

        if signal_data in active_trades:
            active_trades.remove(signal_data)
            logger.debug(f"Trade {signal_id} removido de active_trades")

    except Exception as e:
        logger.error(f"Erro na simulação do sinal {signal_id}: {e}")

def simulate_trade_backtest(client, signal_data, config, get_current_price, get_funding_rate):
    """
    Simula uma ordem para backtest.
    """
    try:
        signal_id = signal_data['signal_id']
        pair = signal_data['par']
        direction = signal_data['direcao']
        entry_price = float(signal_data['preco_entrada'])
        quantity = float(signal_data['quantity'])
        timeframe = signal_data['timeframe']
        tp_percent = float(config.get('tp_percent', 0.5))
        sl_percent = float(config.get('sl_percent', 0.3))
        leverage = float(config.get('leverage', 1))

        tp_price = entry_price * (1 + tp_percent / 100) if direction == "LONG" else entry_price * (1 - tp_percent / 100)
        sl_price = entry_price * (1 - sl_percent / 100) if direction == "LONG" else entry_price * (1 + sl_percent / 100)

        mark_price = get_current_price(client, pair, config)
        if mark_price is None:
            logger.warning(f"Preço atual não obtido para {pair} no backtest. Usando preço de entrada.")
            mark_price = entry_price

        mark_price = float(mark_price)
        if direction == "LONG":
            if mark_price >= tp_price:
                result = "TP"
                lucro_percentual = tp_percent * leverage
            elif mark_price <= sl_price:
                result = "SL"
                lucro_percentual = -sl_percent * leverage
            else:
                result = "Em Aberto"
                lucro_percentual = ((mark_price - entry_price) / entry_price) * 100 * leverage
        else:
            if mark_price <= tp_price:
                result = "TP"
                lucro_percentual = tp_percent * leverage
            elif mark_price >= sl_price:
                result = "SL"
                lucro_percentual = -sl_percent * leverage
            else:
                result = "Em Aberto"
                lucro_percentual = ((entry_price - mark_price) / entry_price) * 100 * leverage

        signal_data['preco_saida'] = mark_price if result in ["TP", "SL"] else None
        signal_data['lucro_percentual'] = lucro_percentual
        signal_data['pnl_realizado'] = lucro_percentual * quantity if result in ["TP", "SL"] else 0.0
        signal_data['resultado'] = result
        signal_data['timestamp_saida'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if result in ["TP", "SL"] else None
        signal_data['estado'] = "fechado" if result in ["TP", "SL"] else "aberto"

        return signal_data
    except Exception as e:
        logger.error(f"Erro na simulação de backtest para sinal {signal_data.get('signal_id', 'desconhecido')}: {e}")
        return signal_data