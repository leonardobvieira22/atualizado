import time
import pandas as pd
import json
from datetime import datetime
from binance_utils import get_current_price

SINALS_FILE = "sinais_detalhados.csv"
CONFIG_FILE = "config.json"

# Função para fechar ordem
from dashboard_utils import close_order

def auto_close_orders():
    while True:
        try:
            df = pd.read_csv(SINALS_FILE)
            open_orders = df[df['estado'] == 'aberto']
            if open_orders.empty:
                print(f"[{datetime.now()}] Nenhuma ordem aberta para fechar.")
                time.sleep(30)
                continue

            for idx, order in open_orders.iterrows():
                signal_id = order['signal_id']
                par = order['par']
                direction = order['direcao']
                entry_price = float(order['preco_entrada'])
                parametros = json.loads(order['parametros'])
                tp_percent = float(parametros['tp_percent'])
                sl_percent = float(parametros['sl_percent'])
                # Pega preço de mercado atual
                mark_price = get_current_price(None, par, None)
                if mark_price is None:
                    print(f"[{datetime.now()}] Não foi possível obter preço de {par}.")
                    continue

                # Calcula TP/SL
                if direction == "LONG":
                    tp_price = entry_price * (1 + tp_percent / 100)
                    sl_price = entry_price * (1 - sl_percent / 100)
                    if mark_price >= tp_price:
                        print(f"[{datetime.now()}] Fechando ordem {signal_id} (TP atingido) ao preço de mercado {mark_price}")
                        close_order(signal_id, mark_price, "TP")
                    elif mark_price <= sl_price:
                        print(f"[{datetime.now()}] Fechando ordem {signal_id} (SL atingido) ao preço de mercado {mark_price}")
                        close_order(signal_id, mark_price, "SL")
                else:  # SHORT
                    tp_price = entry_price * (1 - tp_percent / 100)
                    sl_price = entry_price * (1 + sl_percent / 100)
                    if mark_price <= tp_price:
                        print(f"[{datetime.now()}] Fechando ordem {signal_id} (TP atingido) ao preço de mercado {mark_price}")
                        close_order(signal_id, mark_price, "TP")
                    elif mark_price >= sl_price:
                        print(f"[{datetime.now()}] Fechando ordem {signal_id} (SL atingido) ao preço de mercado {mark_price}")
                        close_order(signal_id, mark_price, "SL")
        except Exception as e:
            print(f"[{datetime.now()}] Erro ao fechar ordens: {e}")
        time.sleep(30)

if __name__ == "__main__":
    auto_close_orders()
