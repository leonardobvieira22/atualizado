import os
import json

def carregar_wallet():
    wallet_file = "wallet.json"
    
    # Caso o arquivo não exista, inicialize com valores padrão
    if not os.path.exists(wallet_file):
        wallet = {
            "saldo": 1000.0,
            "lucro_total": 0.0,
            "trades_total": 0,
            "trades_tp": 0,
            "trades_sl": 0
        }
        with open(wallet_file, 'w') as f:
            json.dump(wallet, f, indent=4)
        return wallet

    with open(wallet_file, 'r') as f:
        wallet = json.load(f)

    # Garante que todos os campos essenciais estão presentes
    wallet.setdefault("saldo", 1000.0)
    wallet.setdefault("lucro_total", 0.0)
    wallet.setdefault("trades_total", 0)
    wallet.setdefault("trades_tp", 0)
    wallet.setdefault("trades_sl", 0)

    return wallet

def salvar_wallet(wallet):
    with open("wallet.json", 'w') as f:
        json.dump(wallet, f, indent=4)

def registrar_trade_simulado(sinal, direcao, preco_entrada, preco_saida, lucro, resultado):
    wallet = carregar_wallet()
    wallet["lucro_total"] += lucro
    wallet["trades_total"] += 1
    if resultado == 'tp':
        wallet["trades_tp"] += 1
    elif resultado == 'sl':
        wallet["trades_sl"] += 1
    salvar_wallet(wallet)
