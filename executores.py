import pandas as pd
import json
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT
from trade_manager import check_timeframe_direction_limit, check_active_trades

def configurar_alavancagem(client, par, leverage):
    try:
        client.futures_change_leverage(symbol=par.replace('/', ''), leverage=leverage)
        print(f"[EXECUTOR] Alavancagem configurada para {par}: {leverage}x")
    except Exception as e:
        print(f"[EXECUTOR] Erro ao configurar alavancagem: {e}")

def executar_ordem(client, par, direcao, capital, stop_loss, take_profit, mercado='futures', dry_run=False):
    # Checagem de pausa de ordens
    try:
        with open("config.json", "r") as f:
            config_json = json.load(f)
        if config_json.get("pausar_ordens", False):
            print("[EXECUTOR] Execução de ordens pausada por configuração (pausar_ordens=true). Nenhuma ordem será executada.")
            return
    except Exception as e:
        print(f"[EXECUTOR] Erro ao ler config.json para pausar_ordens: {e}")

    # Checagem centralizada de limite de ordens por direção/par/timeframe/robô
    # ATENÇÃO: É necessário passar o config correto para os parâmetros abaixo
    from config import CONFIG
    strategy_name = CONFIG.get('strategy_name', 'default')
    timeframe = CONFIG.get('timeframe', '1h')
    active_trades = check_active_trades()
    can_open = check_timeframe_direction_limit(
        par.replace('/', ''),
        timeframe,
        direcao.upper() if direcao in ['LONG', 'SHORT'] else ('LONG' if direcao == 'buy' else 'SHORT'),
        strategy_name,
        active_trades,
        CONFIG
    )
    if not can_open:
        print(f"[EXECUTOR] Limite de trades simultâneos atingido para {strategy_name} em {par}/{timeframe}/{direcao}. Ordem não será criada.")
        with open("oportunidades_perdidas.csv", "a") as f:
            f.write(f"{{}} ,{{}},{{}},{{}},{{}},N/A,N/A,Limite de trades simultâneos atingido\n".format(pd.Timestamp.now(), strategy_name, par, timeframe, direcao))
        return

    if dry_run:
        print(f"[EXECUTOR] Simulando ordem {direcao} em {par} ({mercado}) com capital {capital}")
        return
    
    lado = SIDE_BUY if direcao == "buy" else SIDE_SELL
    try:
        preco = float(client.futures_symbol_ticker(symbol=par.replace('/', ''))['price'])
        quantidade = (capital * CONFIG["leverage"]) / preco
        
        if mercado == 'futures':
            client.futures_change_margin_type(symbol=par.replace('/', ''), marginType=CONFIG["margin_type"])
            ordem = client.futures_create_order(
                symbol=par.replace('/', ''),
                side=lado,
                type=ORDER_TYPE_MARKET,
                quantity=quantidade
            )
            sl_preco = preco * (1 - stop_loss / 100) if direcao == "buy" else preco * (1 + stop_loss / 100)
            tp_preco = preco * (1 + take_profit / 100) if direcao == "buy" else preco * (1 - take_profit / 100)
            client.futures_create_order(
                symbol=par.replace('/', ''),
                side=SIDE_SELL if direcao == "buy" else SIDE_BUY,
                type=ORDER_TYPE_LIMIT,
                quantity=quantidade,
                price=tp_preco,
                stopPrice=tp_preco,
                timeInForce='GTC'
            )
            client.futures_create_order(
                symbol=par.replace('/', ''),
                side=SIDE_SELL if direcao == "buy" else SIDE_BUY,
                type=ORDER_TYPE_LIMIT,
                quantity=quantidade,
                price=sl_preco,
                stopPrice=sl_preco,
                timeInForce='GTC'
            )
            print(f"[EXECUTOR] Ordem {direcao} executada em {par}: {ordem}")
    except Exception as e:
        print(f"[EXECUTOR] Erro ao executar ordem: {e}")