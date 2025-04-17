import pandas as pd
import requests
from binance.client import Client
import logging
import time
import asyncio
from datetime import datetime
from config_grok import *
import json

# Configurar logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, 
                    format="%(asctime)s - %(levelname)s - %(message)s")

ANALYSIS_INTERVAL = 300  # 5 minutos

class UltraBotGrok:
    def __init__(self):
        self.client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        self.headers = {"Authorization": f"Bearer {XAI_API_KEY}"}

    def is_grok_paused(self):
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
            return config.get("pausar_grok", False)
        except Exception as e:
            logging.error(f"Erro ao ler config.json para pausar_grok: {e}")
            return False

    def fetch_market_data(self, pair, timeframe):
        """Obtém dados de mercado da Binance."""
        klines = self.client.get_klines(symbol=pair, interval=timeframe, limit=100)
        df = pd.DataFrame(klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        return df

    def read_orders(self):
        try:
            return pd.read_csv(ORDERS_FILE)
        except FileNotFoundError:
            return pd.DataFrame(columns=["pair", "timeframe", "insights", "timestamp"])

    def read_prices(self):
        try:
            return pd.read_csv(PRICES_FILE)
        except FileNotFoundError:
            return pd.DataFrame(columns=["pair", "price", "timestamp"])

    def read_log(self):
        try:
            with open(LOG_FILE, "r") as f:
                return f.readlines()[-10:]
        except FileNotFoundError:
            return []

    async def analyze_with_grok(self, data, pair, log_lines):
        orders = self.read_orders().tail(5).to_string()
        prices = self.read_prices().tail(5).to_string()
        prompt = (
            f"Analise em tempo real para {pair}:\n"
            f"Dados de mercado: {data.tail(10).to_string()}\n"
            f"Ordens recentes: {orders}\n"
            f"Preços: {prices}\n"
            f"Logs: {''.join(log_lines)}\n"
            f"Identifique tendências, anomalias e sugira ações. Busque sentimentos no X para {pair}."
        )
        payload = {
            "model": "grok-beta",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }
        try:
            response = requests.post(
                f"{XAI_API_URL}/chat/completions",
                json=payload, headers=self.headers, stream=True
            )
            insights = ""
            for chunk in response.iter_lines():
                if chunk:
                    insights += chunk.decode("utf-8") + "\n"
            return insights
        except Exception as e:
            logging.error(f"Erro na API do Grok: {e}")
            return f"Erro na análise: {e}"

    async def run(self):
        while True:
            if self.is_grok_paused():
                logging.info("Execução do Grok pausada por configuração (pausar_grok=true). Aguardando...")
                await asyncio.sleep(30)
                continue
            for pair in TRADING_PAIRS:
                for timeframe in TIMEFRAMES:
                    data = self.fetch_market_data(pair, timeframe)
                    log_lines = self.read_log()
                    insights = await self.analyze_with_grok(data, pair, log_lines)
                    logging.info(f"Insights para {pair} ({timeframe}): {insights}")
                    pd.DataFrame({
                        "pair": [pair],
                        "timeframe": [timeframe],
                        "insights": [insights],
                        "timestamp": [datetime.now()]
                    }).to_csv(ORDERS_FILE, mode="a", index=False, 
                              header=not pd.io.common.file_exists(ORDERS_FILE))
            await asyncio.sleep(ANALYSIS_INTERVAL)

def main():
    bot = UltraBotGrok()
    asyncio.run(bot.run())

if __name__ == "__main__":
    main()
