import pandas as pd
import numpy as np
import uuid
from datetime import datetime, timedelta
import json

# Configurações
PAIRS = ["XRPUSDT", "DOGEUSDT", "TRXUSDT"]
NUM_SINAIS = 1000  # Número total de sinais a gerar (500 TP, 500 SL)

# Colunas esperadas para o arquivo sinais_detalhados.csv
COLUMNS = [
    'signal_id', 'timestamp', 'par', 'timeframe', 'direcao', 'preco_entrada',
    'quantity', 'score_tecnico', 'motivos', 'funding_rate', 'localizadores',
    'parametros', 'timeframes_analisados', 'aceito', 'resultado', 'preco_saida',
    'lucro_percentual', 'pnl_realizado', 'timestamp_saida', 'mode',
    'contributing_indicators', 'strategy_name', 'estado', 'combination_key',
    'historical_win_rate', 'avg_pnl', 'side_performance', 'timeframe_weight'
]

def generate_historical_data():
    print("Gerando dados históricos...")
    data = []
    start_time = datetime.now() - timedelta(days=30)

    # Gerar 500 sinais com resultado TP e 500 com resultado SL
    for i in range(NUM_SINAIS):
        signal_id = str(uuid.uuid4())
        timestamp = (start_time + timedelta(minutes=i * 10)).strftime("%Y-%m-%d %H:%M:%S")
        par = np.random.choice(PAIRS)
        timeframe = "1h"
        direcao = np.random.choice(["LONG", "SHORT"])
        preco_entrada = np.random.uniform(0.1, 2.0)
        quantity = np.random.uniform(1, 10)
        score_tecnico = np.random.uniform(0.3, 0.8)
        motivos = json.dumps(["Teste histórico"])
        funding_rate = 0.0001
        localizadores = json.dumps({})
        parametros = json.dumps({"tp_percent": 2.0, "sl_percent": 1.0, "leverage": 10})
        timeframes_analisados = json.dumps(["1h"])
        aceito = True
        contributing_indicators = "SMA;EMA"
        strategy_name = "all"
        combination_key = f"{par}:{direcao}:all:SMA;EMA:1h"
        historical_win_rate = 0.5
        avg_pnl = 0.0
        side_performance = json.dumps({"LONG": 0.0, "SHORT": 0.0})
        timeframe_weight = 1.0

        # Determinar o resultado (50% TP, 50% SL)
        resultado = "TP" if i < NUM_SINAIS // 2 else "SL"
        if resultado == "TP":
            lucro_percentual = 2.0  # Simulando lucro de 2% para TP
            preco_saida = preco_entrada * (1 + 0.02) if direcao == "LONG" else preco_entrada * (1 - 0.02)
        else:
            lucro_percentual = -1.0  # Simulando perda de 1% para SL
            preco_saida = preco_entrada * (1 - 0.01) if direcao == "LONG" else preco_entrada * (1 + 0.01)

        timestamp_saida = (start_time + timedelta(minutes=i * 10 + 5)).strftime("%Y-%m-%d %H:%M:%S")
        estado = "fechado"

        sinal = {
            "signal_id": signal_id,
            "timestamp": timestamp,
            "par": par,
            "timeframe": timeframe,
            "direcao": direcao,
            "preco_entrada": preco_entrada,
            "quantity": quantity,
            "score_tecnico": score_tecnico,
            "motivos": motivos,
            "funding_rate": funding_rate,
            "localizadores": localizadores,
            "parametros": parametros,
            "timeframes_analisados": timeframes_analisados,
            "aceito": aceito,
            "resultado": resultado,
            "preco_saida": preco_saida,
            "lucro_percentual": lucro_percentual,
            "pnl_realizado": lucro_percentual,
            "timestamp_saida": timestamp_saida,
            "mode": "backtest",
            "contributing_indicators": contributing_indicators,
            "strategy_name": strategy_name,
            "estado": estado,
            "combination_key": combination_key,
            "historical_win_rate": historical_win_rate,
            "avg_pnl": avg_pnl,
            "side_performance": side_performance,
            "timeframe_weight": timeframe_weight
        }
        data.append(sinal)

    # Criar DataFrame e salvar no arquivo
    df = pd.DataFrame(data, columns=COLUMNS)
    df.to_csv("sinais_detalhados.csv", index=False)
    print(f"Gerados {len(df)} sinais históricos. Total de TP: {len(df[df['resultado'] == 'TP'])}, Total de SL: {len(df[df['resultado'] == 'SL'])}")
    print("Dados salvos em 'sinais_detalhados.csv'.")

if __name__ == "__main__":
    generate_historical_data()