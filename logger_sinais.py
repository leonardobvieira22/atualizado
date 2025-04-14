import csv
import os
from datetime import datetime

def logar_sinal_detalhado(sinal, arquivo='sinais_detalhados.csv'):
    cabecalho = [
        'timestamp', 'par', 'direcao', 'preco_entrada', 'preco_saida',
        'score_tecnico', 'aceito', 'motivos', 'timeframe', 'resultado',
        'lucro_percentual', 'tempo_operacao', 'pnl_realizado',
        'rsi', 'bollinger_superior', 'bollinger_inferior', 'estocastico', 
        'ema_curta', 'ema_longa', 'delta_volume', 'funding_rate', 'delta_oi', 
        'vwap', 'fibonacci_23.6', 'fibonacci_38.2', 'fibonacci_50', 'fibonacci_61.8',
        'iceberg_detected', 'timeframes_analisados'
    ]
    existe = os.path.exists(arquivo)
    with open(arquivo, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=cabecalho)
        if not existe:
            writer.writeheader()
        writer.writerow({k: sinal.get(k, None) for k in cabecalho})