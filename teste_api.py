from binance.client import Client
import os
from config import REAL_API_KEY, REAL_API_SECRET, DRY_RUN_API_KEY, DRY_RUN_API_SECRET, CONFIG
from order_executor import OrderExecutor
from trade_simulator import simulate_trade
import random
import time
from config import REAL_API_KEY as api_key, REAL_API_SECRET as api_secret

client = Client(api_key, api_secret, testnet=True)
try:
    perms = client.get_account_api_permissions()
    print("Chave válida! Permissões:", perms)
except Exception as e:
    print("Erro:", e)

# Inicialização dos clients
client_real = Client(REAL_API_KEY, REAL_API_SECRET)
client_dry = Client(DRY_RUN_API_KEY, DRY_RUN_API_SECRET, testnet=True)

# Configuração base para ambos os modos
base_config = CONFIG.copy()
base_config['strategy_name'] = 'roboreal'
base_config['timeframe'] = '1m'

# Parâmetros de teste
symbols = ['DOGEUSDT', 'XRPUSDT', 'TRXUSDT']
directions = ['LONG', 'SHORT']
capital = 10.0
stop_loss = 1.0
take_profit = 2.0

# --- Ordem Real ---
print('\n--- Testando Ordem Real ---')
order_executor_real = OrderExecutor(client_real, base_config)
for symbol in symbols[:2]:
    for direction in directions:
        print(f'Enviando ordem REAL: {symbol} {direction}')
        result = order_executor_real.executar_ordem(
            par=symbol,
            direcao=direction,
            capital=capital,
            stop_loss=stop_loss,
            take_profit=take_profit,
            mercado='futures',
            dry_run=False
        )
        print('Resultado:', result)
        time.sleep(1)

# --- Ordem Dry Run ---
print('\n--- Testando Ordem Dry Run ---')
order_executor_dry = OrderExecutor(client_dry, base_config)
for symbol in symbols:
    for direction in directions:
        print(f'Enviando ordem DRY RUN: {symbol} {direction}')
        result = order_executor_dry.executar_ordem(
            par=symbol,
            direcao=direction,
            capital=capital,
            stop_loss=stop_loss,
            take_profit=take_profit,
            mercado='futures',
            dry_run=True
        )
        print('Resultado:', result)
        time.sleep(1)

print('\nTestes de ordens reais e dry run finalizados.')