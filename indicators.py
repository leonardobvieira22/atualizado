import pandas as pd
import numpy as np
try:
    import ta
except ImportError:
    raise ImportError("Biblioteca 'ta' não encontrada. Instale com 'pip3 install ta'.")
from utils import logger

def calculate_indicators(historical_data, binance_utils):
    """
    Calcula indicadores técnicos para os dados históricos fornecidos.
    """
    try:
        df = historical_data.copy()
        
        # Verificar colunas necessárias
        required_columns = ['close', 'open', 'high', 'low', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"Colunas necessárias ausentes no DataFrame: {missing_columns}")
            return df

        # Verificar dados suficientes
        min_candles = 50
        if len(df) < min_candles:
            logger.warning(f"Dados insuficientes para calcular indicadores: {len(df)} candles, mínimo necessário: {min_candles}")
            return df

        # EMA (ajustado para EMA12 e EMA50)
        logger.debug("Calculando EMA12 e EMA50...")
        df['EMA12'] = ta.trend.EMAIndicator(df['close'], window=12).ema_indicator()
        df['EMA50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        
        # RSI
        logger.debug("Calculando RSI...")
        df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        
        # MACD
        logger.debug("Calculando MACD...")
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        
        # Verificar resultados
        indicator_columns = ['EMA12', 'EMA50', 'RSI', 'MACD', 'MACD_Signal']
        for col in indicator_columns:
            if col not in df.columns:
                logger.error(f"Indicador {col} não foi criado no DataFrame")
            elif df[col].isna().all():
                logger.warning(f"Indicador {col} contém apenas NaN. Últimos dados: {df['close'].tail(5).to_dict()}")
            else:
                logger.info(f"Indicador {col} calculado: Último valor = {df[col].iloc[-1]:.2f}")

        logger.debug(f"Colunas no DataFrame após indicadores: {df.columns.tolist()}")
        return df

    except Exception as e:
        logger.error(f"Erro ao calcular indicadores: {e}")
        return historical_data