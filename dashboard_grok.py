import streamlit as st
import pandas as pd
import plotly.graph_objs as go
from config_grok import *
from datetime import datetime

st.set_page_config(page_title="UltraBot Grok Dashboard", layout="wide", page_icon="🤖", initial_sidebar_state="expanded")

st.title("📊 UltraBot + Grok: Dashboard de Insights em Tempo Real")

# Carregar dados de insights
def load_insights():
    try:
        df = pd.read_csv(ORDERS_FILE)
        df = df.sort_values("timestamp", ascending=False)
        return df
    except Exception:
        return pd.DataFrame(columns=["pair", "timeframe", "insights", "timestamp"])

# Carregar preços
def load_prices():
    try:
        df = pd.read_csv(PRICES_FILE)
        df = df.sort_values("timestamp", ascending=False)
        return df
    except Exception:
        return pd.DataFrame(columns=["pair", "price", "timestamp"])

# Insights em tempo real
st.subheader("🧠 Insights do Grok (minuto a minuto)")
insights_df = load_insights()
if not insights_df.empty:
    for i, row in insights_df.head(5).iterrows():
        st.info(f"[{row['timestamp']}] {row['pair']} ({row['timeframe']}): {row['insights']}")
else:
    st.warning("Nenhum insight disponível ainda.")

# Tabela de ordens recentes
st.subheader("📋 Ordens Recentes")
st.dataframe(insights_df[["pair", "timeframe", "timestamp"]].head(10))

# Tabela de preços recentes
st.subheader("💲 Preços Recentes")
prices_df = load_prices()
st.dataframe(prices_df.head(10))

# Gráficos de preço por par
st.subheader("📈 Gráficos de Preço (Plotly)")
for pair in TRADING_PAIRS:
    pair_prices = prices_df[prices_df["pair"] == pair]
    if not pair_prices.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pair_prices["timestamp"], y=pair_prices["price"], mode="lines+markers", name=pair))
        fig.update_layout(title=f"{pair} - Preço ao longo do tempo", template="plotly_dark", xaxis_title="Timestamp", yaxis_title="Preço")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"Sem dados de preço para {pair}.")

st.caption("Powered by UltraBot + Grok (xAI)")
