import os
import pandas as pd
from sentimento_mercado import obter_oi_e_funding
from delta_volume import calcular_delta_volume
from icebergs import detectar_iceberg

def ajustar_pesos(pesos_iniciais, df_sinais):
    acertos = {ind: {"tp": 0, "sl": 0} for ind in pesos_iniciais}
    for _, row in df_sinais.iterrows():
        if pd.isna(row["resultado"]):
            continue
        for motivo in row["motivos"].split(", "):
            for ind in acertos:
                if ind in motivo.lower():
                    acertos[ind]["tp" if row["resultado"] == "TP" else "sl"] += 1
    for ind in acertos:
        total = acertos[ind]["tp"] + acertos[ind]["sl"]
        if total > 0:
            taxa_acerto = acertos[ind]["tp"] / total
            pesos_iniciais[ind] = max(0.05, min(0.30, taxa_acerto * 0.3))
    return pesos_iniciais

def ajustar_config_com_confiabilidade(config, df_sinais, min_trades=20):
    acertos = {ind: {"tp": 0, "sl": 0} for ind in ["rsi", "bollinger", "estocastico", "volume", "ema", "sentimento", "vwap", "fibonacci"]}
    for _, row in df_sinais.iterrows():
        if pd.isna(row["resultado"]):
            continue
        for motivo in row["motivos"].split(", "):
            for ind in acertos:
                if ind in motivo.lower():
                    acertos[ind]["tp" if row["resultado"] == "TP" else "sl"] += 1
    
    for ind in acertos:
        total = acertos[ind]["tp"] + acertos[ind]["sl"]
        if total >= min_trades:
            taxa_acerto = acertos[ind]["tp"] / total * 100
            config[f"usar_{ind}"] = taxa_acerto >= 50
            print(f"[CONFIG] {ind.capitalize()}: {taxa_acerto:.2f}% ({acertos[ind]['tp']}/{total}) - {'Ativado' if config[f'usar_{ind}'] else 'Desativado'}")
    return config

def ajustar_timeframes_com_confiabilidade(tf_configs, df_sinais, min_trades=20):
    acertos_tf = {tf: {"tp": 0, "sl": 0} for tf in tf_configs}
    for _, row in df_sinais.iterrows():
        if pd.isna(row["resultado"]):
            continue
        tf = row["timeframe"]
        if tf in acertos_tf:
            acertos_tf[tf]["tp" if row["resultado"] == "TP" else "sl"] += 1
    
    for tf in list(tf_configs.keys()):
        total = acertos_tf[tf]["tp"] + acertos_tf[tf]["sl"]
        if total >= min_trades and acertos_tf[tf]["tp"] / total * 100 < 50:
            del tf_configs[tf]
            print(f"[CONFIG] Timeframe {tf} desativado: {acertos_tf[tf]['tp']}/{total}")
    return tf_configs

