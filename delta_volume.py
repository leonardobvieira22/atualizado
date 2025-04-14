def calcular_delta_volume(client, par, limit=500):
    """
    Calcula o delta de volume (compras - vendas) com base nos trades recentes.
    
    Args:
        client: Instância do Binance Client.
        par: Par de negociação (e.g., "XRP/USDT").
        limit: Número de trades a considerar (padrão: 500).
    
    Returns:
        float: Diferença entre volume de compras e vendas, ou 0.0 em caso de erro.
    """
    try:
        trades = client.futures_aggregate_trades(symbol=par.replace('/', ''), limit=limit)
        if not trades or len(trades) == 0:
            print(f"[DELTA] Nenhum trade retornado para {par}")
            return 0.0
        
        buy_volume = sum(float(t['quantity']) for t in trades if not t['isBuyerMaker'])
        sell_volume = sum(float(t['quantity']) for t in trades if t['isBuyerMaker'])
        delta = buy_volume - sell_volume
        print(f"[DELTA] {par}: Buy Volume={buy_volume:.2f}, Sell Volume={sell_volume:.2f}, Delta={delta:.2f}")
        return delta
    except Exception as e:
        print(f"[DELTA] Erro ao calcular delta volume para {par}: {e}")
        return 0.0