import pandas as pd
import os
from utils import logger, CsvWriter
import uuid
from datetime import datetime
import json
import pytz

def get_local_timestamp():
    """Retorna timestamp atual no timezone local"""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

# Inicializar o CsvWriter com filename e columns
csv_writer = CsvWriter(
    filename="sinais_detalhados.csv",
    columns=[
        'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
        'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
        'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
        'motivos', 'timeframe', 'aceito', 'parametros', 'quality_score'
    ]
)

def check_active_trades():
    """
    Verifica se há trades ativos no sistema.
    Returns:
        list: Lista de trades ativos.
    """
    try:
        df = pd.read_csv("sinais_detalhados.csv")
        active_trades = df[df['estado'] == 'aberto'].to_dict('records')
        logger.info(f"Trades ativos encontrados: {len(active_trades)}")
        return active_trades
    except Exception as e:
        logger.error(f"Erro ao verificar trades ativos: {e}")
        return []

def check_timeframe_direction_limit(pair, timeframe, direction, strategy_name, active_trades, config):
    """
    Verifica se já atingiu o limite de ordens para um timeframe/direção específico
    """
    # Verifica se o timeframe está ativo para esta estratégia
    strategy_timeframes = config.get('backtest_config', {}).get('signal_strategies', [])
    strategy_config = next((s for s in strategy_timeframes if s['name'] == strategy_name), None)
    
    if strategy_config and 'timeframes' in strategy_config:
        if timeframe not in strategy_config['timeframes']:
            logger.info(f"Timeframe {timeframe} não está ativo para estratégia {strategy_name}")
            return False
    
    tf_limits = config.get('limits_by_timeframe', {}).get(timeframe, {'LONG': 1, 'SHORT': 1})
    max_orders = tf_limits.get(direction, 1)
    
    # Filtrar ordens ativas para o mesmo par/timeframe/direção/estratégia
    matching_orders = [
        trade for trade in active_trades 
        if trade['par'] == pair 
        and trade['timeframe'] == timeframe 
        and trade['direcao'] == direction 
        and trade['strategy_name'] == strategy_name 
        and trade['estado'] == 'aberto'
    ]
    
    can_open = len(matching_orders) < max_orders
    
    if not can_open:
        logger.info(f"Limite atingido para {strategy_name} em {pair}/{timeframe}/{direction}: {len(matching_orders)}/{max_orders}")
    
    return can_open

def generate_combination_key(pair, direction, strategy_name, contributing_indicators, tf):
    """
    Gera uma chave única para uma combinação de par, direção, estratégia, indicadores e timeframe.
    """
    indicators_str = contributing_indicators if isinstance(contributing_indicators, str) else "_".join(contributing_indicators) if contributing_indicators else "no_indicators"
    combination_key = f"{pair}_{direction}_{strategy_name}_{tf}_{indicators_str}"
    logger.info(f"Chave de combinação gerada: {combination_key}")
    return combination_key

def save_signal(signal_data, accepted, mode):
    """
    Salva um sinal no arquivo CSV.
    """
    try:
        signal_data['signal_id'] = str(uuid.uuid4())
        signal_data['timestamp'] = get_local_timestamp()
        signal_data['estado'] = signal_data.get('estado', 'aberto')
        signal_data['aceito'] = accepted
        signal_data['mode'] = mode
        csv_writer.write_row(signal_data)
        logger.info(f"Sinal salvo com sucesso: {signal_data['signal_id']}, accepted={accepted}, mode={mode}")
    except Exception as e:
        logger.error(f"Erro ao salvar sinal: {e}")

