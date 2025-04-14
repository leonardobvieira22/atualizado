from binance.exceptions import BinanceAPIException
from utils import api_call_with_retry, logger
import requests
import pandas as pd

class BinanceUtils:
    """
    Classe para funções utilitárias específicas da API da Binance.
    """
    def __init__(self, client, config):
        """
        Inicializa o BinanceUtils com um cliente Binance e configurações.

        Args:
            client: Cliente Binance (binance.client.Client).
            config: Configurações do sistema (dicionário).
        """
        self.client = client
        self.config = config

    def calculate_delta_volume(self, symbol):
        """
        Calcula o delta de volume (diferença entre volume de compra e venda) com base no order book.

        Args:
            symbol (str): Símbolo para calcular o delta (ex.: "DOGEUSDT").

        Returns:
            float: Delta de volume (positivo indica mais compras, negativo indica mais vendas).
        """
        try:
            order_book = api_call_with_retry(self.client.get_order_book, symbol=symbol, limit=10)
            bids_volume = sum(float(bid[1]) for bid in order_book['bids'])
            asks_volume = sum(float(ask[1]) for ask in order_book['asks'])
            delta_volume = bids_volume - asks_volume
            logger.debug(f"Delta de volume para {symbol}: {delta_volume} (bids: {bids_volume}, asks: {asks_volume})")
            return delta_volume
        except BinanceAPIException as e:
            logger.error(f"Erro ao calcular delta de volume para {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado ao calcular delta de volume para {symbol}: {e}")
            return None

    def get_sentiment_data(self, symbol):
        """
        Obtém dados de sentimento de mercado via API externa (ex.: LunarCrush).

        Args:
            symbol (str): Símbolo para análise (ex.: "BTCUSDT").

        Returns:
            float: Valor de sentimento (ex.: positivo > 0, negativo < 0) ou None se falhar.
        """
        if not self.config.get('sentiment_enabled', False):
            return 0.0
        try:
            api_key = self.config.get('sentiment_api_key', '')
            source = self.config.get('sentiment_source', 'lunarcrush')
            if source == 'lunarcrush' and api_key:
                base_symbol = symbol.replace("USDT", "")
                response = requests.get(
                    f"https://api.lunarcrush.com/v2?data=assets&key={api_key}&symbol={base_symbol}",
                    timeout=5
                )
                response.raise_for_status()
                data = response.json()
                sentiment = data['data'][0].get('sentiment', 0.0) if data.get('data') else 0.0
                logger.debug(f"Sentimento para {symbol}: {sentiment}")
                return float(sentiment)
            else:
                logger.warning("Configuração de sentimento inválida ou chave API ausente.")
                return 0.0
        except Exception as e:
            logger.error(f"Erro ao obter sentimento para {symbol}: {e}")
            return 0.0

    def calculate_advanced_risk_metrics(self, symbol, timeframe, data):
        """
        Calcula métricas de risco avançadas, incluindo ATR para TP/SL dinâmicos.

        Args:
            symbol (str): Símbolo (ex.: "DOGEUSDT").
            timeframe (str): Intervalo de tempo (ex.: "1h").
            data (pd.DataFrame): Dados históricos com colunas 'high', 'low', 'close'.

        Returns:
            dict: Dicionário com métricas de risco (ex.: {'atr': valor, 'tp': valor, 'sl': valor}).
        """
        try:
            if self.config.get('atr_enabled', False):
                from utils import calculate_atr
                atr = calculate_atr(data, period=self.config.get('atr_period', 14))
                tp = atr * self.config.get('atr_tp_multiplier', 2.0)
                sl = atr * self.config.get('atr_sl_multiplier', 1.0)
                return {
                    'atr': atr,
                    'tp': tp,
                    'sl': sl
                }
            else:
                return {
                    'atr': 0.0,
                    'tp': self.config['stop_padrao']['tp_percent'] / 100,
                    'sl': self.config['stop_padrao']['sl_percent'] / 100
                }
        except Exception as e:
            logger.error(f"Erro ao calcular métricas de risco para {symbol}: {e}")
            return {
                'atr': 0.0,
                'tp': self.config['stop_padrao']['tp_percent'] / 100,
                'sl': self.config['stop_padrao']['sl_percent'] / 100
            }

    def get_historical_volatility(self, symbol, timeframe, limit=50):
        """
        Calcula a volatilidade histórica para suporte ao gerenciamento de risco.

        Args:
            symbol (str): Símbolo (ex.: "DOGEUSDT").
            timeframe (str): Intervalo de tempo (ex.: "1h").
            limit (int): Número de candles para análise.

        Returns:
            float: Volatilidade histórica (desvio padrão dos retornos) ou None se falhar.
        """
        try:
            klines = api_call_with_retry(self.client.get_klines, symbol=symbol, interval=timeframe, limit=limit)
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['close'] = df['close'].astype(float)
            returns = df['close'].pct_change().dropna()
            volatility = returns.std() * (252 ** 0.5)  # Anualizado
            logger.debug(f"Volatilidade histórica para {symbol} ({timeframe}): {volatility}")
            return volatility
        except Exception as e:
            logger.error(f"Erro ao calcular volatilidade para {symbol}: {e}")
            return None