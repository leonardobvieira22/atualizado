import streamlit as st
import pandas as pd
import time

# Função para gerar o resumo do motivo do sinal
def gerar_resumo(indicadores, valores):
    """
    Gera um resumo textual com base nos indicadores e seus valores.
    Args:
        indicadores (list): Lista de indicadores utilizados (ex.: ["EMA", "MACD"]).
        valores (dict): Dicionário com os valores dos indicadores.
    Returns:
        str: Resumo textual dos motivos do sinal.
    """
    resumo = []
    if "EMA" in indicadores:
        if valores.get("EMA") == "Cruzamento EMA9 > EMA21":
            resumo.append("Tendência de alta pelo cruzamento de EMAs")
        elif valores.get("EMA") == "Cruzamento EMA9 < EMA21":
            resumo.append("Tendência de baixa pelo cruzamento de EMAs")
    if "MACD" in indicadores:
        if valores.get("MACD") == "Cruzamento de alta":
            resumo.append("MACD indicando alta")
        elif valores.get("MACD") == "Cruzamento de baixa":
            resumo.append("MACD indicando baixa")
    if "RSI" in indicadores:
        rsi_value = valores.get("RSI", 0)
        if rsi_value < 30:
            resumo.append("RSI em sobrevenda")
        elif rsi_value > 70:
            resumo.append("RSI em sobrecompra")
    return ", ".join(resumo) if resumo else "Motivo não especificado"

# Função para calcular confiabilidade histórica
def calcular_confiabilidade_historica(strategy, direction, df_closed):
    """
    Calcula a confiabilidade histórica e o PnL médio de uma estratégia.
    Args:
        strategy (str): Nome da estratégia.
        direction (str): Direção da ordem (ex.: "Compra", "Venda").
        df_closed (pd.DataFrame): DataFrame com ordens fechadas.
    Returns:
        tuple: (win_rate, avg_pnl, total_signals).
    """
    ordens_passadas = df_closed[
        (df_closed["strategy"] == strategy) & (df_closed["direction"] == direction)
    ]
    if len(ordens_passadas) == 0:
        return 0, 0, 0
    acertos = len(ordens_passadas[ordens_passadas["pnl_realizado"] > 0])
    win_rate = (acertos / len(ordens_passadas)) * 100
    avg_pnl = ordens_passadas["pnl_realizado"].mean()
    total_signals = len(ordens_passadas)
    return round(win_rate, 2), round(avg_pnl, 2), total_signals

# Função para verificar e fechar ordens automaticamente
def verificar_e_fechar_ordens(ordens, precos_atuais):
    """
    Verifica se as ordens atingiram TP ou SL e as fecha automaticamente.
    Args:
        ordens (list): Lista de ordens ativas.
        precos_atuais (dict): Dicionário com os preços atuais por par.
    """
    for ordem in ordens:
        par = ordem['par']
        preco_atual = precos_atuais.get(par)
        if not preco_atual:
            continue

        preco_entrada = ordem['preco_entrada']
        tp_percent = ordem['tp_percent'] / 100
        sl_percent = ordem['sl_percent'] / 100

        tp_preco = preco_entrada * (1 + tp_percent)
        sl_preco = preco_entrada * (1 - sl_percent)

        if ordem['direction'] == 'Compra':
            if preco_atual >= tp_preco:
                ordem['status'] = 'Fechado (TP)'
            elif preco_atual <= sl_preco:
                ordem['status'] = 'Fechado (SL)'
        elif ordem['direction'] == 'Venda':
            if preco_atual <= tp_preco:
                ordem['status'] = 'Fechado (TP)'
            elif preco_atual >= sl_preco:
                ordem['status'] = 'Fechado (SL)'

# Dados fictícios para simulação (substitua pelos seus dados reais)
ordens = [
    {
        "signal_id": "123",
        "preco_entrada": 0.2433,
        "quantity": 1.0,
        "tp_percent": 2.0,
        "sl_percent": 1.0,
        "strategy": "extended_target",
        "indicadores": ["EMA", "MACD"],
        "valores_indicadores": {
            "EMA": "Cruzamento EMA9 < EMA21",
            "MACD": "Cruzamento de alta"
        },
        "status": "Aceito",
        "direction": "Compra",
        "par": "TRXUSDT"
    }
]

# DataFrame fictício de ordens fechadas (substitua pelo seu)
df_closed = pd.DataFrame({
    "strategy": ["extended_target", "extended_target"],
    "direction": ["Compra", "Compra"],
    "pnl_realizado": [0.5, -0.2]
})

# Simulação de preços atuais (substitua pela lógica real para obter preços)
precos_atuais = {
    'TRXUSDT': 0.2475,
    'XRPUSDT': 2.1415,
    'DOGEUSDT': 0.1642
}

# Configuração do Dashboard
st.title("UltraBot Dashboard 1.0")

# Seção de Configurações
st.header("Configurações de Estratégia")

# Sliders para score_tecnico e ML_Confidence
score_tecnico_min = st.slider(
    "Score Técnico Mínimo", min_value=0.0, max_value=1.0, value=0.3, step=0.01
)
ml_confidence_min = st.slider(
    "Confiança ML Mínima", min_value=0.0, max_value=1.0, value=0.5, step=0.01
)

# Inputs para TP e SL
tp_percent = st.number_input(
    "TP (%)", min_value=0.1, max_value=100.0, value=2.0, step=0.1
)
sl_percent = st.number_input(
    "SL (%)", min_value=0.1, max_value=100.0, value=1.0, step=0.1
)

# Controles para Indicadores
st.subheader("Indicadores")
indicadores = ["EMA", "MACD", "RSI"]
indicadores_ativos = {}
confianca_minima = {}

for indicador in indicadores:
    indicadores_ativos[indicador] = st.checkbox(f"Ativar {indicador}", value=True)
    if indicadores_ativos[indicador]:
        confianca_minima[indicador] = st.slider(
            f"Confiança Mínima para {indicador}",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.01
        )

# Verificar e fechar ordens antes de renderizar no dashboard
verificar_e_fechar_ordens(ordens, precos_atuais)

# Renderização das Ordens
st.header("Ordens Ativas")
for ordem in ordens:
    # Gerar resumo do motivo do sinal
    resumo = gerar_resumo(ordem["indicadores"], ordem["valores_indicadores"])
    ordem["resumo"] = resumo

    # Calcular confiabilidade histórica
    win_rate, avg_pnl, total_signals = calcular_confiabilidade_historica(
        ordem["strategy"], ordem["direction"], df_closed
    )

    # Renderizar o card da ordem com Markdown
    st.markdown(f"""
    ---
    💰 **Preço de Entrada:** {ordem['preco_entrada']} | **Quantidade:** {ordem['quantity']}  
    🎯 **TP:** +{ordem['tp_percent']}% | **SL:** -{ordem['sl_percent']}%  
    🧠 **Estratégia:** {ordem['strategy']}  

    📌 **Motivos do Sinal:** {ordem['resumo']}  

    📊 **Indicadores Utilizados:**  
    - {', '.join(ordem['indicadores'])}  

    📈 **Confiabilidade Histórica:** {win_rate}% ({total_signals} sinais)  
    💵 **PnL Médio por Sinal:** {avg_pnl}%  
    ✅ **Status:** Sinal {ordem['status']} (Dry-Run Interno)  
    ---
    """)

# Rodapé
st.write("Dashboard atualizado com sucesso!")