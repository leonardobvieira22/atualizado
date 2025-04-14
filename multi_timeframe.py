
from binance.client import Client
import pandas as pd
import numpy as np
import os
import ta

# Carrega chave da API da Binance se necessário (usado para consulta de dados históricos)
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key, api_secret)

def validar_timeframe_superior(par, timeframe_secundario='1h'):
    try:
        klines = client.get_klines(symbol=par.replace("/", ""), interval=timeframe_secundario, limit=100)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'num_trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])

        # Indicadores no timeframe superior
        df['ema21'] = ta.trend.ema_indicator(df['close'], window=21)
        df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)

        # Verificação de confirmação:
        ultima = df.iloc[-1]

        tendencia_alta = ultima['ema21'] > ultima['ema50']
        rsi_ok = ultima['rsi'] < 70  # não sobrecomprado
        adx_ok = ultima['adx'] > 20  # tendência estabelecida

        if tendencia_alta and rsi_ok and adx_ok:
            return True
        else:
            return False

    except Exception as e:
        print(f"[MTF] Erro ao validar timeframe superior: {e}")
        return True  # Por segurança, se falhar na verificação, deixa passar
