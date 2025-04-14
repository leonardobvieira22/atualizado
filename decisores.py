# Este módulo pode ser expandido para unificar análise técnica e IA

def decidir_entrada(rsi, adx, ema, confianca_ia):
    score = 0

    # Analisando o indicador RSI
    if rsi < 30:
        score += 30

    # Analisando o indicador ADX
    if adx > 20:
        score += 30

    # Verificando a confiança da IA
    if confianca_ia > 50:
        score += 40

    # Retorna True se o score for maior ou igual a 70
    return score >= 70
