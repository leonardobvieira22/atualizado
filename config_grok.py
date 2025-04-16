import os
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = os.getenv("XAI_API_URL", "https://api.x.ai/v1")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL", 60))
TRADING_PAIRS = os.getenv("TRADING_PAIRS", "XRPUSDT,DOGEUSDT,TRXUSDT").split(",")
TIMEFRAMES = os.getenv("TIMEFRAMES", "1m,5m,15m").split(",")
ORDERS_FILE = os.getenv("ORDERS_FILE", "sinais_detalhados.csv")
PRICES_FILE = os.getenv("PRICES_FILE", "precos_log.csv")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