def save_signal_log(signal_data, accepted, mode):
    """
    Salva um log relacionado a um sinal e registra sinais rejeitados em oportunidades_perdidas.csv.
    """
    try:
        log_message = f"Sinal {signal_data.get('signal_id', 'N/A')}: {signal_data}, accepted={accepted}, mode={mode}"
        if accepted:
            logger.info(log_message)
        else:
            logger.warning(log_message)
            # Registrar sinal rejeitado
            MISSED_OPPORTUNITIES_FILE = "oportunidades_perdidas.csv"
            log_entry = {
                'timestamp': get_local_timestamp(),
                'robot_name': signal_data['strategy_name'],
                'par': signal_data['par'],
                'timeframe': signal_data['timeframe'],
                'direcao': signal_data['direcao'],
                'score_tecnico': signal_data.get('score_tecnico', 0.0),
                'contributing_indicators': signal_data['contributing_indicators'],
                'reason': 'Limite de trades simultâneos atingido'
            }

            columns = [
                'timestamp', 'robot_name', 'par', 'timeframe', 'direcao',
                'score_tecnico', 'contributing_indicators', 'reason'
            ]
            if os.path.exists(MISSED_OPPORTUNITIES_FILE):
                df = pd.read_csv(MISSED_OPPORTUNITIES_FILE)
                # Garantir que todas as colunas existam
                for col in columns:
                    if col not in df.columns:
                        df[col] = pd.NA
            else:
                df = pd.DataFrame(columns=columns)

            # Filtrar linhas completamente NA antes da concatenação
            df = df.dropna(how='all')
            df_new_entry = pd.DataFrame([log_entry], columns=columns)
            df = pd.concat([df, df_new_entry], ignore_index=True)
            df.to_csv(MISSED_OPPORTUNITIES_FILE, index=False)
            logger.info(f"Sinal rejeitado registrado em {MISSED_OPPORTUNITIES_FILE}: {log_entry}")
    except Exception as e:
        logger.error(f"Erro ao salvar log do sinal: {e}")

def save_indicator_stats(indicator_stats):
    """
    Salva as estatísticas dos indicadores em um arquivo JSON.
    """
    try:
        with open("indicator_stats.json", "w") as f:
            json.dump(indicator_stats, f, indent=4)
        logger.info("Estatísticas dos indicadores salvas com sucesso em 'indicator_stats.json'.")
    except Exception as e:
        logger.error(f"Erro ao salvar estatísticas dos indicadores: {e}")

def save_report(report_data):
    """
    Salva um relatório de backtest ou simulação em um arquivo JSON.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"report_{timestamp}.json"
        with open(report_filename, "w") as f:
            json.dump(report_data, f, indent=4)
        logger.info(f"Relatório salvo com sucesso em '{report_filename}'.")
    except Exception as e:
        logger.error(f"Erro ao salvar relatório: {e}")

def close_order(signal_id, exit_price, result="Manual"):
    """
    Fecha uma ordem no arquivo sinais_detalhados.csv
    """
    try:
        df = pd.read_csv("sinais_detalhados.csv")
        order_idx = df.index[df['signal_id'] == signal_id].tolist()[0]
        
        df.at[order_idx, 'preco_saida'] = exit_price
        df.at[order_idx, 'timestamp_saida'] = get_local_timestamp()
        df.at[order_idx, 'estado'] = 'fechado'
        df.at[order_idx, 'resultado'] = result
        
        # Calcular lucro
        entry_price = float(df.at[order_idx, 'preco_entrada'])
        direction = df.at[order_idx, 'direcao']
        
        if direction == "LONG":
            profit_percent = ((exit_price - entry_price) / entry_price) * 100
        else:
            profit_percent = ((entry_price - exit_price) / entry_price) * 100
            
        df.at[order_idx, 'lucro_percentual'] = profit_percent
        df.at[order_idx, 'pnl_realizado'] = profit_percent
        
        df.to_csv("sinais_detalhados.csv", index=False)
        logger.info(f"Ordem {signal_id} fechada com sucesso. Resultado: {result}, PNL: {profit_percent:.2f}%")
        return True
    except Exception as e:
        logger.error(f"Erro ao fechar ordem {signal_id}: {e}")
        return False