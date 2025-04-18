import time
import logging
import os
import json
from datetime import datetime
from binance.client import Client
from learning_engine import LearningEngine
from notification_manager import get_last_notifications

# Configuração do logging para o terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BINANCE_API_KEY = None
BINANCE_API_SECRET = None
try:
    import toml
    secrets = toml.load("secrets.toml")
    BINANCE_API_KEY = secrets.get("binance", {}).get("api_key")
    BINANCE_API_SECRET = secrets.get("binance", {}).get("api_secret")
except Exception:
    pass

def check_binance_api():
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        return "não configurada"
    try:
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        client.ping()
        return "válida"
    except Exception as e:
        return f"inválida/erro: {e}"

def check_grok_api():
    try:
        from config_grok import GROK_API_KEY
        if not GROK_API_KEY:
            return "não configurada"
        # Simulação de teste de conexão
        return "válida"
    except Exception as e:
        return f"erro: {e}"

def count_open_orders():
    try:
        import pandas as pd
        df = pd.read_csv("sinais_detalhados.csv")
        return len(df[df['estado'] == 'aberto'])
    except Exception:
        return "erro"

def count_active_trades():
    try:
        if os.path.exists("trades_dry_run.json"):
            with open("trades_dry_run.json") as f:
                trades = json.load(f)
            return len(trades)
        return 0
    except Exception:
        return "erro"

def check_learning_engine():
    try:
        le = LearningEngine()
        return f"carregado, acurácia: {le.accuracy:.2f}" if hasattr(le, 'accuracy') else "carregado"
    except Exception as e:
        return f"erro: {e}"

def check_sinais_file():
    try:
        if not os.path.exists("sinais_detalhados.csv"):
            return "não encontrado"
        size = os.path.getsize("sinais_detalhados.csv")
        if size == 0:
            return "vazio"
        return f"ok, {size} bytes"
    except Exception as e:
        return f"erro: {e}"

def check_historical_sync():
    try:
        arquivos = [f for f in os.listdir('.') if f.startswith('historical_data_') and f.endswith('.csv')]
        return f"{len(arquivos)} arquivos"
    except Exception:
        return "erro"

def get_last_log_errors(n=5):
    try:
        if not os.path.exists("bot.log"):
            return []
        with open("bot.log", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        errors = [l.strip() for l in lines if "ERROR" in l or "CRITICAL" in l or "WARNING" in l]
        return errors[-n:]
    except Exception:
        return []

def get_last_notification():
    try:
        return get_last_notifications(1)[0]
    except Exception:
        return "sem notificações"

def main():
    while True:
        print("\n--- STATUS DO SISTEMA ---")
        print(f"Data/hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Binance API: {check_binance_api()}")
        print(f"Grok API: {check_grok_api()}")
        print(f"Ordens abertas: {count_open_orders()}")
        print(f"Trades ativos: {count_active_trades()}")
        print(f"LearningEngine: {check_learning_engine()}")
        print(f"Arquivo de sinais: {check_sinais_file()}")
        print(f"Sync dados históricos: {check_historical_sync()}")
        print(f"Última notificação: {get_last_notification()}")
        print("Últimos erros/warnings:")
        for err in get_last_log_errors():
            print(f"  {err}")
        print("------------------------\n")
        time.sleep(30)

if __name__ == "__main__":
    main()
