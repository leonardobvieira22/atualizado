import pandas as pd
import os
from utils import logger, CsvWriter
import uuid
from datetime import datetime
import json

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
        signal_data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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