
import os
import json
import pandas as pd
from datetime import datetime

WALLET_FILE = "wallet_dry_run.json"
TRADES_FILE = "trades_simulados.csv"

# Inicializar a carteira simulada
def init_wallet(start_balance=1000):
    if not os.path.exists(WALLET_FILE):
        wallet = {
            "balance": start_balance,
            "initial_balance": start_balance,
            "total_profit": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0
        }
        save_wallet(wallet)
    else:
        wallet = load_wallet()
    return wallet

def save_wallet(wallet):
    with open(WALLET_FILE, "w") as f:
        json.dump(wallet, f, indent=4)

def load_wallet():
    with open(WALLET_FILE, "r") as f:
        return json.load(f)

def log_trade(symbol, direction, entry_price, exit_price, amount_usdt, pnl):
    trade_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "side": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "amount_usdt": amount_usdt,
        "pnl": pnl
    }

    if os.path.exists(TRADES_FILE):
        df = pd.read_csv(TRADES_FILE)
        df = pd.concat([df, pd.DataFrame([trade_data])], ignore_index=True)
    else:
        df = pd.DataFrame([trade_data])
    df.to_csv(TRADES_FILE, index=False)

def update_wallet(pnl):
    wallet = load_wallet()
    wallet["balance"] += pnl
    wallet["total_profit"] += pnl
    wallet["total_trades"] += 1
    if pnl > 0:
        wallet["wins"] += 1
    else:
        wallet["losses"] += 1
    save_wallet(wallet)
