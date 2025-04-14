def detectar_topos_e_fundos(candles):
    """
    Detecta topos (highs) e fundos (lows) em uma lista de candles.
    Retorna listas de preços correspondentes aos topos e fundos.
    """
    topos = []
    fundos = []
    
    for i in range(1, len(candles) - 1):
        # Candle atual
        high_atual = float(candles[i][2])  # Preço máximo (high)
        low_atual = float(candles[i][3])   # Preço mínimo (low)
        
        # Candles anterior e próximo
        high_anterior = float(candles[i - 1][2])
        high_proximo = float(candles[i + 1][2])
        low_anterior = float(candles[i - 1][3])
        low_proximo = float(candles[i + 1][3])
        
        # Topo: high atual é maior que o anterior e o próximo
        if high_atual > high_anterior and high_atual > high_proximo:
            topos.append(high_atual)
        
        # Fundo: low atual é menor que o anterior e o próximo
        if low_atual < low_anterior and low_atual < low_proximo:
            fundos.append(low_atual)
    
    return topos, fundos