from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT

def configurar_alavancagem(client, par, leverage):
    try:
        client.futures_change_leverage(symbol=par.replace('/', ''), leverage=leverage)
        print(f"[EXECUTOR] Alavancagem configurada para {par}: {leverage}x")
    except Exception as e:
        print(f"[EXECUTOR] Erro ao configurar alavancagem: {e}")

def executar_ordem(client, par, direcao, capital, stop_loss, take_profit, mercado='futures', dry_run=False):
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