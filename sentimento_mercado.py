def obter_oi_e_funding(client, par, period='5m'):
    """
    Obtém o sentimento de mercado com base na taxa de funding e variação do open interest.
    
    Args:
        client: Instância do Binance Client.
        par: Par de negociação (e.g., "XRP/USDT").
        period: Período para o histórico de open interest (e.g., '5m', '15m', '1h').
    
    Returns:
        dict: Contendo 'funding_rate' (taxa de funding) e 'delta_oi' (variação do OI),
              ou valores padrão (0.0) em caso de erro.
    """
    try:
        # Obter taxa de funding mais recente
        funding_data = client.futures_funding_rate(symbol=par.replace('/', ''), limit=1)
        if not funding_data:
            print(f"[SENTIMENTO] Nenhuma taxa de funding retornada para {par}")
            return {"funding_rate": 0.0, "delta_oi": 0.0}
        funding = float(funding_data[0]['fundingRate'])

        # Obter open interest atual
        oi_data = client.futures_open_interest(symbol=par.replace('/', ''))
        if not oi_data:
            print(f"[SENTIMENTO] Nenhum open interest retornado para {par}")
            return {"funding_rate": 0.0, "delta_oi": 0.0}
        oi = float(oi_data['openInterest'])

        # Obter open interest anterior para calcular delta
        oi_hist = client.futures_open_interest_hist(symbol=par.replace('/', ''), period=period, limit=2)
        if len(oi_hist) < 2:
            print(f"[SENTIMENTO] Histórico de OI insuficiente para {par}")
            return {"funding_rate": funding, "delta_oi": 0.0}
        oi_prev = float(oi_hist[0]['sumOpenInterest'])
        delta_oi = oi - oi_prev

        print(f"[SENTIMENTO] {par}: Funding Rate={funding:.6f}, Delta OI={delta_oi:.2f}")
        return {
            "funding_rate": funding,
            "delta_oi": delta_oi
        }
    except Exception as e:
        print(f"[SENTIMENTO] Erro ao obter OI/Funding para {par}: {e}")
        return {"funding_rate": 0.0, "delta_oi": 0.0}