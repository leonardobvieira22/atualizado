import pandas as pd  # Importação adicionada para pd
import os  # Importação adicionada para os
from datetime import datetime, timedelta  # Importação adicionada para datetime e timedelta
import pytz
from utils import logger, api_call_with_retry

def convert_timestamp_to_local(timestamp):
    """Converte timestamp da Binance (UTC) para horário local"""
    utc_time = datetime.fromtimestamp(timestamp/1000.0, tz=pytz.UTC)
    local_timezone = datetime.now().astimezone().tzinfo
    return utc_time.astimezone(local_timezone)

def get_historical_data(client, symbol, timeframe, limit=100):
    """
    Obtém dados históricos de preços para um dado símbolo e timeframe.
    
    Args:
        client: Cliente Binance.
        symbol (str): Símbolo (ex.: "XRPUSDT").
        timeframe (str): Intervalo de tempo (ex.: "1m").
        limit (int): Número de candles a serem buscados.
    
    Returns:
        pd.DataFrame: DataFrame com os dados históricos.
    """
    try:
        logger.info(f"Obtendo dados históricos para {symbol} no timeframe {timeframe}...")
        klines = api_call_with_retry(client.get_klines, symbol=symbol, interval=timeframe, limit=limit)
        if not klines:
            logger.warning(f"Nenhum dado histórico retornado para {symbol} ({timeframe}).")
            return pd.DataFrame()
        
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # Converter timestamps para horário local
        df['timestamp'] = df['timestamp'].apply(convert_timestamp_to_local)
        df['close_time'] = df['close_time'].apply(convert_timestamp_to_local)
        
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        if len(df) < limit:
            logger.warning(f"Dados insuficientes para {symbol} no timeframe {timeframe}: {len(df)} candles obtidos, esperado {limit}.")
        
        logger.info(f"Dados históricos obtidos com sucesso para {symbol} no timeframe {timeframe}: {len(df)} candles.")
        return df
    except Exception as e:
        logger.error(f"Erro ao obter dados históricos para {symbol} ({timeframe}): {e}")
        return pd.DataFrame()

def get_funding_rate(client, symbol, config, mode="dry_run"):
    """
    Obtém a taxa de funding para um símbolo.
    
    Args:
        client: Cliente Binance.
        symbol (str): Símbolo (ex.: "XRPUSDT").
        config: Configurações do sistema.
        mode (str): Modo de operação ("dry_run" ou "real").
    
    Returns:
        float: Taxa de funding ou valor padrão.
    """
    try:
        if mode == "dry_run":
            return config.get("backtest_funding_rate", 0.0001)
        funding_info = api_call_with_retry(client.get_funding_rate, symbol=symbol, limit=1)
        if funding_info and isinstance(funding_info, list) and len(funding_info) > 0:
            funding_rate = float(funding_info[0]['fundingRate'])
            logger.debug(f"Taxa de funding obtida para {symbol}: {funding_rate}")
            return funding_rate
        logger.warning(f"Taxa de funding não disponível para {symbol}. Usando valor padrão.")
        return 0.0001
    except Exception as e:
        logger.error(f"Erro ao obter taxa de funding para {symbol}: {e}")
        return 0.0001

def get_current_price(client, symbol, config):
    """
    Obtém o preço atual de um símbolo.
    
    Args:
        client: Cliente Binance.
        symbol (str): Símbolo (ex.: "XRPUSDT").
        config: Configurações do sistema.
    
    Returns:
        float: Preço atual ou None em caso de erro.
    """
    try:
        price_data = api_call_with_retry(client.get_symbol_ticker, symbol=symbol)
        if not price_data:
            logger.warning(f"Não foi possível obter preço para {symbol}.")
            return None
        price = float(price_data['price'])
        
        # Registrar preço em precos_log.csv
        log_entry = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'par': symbol,
            'price': price
        }
        columns = ['timestamp', 'par', 'price']
        if os.path.exists("precos_log.csv"):
            df = pd.read_csv("precos_log.csv")
        else:
            df = pd.DataFrame(columns=columns)
        df = pd.concat([df, pd.DataFrame([log_entry])], ignore_index=True)
        df.to_csv("precos_log.csv", index=False)
        logger.info(f"Preço salvo em 'precos_log.csv' para {symbol}: {price}")
        
        return price
    except Exception as e:
        logger.error(f"Erro ao obter preço atual para {symbol}: {e}")
        return None

def get_quantity(config, symbol, price):
    """
    Calcula a quantidade a ser negociada com base no risco e preço atual.
    
    Args:
        config: Configurações do sistema.
        symbol (str): Símbolo (ex.: "XRPUSDT").
        price (float): Preço atual do símbolo.
    
    Returns:
        float: Quantidade a ser negociada ou None em caso de erro.
    """
    try:
        # Usar quantity_in_usdt (adicionado ao config)
        quantity_in_usdt = config.get('quantity_in_usdt', 10.0)  # Valor padrão: 10 USDT
        if price <= 0:
            logger.error(f"Preço inválido para {symbol}: {price}")
            return None
        quantity = quantity_in_usdt / price
        logger.debug(f"Quantidade calculada para {symbol}: {quantity} (price={price}, quantity_in_usdt={quantity_in_usdt})")
        return quantity
    except Exception as e:
        logger.error(f"Erro ao calcular quantidade para {symbol}: {e}")
        return None

def is_candle_closed(client, symbol, timeframe):
    """
    Verifica se a vela atual para um símbolo e timeframe está fechada.
    
    Args:
        client: Cliente Binance.
        symbol (str): Símbolo (ex.: "XRPUSDT").
        timeframe (str): Intervalo de tempo (ex.: "1m").
    
    Returns:
        tuple: (bool, datetime) - (Se a vela está fechada, timestamp de fechamento).
    """
    try:
        klines = api_call_with_retry(client.get_klines, symbol=symbol, interval=timeframe, limit=1)
        if not klines:
            logger.warning(f"Não foi possível obter klines para {symbol} ({timeframe}).")
            return False, None
        
        close_time_ms = klines[0][6]  # Close time em milissegundos
        close_time = datetime.fromtimestamp(close_time_ms / 1000)
        current_time = datetime.now()
        
        tf_minutes = {
            "1m": 1, "5m": 5, "15m": 15, "1h": 60,
            "4h": 240, "1d": 1440
        }
        interval_minutes = tf_minutes.get(timeframe, 1)
        next_open_time = close_time + timedelta(minutes=interval_minutes)
        
        is_closed = current_time >= next_open_time
        logger.debug(f"Verificando vela para {symbol} ({timeframe}): Fechada={is_closed}, Close Time={close_time}, Next Open={next_open_time}")
        return is_closed, close_time
    except Exception as e:
        logger.error(f"Erro ao verificar se a vela está fechada para {symbol} ({timeframe}): {e}")
        return False, None