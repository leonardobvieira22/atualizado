
from binance.client import Client
import pandas as pd
import numpy as np
import os

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key, api_secret)

def detectar_zonas_de_liquidez(par, timeframe='5m', n_faixas=20):
    try:
        klines = client.get_klines(symbol=par.replace("/", ""), interval=timeframe, limit=500)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'num_trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])

        # Define a faixa de preço
        min_price = df['close'].min()
        max_price = df['close'].max()
        faixa = (max_price - min_price) / n_faixas

        # Cria os bins de volume por preço
        df['faixa_preco'] = ((df['close'] - min_price) // faixa).astype(int)
        volume_por_faixa = df.groupby('faixa_preco')['volume'].sum().reset_index()

        zonas = []
        for _, row in volume_por_faixa.iterrows():
            faixa_idx = row['faixa_preco']
            volume_total = row['volume']
            preco_medio = min_price + faixa_idx * faixa + faixa / 2
            zonas.append((preco_medio, volume_total))

        # Ordena por volume acumulado decrescente
        zonas_ordenadas = sorted(zonas, key=lambda x: x[1], reverse=True)

        return zonas_ordenadas[:5]  # retorna top 5 zonas de liquidez
    except Exception as e:
        print(f"[LIQUIDEZ] Erro ao detectar zonas de liquidez: {e}")
        return []