def validar_sinal(
    rsi, adx, ema, macd, volume, bollinger, estocastico, vwap, fibonacci,
    usar_rsi=True, usar_adx=False, usar_ema=True, usar_macd=False,
    usar_bollinger=True, usar_estocastico=True, usar_vwap=True, usar_fibonacci=True,
    stop_loss=3.0, take_profit=6.0, par=None, preco_atual=None, client=None, timeframes_analisados=None
):
    pesos = {
        "rsi": 0.15, "bollinger": 0.10, "estocastico": 0.10, "volume": 0.10, "ema": 0.10,
        "sentimento": 0.15, "iceberg": 0.10, "vwap": 0.10, "fibonacci": 0.10
    }
    if os.path.exists("sinais_detalhados.csv"):
        df_sinais = pd.read_csv("sinais_detalhados.csv")
        pesos = ajustar_pesos(pesos, df_sinais)

    motivos = []
    score_total = 0.0
    direcao = None

    if usar_rsi and rsi is not None:
        if rsi < 30:
            motivos.append("RSI < 30 (compra)")
            direcao = 'buy'
            score_total += pesos["rsi"] * 100
        elif rsi > 70:
            motivos.append("RSI > 70 (venda)")
            direcao = 'sell'
            score_total += pesos["rsi"] * 100

    if usar_bollinger and bollinger and preco_atual:
        superior, _, inferior = bollinger
        if preco_atual < inferior:
            motivos.append("Abaixo de Bollinger (compra)")
            direcao = 'buy' if direcao is None else direcao
            score_total += pesos["bollinger"] * 100
        elif preco_atual > superior:
            motivos.append("Acima de Bollinger (venda)")
            direcao = 'sell' if direcao is None else direcao
            score_total += pesos["bollinger"] * 100

    if usar_estocastico and estocastico is not None:
        if estocastico < 20:
            motivos.append("Estocástico < 20 (compra)")
            direcao = 'buy' if direcao is None else direcao
            score_total += pesos["estocastico"] * 100
        elif estocastico > 80:
            motivos.append("Estocástico > 80 (venda)")
            direcao = 'sell' if direcao is None else direcao
            score_total += pesos["estocastico"] * 100

    if volume and par and client:
        delta_vol = calcular_delta_volume(client, par)
        if delta_vol > 1000:
            motivos.append("Delta volume positivo (compra)")
            direcao = 'buy' if direcao is None else direcao
            score_total += pesos["volume"] * 50
        elif delta_vol < -1000:
            motivos.append("Delta volume negativo (venda)")
            direcao = 'sell' if direcao is None else direcao
            score_total += pesos["volume"] * 50

    if usar_ema and ema is not None:
        ema_curta, ema_longa = ema
        if ema_curta > ema_longa:
            motivos.append("EMA curta > longa (compra)")
            direcao = 'buy' if direcao is None else direcao
            score_total += pesos["ema"] * 50
        elif ema_curta < ema_longa:
            motivos.append("EMA curta < longa (venda)")
            direcao = 'sell' if direcao is None else direcao
            score_total += pesos["ema"] * 50

    if par and client:
        sentimento = obter_oi_e_funding(client, par)
        if sentimento['funding_rate'] > 0.01 and sentimento['delta_oi'] > 0:
            motivos.append("Sentimento bullish")
            direcao = 'buy' if direcao is None else direcao
            score_total += pesos["sentimento"] * 75
        elif sentimento['funding_rate'] < -0.01 and sentimento['delta_oi'] < 0:
            motivos.append("Sentimento bearish")
            direcao = 'sell' if direcao is None else direcao
            score_total += pesos["sentimento"] * 75

    if usar_vwap and vwap and preco_atual:
        if preco_atual < vwap:
            motivos.append("Preço < VWAP (compra)")
            direcao = 'buy' if direcao is None else direcao
            score_total += pesos["vwap"] * 75
        elif preco_atual > vwap:
            motivos.append("Preço > VWAP (venda)")
            direcao = 'sell' if direcao is None else direcao
            score_total += pesos["vwap"] * 75

    if usar_fibonacci and fibonacci and preco_atual:
        for nivel, valor in fibonacci.items():
            if abs(preco_atual - valor) / preco_atual < 0.01:
                if direcao == 'buy' and preco_atual < valor:
                    motivos.append(f"Suporte Fibonacci {nivel} (compra)")
                    score_total += pesos["fibonacci"] * 50
                elif direcao == 'sell' and preco_atual > valor:
                    motivos.append(f"Resistência Fibonacci {nivel} (venda)")
                    score_total += pesos["fibonacci"] * 50

    if par and preco_atual and client and direcao:
        iceberg = detectar_iceberg(client, par, preco_atual, 'compra' if direcao == 'buy' else 'venda')
        if iceberg:
            motivos.append("Iceberg detectado (risco)")
            score_total -= pesos["iceberg"] * 100

    pode_entrar = score_total >= 50 and direcao is not None
    return {
        "pode_entrar": pode_entrar,
        "motivos": motivos,
        "direcao": direcao,
        "score": round(score_total, 2),
        "rsi": rsi,
        "bollinger_superior": bollinger[0] if bollinger else None,
        "bollinger_inferior": bollinger[2] if bollinger else None,
        "estocastico": estocastico,
        "ema_curta": ema[0] if ema else None,
        "ema_longa": ema[1] if ema else None,
        "delta_volume": delta_vol if 'delta_vol' in locals() else None,
        "funding_rate": sentimento['funding_rate'] if 'sentimento' in locals() else None,
        "delta_oi": sentimento['delta_oi'] if 'sentimento' in locals() else None,
        "vwap": vwap,
        "fibonacci_23.6": fibonacci["23.6%"] if fibonacci else None,
        "fibonacci_38.2": fibonacci["38.2%"] if fibonacci else None,
        "fibonacci_50": fibonacci["50%"] if fibonacci else None,
        "fibonacci_61.8": fibonacci["61.8%"] if fibonacci else None,
        "iceberg_detected": iceberg if 'iceberg' in locals() else False,
        "timeframes_analisados": timeframes_analisados
    }