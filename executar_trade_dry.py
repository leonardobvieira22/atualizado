import random
import pandas as pd
import os

def simular_trade(sinal, preco_entrada, direcao, config):
    preco_atual = preco_entrada
    stop_loss = preco_entrada * (1 - config["sl_porcentagem"] / 100) if direcao == "buy" else preco_entrada * (1 + config["sl_porcentagem"] / 100)
    take_profit = preco_entrada * (1 + config["tp_porcentagem"] / 100) if direcao == "buy" else preco_entrada * (1 - config["tp_porcentagem"] / 100)
    
    resultado = random.choice(["TP", "SL"])
    preco_saida = take_profit if resultado == "TP" else stop_loss
    lucro = (preco_saida - preco_entrada) * config["capital_por_trade"] * config["leverage"] / preco_entrada if direcao == "buy" else (preco_entrada - preco_saida) * config["capital_por_trade"] * config["leverage"] / preco_entrada
    
    return {
        "preco_saida": preco_saida,
        "lucro": lucro,
        "resultado": resultado
    }