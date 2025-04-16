import streamlit as st
import pandas as pd
import numpy as np
import json
import time
import os
import random
import ta
import plotly.express as px
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException
from learning_engine import LearningEngine
from utils import logger, gerar_resumo, calcular_confiabilidade_historica
from strategy_manager import load_strategies, save_strategies
import uuid
import toml
import logging
import shutil
from dashboard_utils import calculate_advanced_metrics
from strategy_manager import sync_strategies_and_status
from trade_manager import check_timeframe_direction_limit, check_active_trades, save_signal_log

st.set_page_config(page_title="UltraBot Dashboard 9.0", layout="wide")

SINALS_FILE = "sinais_detalhados.csv"
CONFIG_FILE = "config.json"
STRATEGIES_FILE = "strategies.json"
ROBOT_STATUS_FILE = "robot_status.json"
MISSED_OPPORTUNITIES_FILE = "oportunidades_perdidas.csv"

# Após as funções globais existentes (como generate_orders, check_alerts, etc.)

# Função para contar indicadores frequentes
def get_frequent_indicators(indicators_series):
    all_indicators = []
    for indicators in indicators_series:
        if isinstance(indicators, str):
            all_indicators.extend(indicators.split(';'))
    if not all_indicators:
        return "N/A"
    from collections import Counter
    most_common = Counter(all_indicators).most_common(4)  # Top 4 indicadores
    return ", ".join([indicator for indicator, count in most_common])

# Verificar se as credenciais estão presentes no st.secrets
if "binance" not in st.secrets or "api_key" not in st.secrets["binance"] or "api_secret" not in st.secrets["binance"]:
    try:
        secrets = toml.load("secrets.toml")
        st.secrets["binance"] = secrets.get("binance", {})
    except Exception as e:
        raise KeyError("As credenciais da API Binance não foram encontradas.") from e

api_key = st.secrets["binance"]["api_key"]
api_secret = st.secrets["binance"]["api_secret"]

if not api_key or not api_secret:
    raise ValueError("As credenciais da API da Binance não foram configuradas.")

logging.basicConfig(level=logging.DEBUG)

try:
    logging.info("Testando conectividade com a API Binance...")
    client = Client(api_key=api_key, api_secret=api_secret)
    client.ping()
    logging.info("Conexão com a API Binance bem-sucedida!")
except BinanceAPIException as e:
    logging.error(f"Erro na API Binance: Código {e.status_code}, Mensagem: {e.message}")
    raise
except Exception as e:
    logging.error(f"Erro inesperado: {e}")
    raise

learning_engine = LearningEngine()

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
.loader {
    width: 24px;
    height: 24px;
    border: 3px solid #007bff;
    border-top: 3px solid transparent;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
}

@keyframes spin {
    0% { transform: translate(-50%, -50%) rotate(0deg); }
    100% { transform: translate(-50%, -50%) rotate(360deg); }
}

.robot-tag.updating {
    opacity: 0.7;
    position: relative;
    border: 2px solid #00d4ff;
    animation: pulse 1s infinite ease-in-out;
}

@keyframes pulse {
    0% { box-shadow: 0 0 8px rgba(0, 212, 255, 0.3); }
    50% { box-shadow: 0 0 12px rgba(0, 212, 255, 0.6); }
    100% { box-shadow: 0 0 8px rgba(0, 212, 255, 0.3); }
}

.toggle-button {
    background-color: #28a745; /* Verde para "Ligar" */
    color: white;
    border: none;
    border-radius: 3px;
    padding: 3px 6px;
    cursor: pointer;
    font-family: 'Orbitron', sans-serif;
    font-size: 10px;
    transition: background-color 0.3s ease, transform 0.3s ease;
}

.toggle-button.toggle-button-off {
    background-color: #dc3545; /* Vermelho para "Desligar" */
}

.toggle-button:hover {
    background-color: #218838; /* Verde escuro para "Ligar" */
}

.toggle-button.toggle-button-off:hover {
    background-color: #c82333; /* Vermelho escuro para "Desligar" */
}

.toggle-button:active {
    transform: scale(0.95);
}

.edit-button {
    background-color: #e0f7fa;
    color: #1e3c72;
    border: 1px solid #1e3c72;
    border-radius: 3px;
    padding: 3px 6px;
    cursor: pointer;
    font-family: 'Orbitron', sans-serif;
    font-size: 10px;
    transition: background-color 0.3s ease;
    margin-left: 5px;
}

.edit-button:hover {
    background-color: #b3e5fc;
}

.toast-notification {
    position: fixed;
    top: 20px;
    right: 20px;
    background-color: #007bff;
    color: white;
    padding: 10px 20px;
    border-radius: 5px;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    z-index: 1000;
    animation: fade-in 0.5s ease-in-out;
    font-family: 'Roboto', sans-serif;
}

@keyframes fade-in {
    0% { opacity: 0; transform: translateY(-20px); }
    100% { opacity: 1; transform: translateY(0); }
}

@keyframes fade-out {
    0% { opacity: 1; transform: translateY(0); }
    100% { opacity: 0; transform: translateY(-20px); }
}

.fade-out {
    animation: fade-out 0.5s ease-in-out forwards;
}
    body {
        background-color: #f0f2f6;
        color: #333333;
        font-family: 'Roboto', sans-serif;
        margin: 0;
        padding: 20px;
    }

    h1, h2, h3 {
        color: #333333;
        font-weight: 500;
        margin-bottom: 15px;
    }

    h1 { font-size: 28px; }
    h2 { font-size: 22px; }
    h3 { font-size: 18px; }

    .stButton>button {
        background-color: #007bff;
        color: white;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 14px;
        border: none;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        transition: background-color 0.3s ease, transform 0.2s ease;
    }

    .stButton>button:hover {
        background-color: #0056b3;
        transform: translateY(-1px);
    }

    .stButton>button:active {
        transform: translateY(0);
    }

    .stNumberInput input, .stSelectbox div, .stTextInput input {
        background-color: #ffffff;
        color: #333333;
        border: 1px solid #cccccc;
        border-radius: 6px;
        padding: 8px;
    }

    .table-container {
        width: 100%;
        overflow-x: auto;
        max-height: 500px;
        overflow-y: auto;
        margin-bottom: 20px;
        position: relative;
        border-radius: 8px;
    }

    .status-table {
        border-collapse: collapse;
        width: 100%;
        background-color: #f5f5f5;
        border-radius: 8px;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.1);
        table-layout: auto;
    }

    .status-table th {
        background-color: #007bff;
        color: white;
        padding: 12px;
        text-align: left;
        font-weight: 500;
        position: sticky;
        top: 0;
        z-index: 1;
        white-space: nowrap;
    }

    .status-table td {
        padding: 12px;
        color: #333333;
        border-bottom: 1px solid #dddddd;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 200px;
    }

    .status-table tr:nth-child(even) {
        background-color: #e9ecef;
    }

    .status-table tr:hover {
        background-color: #dee2e6;
        transition: background-color 0.2s ease;
    }

    .status-table td[title]:hover::after {
        content: attr(title);
        position: absolute;
        left: 0;
        top: 100%;
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 5px;
        border-radius: 4px;
        font-size: 12px;
        z-index: 1000;
        white-space: normal;
        max-width: 300px;
        display: block;
    }

    .metric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.1);
        margin: 10px 0;
        text-align: center;
    }

    .metric-label {
        font-size: 14px;
        color: #666666;
        margin-bottom: 5px;
    }

    .metric-value {
        font-size: 26px;
        font-weight: bold;
        color: #333333;
    }

    .alert {
        padding: 12px;
        border-radius: 6px;
        margin: 10px 0;
        font-size: 16px;
    }

    .alert-success {
        background-color: #28a745;
        color: white;
    }

    .alert-warning {
        background-color: #ffc107;
        color: #333333;
    }

    .alert-danger {
        background-color: #dc3545;
        color: white;
    }

    .main {
        max-width: 1200px;
        margin: 0 auto;
    }

    .strategy-header {
        background-color: #007bff;
        color: white;
        padding: 10px;
        border-radius: 5px 5px 0 0;
        font-weight: bold;
        text-align: center;
    }

    .strategy-section {
        background-color: #f9f9f9;
        padding: 15px;
        border: 1px solid #ddd;
        border-radius: 0 0 5px 5px;
        font-size: 14px;
    }

    .strategy-section p {
        margin: 5px 0;
    }

    .robot-tag {
        background: #1e3c72;
        border: 1px solid #00d4ff;
        border-radius: 8px;
        padding: 8px;
        margin: 5px;
        display: inline-block;
        box-shadow: 0 0 8px rgba(0, 212, 255, 0.3);
        font-family: 'Orbitron', sans-serif;
        color: #e0f7fa;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        width: 300px;
    }

    .robot-tag:hover {
        transform: scale(1.03);
        box-shadow: 0 0 12px rgba(0, 212, 255, 0.5);
    }

    .robot-tag h4 {
        margin: 0 0 5px 0;
        font-size: 14px;
        color: #00d4ff;
        text-shadow: 0 0 3px rgba(0, 212, 255, 0.5);
    }

    .robot-tag p {
        margin: 2px 0;
        font-size: 10px;
        line-height: 1.2;
    }

    .robot-tag .button-container {
    display: flex;
    justify-content: flex-start;
    align-items: center;
    margin-top: 5px;
}

.robot-tag .toggle-container {
    position: relative;
    width: 40px;
    height: 20px;
    background-color: #ccc; /* Cor de fundo quando desligado */
    border-radius: 20px;
    cursor: pointer;
    transition: background-color 0.3s ease;
}

.robot-tag .toggle-container.active {
    background-color: #28a745; /* Verde quando ligado */
}

.robot-tag .toggle-circle {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background-color: white;
    border-radius: 50%;
    transition: transform 0.3s ease;
}

.robot-tag .toggle-container.active .toggle-circle {
    transform: translateX(20px); /* Move o círculo para a direita quando ligado */
}

.robot-tag .toggle-container:hover {
    opacity: 0.9;
}

    .robot-tag .edit-button {
        background-color: #ffffff;
        color: #1e3c72;
        border: 1px solid #1e3c72;
        border-radius: 3px;
        padding: 3px 6px;
        cursor: pointer;
        font-family: 'Orbitron', sans-serif;
        font-size: 10px;
        transition: background-color 0.3s ease;
        margin-left: 5px;
    }

    .robot-tag .edit-button:hover {
        background-color: #e0e0e0;
    }

    .robots {
        display: inline-block;
        vertical-align: middle;
        margin-left: 10px;
    }

    .head,
    .left_arm,
    .torso,
    .right_arm,
    .left_leg,
    .right_leg {
        background-color: white;
    }

    .head {
        max-width: 100px;
        height: 75px;
        border-radius: 100px 100px 0 0;
        margin-bottom: 5px;
        border: 3px solid #1f3969;
    }

    .eyes {
        position: relative;
        top: 27px;
        height: 50px;
        display: flex;
        justify-content: space-around;
        align-items: center;
        cursor: pointer;
    }

    .left_eye {
        position: relative;
        left: 10px;
        width: 17px;
        height: 17px;
        border-radius: 15px;
        border: 4px solid #1f3969;
        background: #5092e6;
        transition: 300ms ease-in-out;
    }

    .right_eye {
        position: relative;
        top: 5px;
        right: 5px;
        width: 12px;
        height: 12px;
        border-radius: 15px;
        background: #0a41a7;
        transition: 200ms ease-in-out 0.5s;
    }

    .glow {
        float: right;
        height: 17px;
        width: 17px;
        opacity: 1;
        border-radius: 15px;
        border-right-color: #cee3ff;
        border-right-style: solid;
        transition: 300ms ease-in-out 0.3s;
    }

    .upper_body {
        display: flex;
        justify-content: center;
    }

    .left_arm,
    .right_arm {
        min-width: 20px;
        height: 62px;
        border-radius: 50px;
        border: 3px solid #1f3969;
        z-index: -1;
        transition: 200ms ease-in-out;
    }

    .left_arm {
        margin-right: 5px;
    }

    .right_arm {
        margin-left: 5px;
    }

    .torso {
        min-width: 100px;
        height: 100px;
        border: 3px solid #1f3969;
        border-radius: 0 0 25px 25px;
        cursor: pointer;
    }

    .lower_body {
        display: flex;
        align-items: flex-start;
        justify-content: center;
    }

    .left_leg,
    .right_leg {
        width: 20px;
        height: 50px;
        margin-top: -5px;
        border-radius: 0 0 50px 50px;
        border: 3px solid #1f3969;
        border-top-color: white;
        z-index: -1;
        transition: 200ms ease-in-out;
    }

    .left_leg {
        margin-right: 15px;
    }

    .eyes:hover .left_eye {
        transform: translateX(10px) translateY(-7px) scale(1.1);
    }

    .eyes:hover .glow {
        transform: rotate(360deg);
    }

    .eyes:hover .right_eye {
        transform: translateY(-7px);
        background: red;
    }

    .upper_body:active .right_arm {
        transform: translateX(-50px);
    }

    .upper_body:active .left_arm {
        transform: translateX(50px);
    }

    .robots:active .left_leg {
        transform: translateY(-75px);
    }

    .robots:active .right_leg {
        transform: translateY(-75px);
    }

    .robot-container {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        margin-bottom: 20px;
        gap: 10px;
    }

    .notification {
        border-left: 4px solid #007bff;
        padding: 12px 15px;
        background-color: #f8f9fa;
        margin-bottom: 10px;
        border-radius: 4px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        transition: background-color 0.3s;
    }

    .notification:hover {
        background-color: #e9ecef;
    }

    .notification-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 5px;
    }

    .notification-source {
        font-weight: 500;
        font-size: 15px;
    }

    .notification-timestamp {
        color: #6c757d;
        font-size: 12px;
    }

    .notification-message {
        font-size: 14px;
        margin-bottom: 3px;
    }

    .notification-details {
        font-size: 12px;
        color: #6c757d;
    }

    .notification-count {
        background-color: #6c757d;
        color: white;
        border-radius: 10px;
        padding: 1px 6px;
        font-size: 11px;
        margin-left: 5px;
    }

    .notification-error {
        border-left-color: #dc3545;
    }

    .notification-warning {
        border-left-color: #ffc107;
    }

    .notification-info {
        border-left-color: #0dcaf0;
    }

    .notification-success {
        border-left-color: #28a745;
    }

    .mark-read-button {
        font-size: 12px;
        padding: 2px 5px;
        background-color: #f8f9fa;
        color: #6c757d;
        border: 1px solid #dee2e6;
        border-radius: 3px;
    }

    .mark-read-button:hover {
        background-color: #e9ecef;
    }

    .robot-card {
        background-color: #ffffff;
        border-radius: 20px;
        padding: 20px;
        margin: 10px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        width: 300px;
        position: relative;
        font-family: Arial, sans-serif;
    }

    .profile-pic {
        width: 60px;
        height: 60px;
        background-color: #e0e0e0;
        border-radius: 50%;
        position: absolute;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
    }

    .more-options {
        position: absolute;
        top: 20px;
        right: 20px;
        font-size: 20px;
        color: #888;
    }

    .robot-card h3 {
        margin-top: 80px;
        text-align: center;
        font-size: 1.5em;
        color: #333;
        font-weight: bold;
    }

    .stats {
        display: flex;
        justify-content: space-around;
        margin: 10px 0;
    }

    .stats div {
        text-align: center;
    }

    .stats span {
        display: block;
        font-size: 1.2em;
        font-weight: bold;
        color: #333;
    }

    .stats div {
        font-size: 0.9em;
        color: #666;
    }

    .follow-btn {
        display: block;
        width: 100%;
        padding: 10px;
        background-color: #f7c948;
        border: none;
        border-radius: 20px;
        color: #333;
        font-size: 1em;
        font-weight: bold;
        cursor: pointer;
        margin: 10px 0;
        text-align: center;
    }

    .follow-btn:hover {
        background-color: #f0b428;
    }

    .robot-card p {
        margin: 5px 0;
        font-size: 0.9em;
        color: #666;
        text-align: left;
    }

    .robot-card p strong {
        color: #333;
    }
    </style>
""", unsafe_allow_html=True)

# Adicione este CSS para padronizar todos os botões do dashboard
st.markdown("""
<style>
/* Botões padrão do dashboard (azul, texto branco) */
.stButton > button,
.binance-yellow,
.binance-gray,
.binance-refresh,
.binance-closeall {
    background-color: #007bff !important;
    color: #fff !important;
    border-radius: 8px !important;
    padding: 8px 16px !important;
    font-size: 14px !important;
    border: none !important;
    font-family: 'Orbitron', sans-serif !important;
    font-weight: 500 !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.12) !important;
    transition: background-color 0.3s, transform 0.2s !important;
}
.stButton > button:hover,
.binance-yellow:hover,
.binance-gray:hover,
.binance-refresh:hover,
.binance-closeall:hover {
    background-color: #0056b3 !important;
    color: #fff !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active,
.binance-yellow:active,
.binance-gray:active,
.binance-refresh:active,
.binance-closeall:active {
    transform: translateY(0) !important;
}

/* Força fundo azul e texto branco para todos os botões input, select, etc */
button, input[type=button], input[type=submit], input[type=reset], select {
    background-color: #007bff !important;
    color: #fff !important;
    border-radius: 8px !important;
    border: none !important;
    font-family: 'Orbitron', sans-serif !important;
    font-weight: 500 !important;
}
button:hover, input[type=button]:hover, input[type=submit]:hover, input[type=reset]:hover, select:hover {
    background-color: #0056b3 !important;
    color: #fff !important;
}
</style>
""", unsafe_allow_html=True)

# Sincronizar estratégias e status dos robôs antes de carregar
sync_strategies_and_status()

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "tp_percent": 2.0,
        "sl_percent": 1.0,
        "leverage": 22,
        "max_trades_simultaneos": 50,
        "score_tecnico_min": 0.3,
        "ml_confidence_min": 0.5,
        "indicadores_ativos": {
            "EMA": True, "MACD": True, "RSI": True,
            "Swing Trade Composite": True
        },
        "confianca_minima": {
            "Sentimento": 0.5,
            "Swing Trade Composite": 0.5
        },
        "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]
    }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def load_robot_status():
    if os.path.exists(ROBOT_STATUS_FILE):
        with open(ROBOT_STATUS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_robot_status(status):
    with open(ROBOT_STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=4)

@st.cache_data(ttl=5)
def get_mark_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        logger.error(f"Erro ao obter Mark Price para {symbol}: {e}")
        return None

def calculate_liq_price(entry_price, leverage, direction):
    if direction == "LONG":
        return entry_price * (1 - 1/leverage)
    else:
        return entry_price * (1 + 1/leverage)

def calculate_distances(entry_price, mark_price, tp_percent, sl_percent, direction):
    if direction == "LONG":
        tp_price = entry_price * (1 + tp_percent / 100)
        sl_price = entry_price * (1 - sl_percent / 100)
        distance_to_tp = (tp_price - mark_price) / mark_price * 100 if mark_price > 0 else float('inf')
        distance_to_sl = (mark_price - sl_price) / mark_price * 100 if mark_price > 0 else float('inf')
    else:
        tp_price = entry_price * (1 - tp_percent / 100)
        sl_price = entry_price * (1 + sl_percent / 100)
        distance_to_tp = (mark_price - tp_price) / mark_price * 100 if mark_price > 0 else float('inf')
        distance_to_sl = (sl_price - mark_price) / mark_price * 100 if mark_price > 0 else float('inf')
    return distance_to_tp, distance_to_sl

def close_order_manually(signal_id, mark_price):
    df = pd.read_csv(SINALS_FILE)
    order_idx = df.index[df['signal_id'] == signal_id].tolist()
    if not order_idx:
        st.error(f"Ordem {signal_id} não encontrada.")
        return
    order_idx = order_idx[0]
    order = df.iloc[order_idx]
    direction = order['direcao']
    entry_price = float(order['preco_entrada'])
    position_size = float(order['quantity']) * entry_price

    if direction == "LONG":
        profit_percent = (mark_price - entry_price) / entry_price * 100
    else:
        profit_percent = (entry_price - mark_price) / entry_price * 100

    df.at[order_idx, 'preco_saida'] = mark_price
    df.at[order_idx, 'lucro_percentual'] = profit_percent
    df.at[order_idx, 'pnl_realizado'] = profit_percent
    df.at[order_idx, 'resultado'] = "Manual"
    df.at[order_idx, 'timestamp_saida'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.at[order_idx, 'estado'] = "fechado"
    df.to_csv(SINALS_FILE, index=False)
    st.success(f"Ordem {signal_id} fechada manualmente com PNL de {profit_percent:.2f}%.")

def close_order(signal_id, mark_price, reason):
    df = pd.read_csv(SINALS_FILE)
    order_idx = df.index[df['signal_id'] == signal_id].tolist()
    if not order_idx:
        logger.error(f"Ordem {signal_id} não encontrada ao tentar fechar.")
        return
    order_idx = order_idx[0]
    order = df.iloc[order_idx]
    direction = order['direcao']
    entry_price = float(order['preco_entrada'])
    position_size = float(order['quantity']) * entry_price

    if direction == "LONG":
        profit_percent = (mark_price - entry_price) / entry_price * 100
    else:
        profit_percent = (entry_price - mark_price) / entry_price * 100

    df.at[order_idx, 'preco_saida'] = mark_price
    df.at[order_idx, 'lucro_percentual'] = profit_percent
    df.at[order_idx, 'pnl_realizado'] = profit_percent
    df.at[order_idx, 'resultado'] = reason
    df.at[order_idx, 'timestamp_saida'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.at[order_idx, 'estado'] = "fechado"
    df.to_csv(SINALS_FILE, index=False)
    logger.info(f"Ordem {signal_id} fechada automaticamente com motivo {reason} e PNL de {profit_percent:.2f}%.")

def download_historical_data(symbol, interval='1d', lookback='30 days'):
    try:
        klines = client.get_historical_klines(symbol, interval, lookback)
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df['close'] = df['close'].astype(float)
        df.to_csv(f"historical_data_{symbol}_{interval}.csv", index=False)
        logger.info(f"Dados históricos para {symbol} (intervalo {interval}) baixados com sucesso.")
        return df
    except Exception as e:
        logger.error(f"Erro ao baixar dados históricos para {symbol}: {e}")
        return None

def calculate_indicators(df, active_indicators):
    indicators = {}
    if "EMA" in active_indicators:
        df['EMA12'] = ta.trend.EMAIndicator(df['close'], window=12).ema_indicator()
        df['EMA50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        indicators["EMA12>EMA50"] = df['EMA12'].iloc[-1] > df['EMA50'].iloc[-1] if not df['EMA12'].isna().all() and not df['EMA50'].isna().all() else False
    if "RSI" in active_indicators:
        df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        indicators["RSI Sobrevendido"] = df['RSI'].iloc[-1] < 30 if not df['RSI'].isna().all() else False
    if "MACD" in active_indicators:
        macd = ta.trend.MACD(df['close'])
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        if len(df) >= 2:
            last_macd = df['MACD'].iloc[-1]
            last_signal = df['MACD_Signal'].iloc[-1]
            prev_macd = df['MACD'].iloc[-2]
            prev_signal = df['MACD_Signal'].iloc[-2]
            indicators["MACD Cruzamento Alta"] = (last_macd > last_signal) and (prev_macd <= prev_signal)
        else:
            indicators["MACD Cruzamento Alta"] = False
    if "Swing Trade Composite" in active_indicators:
        indicators["Swing_Trade_Composite_LONG"] = df['close'].iloc[-1] > df['close'].rolling(window=20).mean().iloc[-1]
        indicators["Swing_Trade_Composite_SHORT"] = df['close'].iloc[-1] < df['close'].rolling(window=20).mean().iloc[-1]
    return indicators

def generate_orders(robot_name, strategy_config):
    if not isinstance(robot_name, str) or not robot_name:
        logger.error(f"Nome de robô inválido: {robot_name}")
        return None

    if os.path.exists(SINALS_FILE):
        df = pd.read_csv(SINALS_FILE)
    else:
        df = pd.DataFrame(columns=[
            'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
            'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
            'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
            'motivos', 'timeframe', 'aceito', 'parametros', 'quality_score'
        ])

    params = {
        "tp_percent": strategy_config['tp_percent'],
        "sl_percent": strategy_config['sl_percent'],
        "leverage": strategy_config['leverage']
    }
    active_indicators = [ind for ind, active in strategy_config["indicadores_ativos"].items() if active]
    contributing_indicators = ";".join(active_indicators)

    available_pairs = ["XRPUSDT", "DOGEUSDT", "TRXUSDT"]
    selected_pair = random.choice(available_pairs)

    timeframes = strategy_config.get('timeframes', ["1d"])
    tf_weights = {
        "1m": 1.0,
        "5m": 1.0,
        "15m": 1.0,
        "1h": 1.2,
        "4h": 1.2,
        "1d": 1.3
    }
    timeframes = sorted(timeframes, key=lambda tf: tf_weights.get(tf, 1.0), reverse=True)

    for timeframe in timeframes:
        active_trades = check_active_trades()
        # Limite de 36 ordens abertas por robô
        robot_open_orders = [t for t in active_trades if t['strategy_name'] == robot_name and t['estado'] == 'aberto']
        if len(robot_open_orders) >= 36:
            logger.warning(f"Limite de 36 ordens abertas por robô atingido para {robot_name}. Ordem não será criada.")
            save_signal_log({
                'strategy_name': robot_name,
                'par': selected_pair,
                'timeframe': timeframe,
                'direcao': 'LONG',
                'contributing_indicators': contributing_indicators
            }, accepted=False, mode='DASHBOARD')
            continue
        direction = None
        historical_data = download_historical_data(selected_pair, interval=timeframe, lookback='30 days')
        if historical_data is None or len(historical_data) < 50:
            logger.warning(f"Dados insuficientes para {selected_pair} no timeframe {timeframe}.")
            continue
        indicators = calculate_indicators(historical_data, active_indicators)
        should_generate_order = any([
            indicators.get("EMA12>EMA50", False),
            indicators.get("RSI Sobrevendido", False),
            indicators.get("MACD Cruzamento Alta", False),
            indicators.get("Swing_Trade_Composite_LONG", False),
            indicators.get("Swing_Trade_Composite_SHORT", False)
        ])
        if not should_generate_order:
            logger.info(f"Nenhuma condição atendida para {robot_name} no par {selected_pair}.")
            continue
        direction = "LONG" if indicators.get("EMA12>EMA50", False) or indicators.get("MACD Cruzamento Alta", False) or indicators.get("Swing_Trade_Composite_LONG", False) else "SHORT"
        # Só pode haver 1 ordem aberta por robô/par/timeframe/direção
        already_open = [t for t in robot_open_orders if t['par'] == selected_pair and t['timeframe'] == timeframe and t['direcao'] == direction]
        if already_open:
            logger.warning(f"Já existe ordem aberta para {robot_name} em {selected_pair}/{timeframe}/{direction}. Ordem não será criada.")
            save_signal_log({
                'strategy_name': robot_name,
                'par': selected_pair,
                'timeframe': timeframe,
                'direcao': direction,
                'contributing_indicators': contributing_indicators
            }, accepted=False, mode='DASHBOARD')
            continue
        entry_price = historical_data['close'].iloc[-1]
        quantity_in_usdt = strategy_config.get('quantity_in_usdt', 10.0)
        quantity = quantity_in_usdt / entry_price if entry_price > 0 else 1.0
        new_order = {
            'signal_id': str(uuid.uuid4()),
            'par': selected_pair,
            'direcao': direction,
            'preco_entrada': entry_price,
            'preco_saida': np.nan,
            'quantity': quantity,
            'lucro_percentual': np.nan,
            'pnl_realizado': np.nan,
            'resultado': np.nan,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'timestamp_saida': np.nan,
            'estado': "aberto",
            'strategy_name': robot_name,
            'contributing_indicators': contributing_indicators,
            'localizadores': json.dumps({}),
            'motivos': "Ordem gerada com base em indicadores reais",
            'timeframe': timeframe,
            'aceito': True,
            'parametros': json.dumps(params),
            'quality_score': 0.5
        }
        df = pd.concat([df, pd.DataFrame([new_order])], ignore_index=True)
        df.to_csv(SINALS_FILE, index=False)
        logger.info(f"Ordem simulada gerada para {robot_name} no par {selected_pair}.")
        return new_order
    logger.warning(f"Nenhum timeframe gerou ordens para {robot_name} no par {selected_pair}.")
    return None

def check_alerts(df_open):
    alerts = []
    for _, row in df_open.iterrows():
        symbol = row['par']
        historical_file = f"historical_data_{symbol}_{row['timeframe']}.csv"
        if not os.path.exists(historical_file):
            download_historical_data(symbol, interval=row['timeframe'])
            continue

        mark_price = get_mark_price(symbol)
        if mark_price is None:
            continue

        entry_price = float(row['preco_entrada'])
        params = json.loads(row['parametros'])
        tp_percent = params.get('tp_percent', 2.0)
        sl_percent = params.get('sl_percent', 1.0)
        direction = row['direcao']
        robot_name = row['strategy_name']
        distance_to_tp, distance_to_sl = calculate_distances(entry_price, mark_price, tp_percent, sl_percent, direction)

        if distance_to_tp <= 0:
            close_order(row['signal_id'], mark_price, "TP")
            alerts.append(f"✅ Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) fechada: TP! ({row['timeframe']})")
        elif distance_to_sl <= 0:
            close_order(row['signal_id'], mark_price, "SL")
            alerts.append(f"❌ Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) fechada: SL! ({row['timeframe']})")
        else:
            if distance_to_tp > 0 and distance_to_tp <= 0.5:
                alerts.append(f"🚨 Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) a {distance_to_tp:.2f}% do TP! ({row['timeframe']})")
            if distance_to_sl > 0 and distance_to_sl <= 0.5:
                alerts.append(f"⚠️ Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) a {distance_to_sl:.2f}% do SL! ({row['timeframe']})")

    log_file = "bot.log"
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = f.readlines()
        recent_logs = [log for log in logs if "ERROR" in log and datetime.strptime(log[:19], "%Y-%m-%d %H:%M:%S") > datetime.now() - timedelta(minutes=5)]
        for log in recent_logs:
            if "Erro ao verificar histórico de preços" in log:
                alerts.append(f"⚠️ Sistema: Erro detectado: {log.strip()}")

    # --- CORREÇÃO: só tenta ler o arquivo se ele existir ---
    if not os.path.exists(SINALS_FILE):
        return alerts

    df = pd.read_csv(SINALS_FILE)
    df_closed = df[df['estado'] == 'fechado']
    if len(df_closed[df_closed['resultado'].isin(['TP', 'SL'])]) < 5:
        alerts.append("⚠️ Sistema: Modelo ML não treinado: menos de 5 ordens com TP/SL.")

    return alerts

def reset_bot_data(reset_password):
    correct_password = "ultra2025"
    reset_password = reset_password.strip()

    if reset_password != correct_password:
        return False, "Senha incorreta."

    try:
        backup_dir = "backup"
        os.makedirs(backup_dir, exist_ok=True)

        if os.path.exists(SINALS_FILE):
            shutil.copy(SINALS_FILE, os.path.join(backup_dir, os.path.basename(SINALS_FILE)))
            os.remove(SINALS_FILE)

        if os.path.exists(MISSED_OPPORTUNITIES_FILE):
            shutil.copy(MISSED_OPPORTUNITIES_FILE, os.path.join(backup_dir, os.path.basename(MISSED_OPPORTUNITIES_FILE)))
            os.remove(MISSED_OPPORTUNITIES_FILE)

        robot_status = load_robot_status()
        for strategy_name in robot_status.keys():
            robot_status[strategy_name] = False
        save_robot_status(robot_status)

        from notification_manager import clear_all_notifications
        clear_all_notifications()

        try:
            learning_engine.train()
        except Exception as e:
            logger.error(f"Erro ao treinar modelo após reset: {e}")

        return True, "Bot resetado com sucesso!"
    except Exception as e:
        logger.error(f"Erro ao resetar bot: {e}")
        return False, f"Erro ao resetar bot: {e}"

def get_tp_sl(row, key, default=0.0):
    try:
        params = json.loads(row['parametros'])
        return params.get(key, default)
    except (json.JSONDecodeError, KeyError, TypeError):
        return default

def validate_robot_status_and_stats():
    robot_status = load_robot_status()
    if os.path.exists(SINALS_FILE):
        df = pd.read_csv(SINALS_FILE)
        # Verificação de existência da coluna antes de acessar
        if 'strategy_name' not in df.columns or df.empty:
            logger.warning("Arquivo sinais_detalhados.csv está vazio ou sem a coluna 'strategy_name'.")
            return
        # Tratar valores inválidos na coluna strategy_name
        df = df.dropna(subset=['strategy_name'])  # Remover linhas com NaN
        df = df[df['strategy_name'].apply(lambda x: isinstance(x, str))]  # Manter apenas strings
        logger.info(f"Valores únicos em strategy_name após limpeza: {df['strategy_name'].unique()}")
    else:
        df = pd.DataFrame(columns=[
            'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
            'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
            'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
            'motivos', 'timeframe', 'aceito', 'parametros', 'quality_score'
        ])
    
    indicadores_compostos = ["swing_trade_composite"]
    
    from notification_manager import check_system_health
    inconsistency_count = check_system_health(df, robot_status, indicadores_compostos)
    
    all_strategies = set(robot_status.keys())
    active_strategies_in_data = set(df['strategy_name'].unique()) if 'strategy_name' in df.columns else set()
    unlisted_strategies = active_strategies_in_data - all_strategies

    for strategy_name in unlisted_strategies:
        if isinstance(strategy_name, str) and strategy_name.lower() in [ind.lower() for ind in indicadores_compostos]:
            continue
        robot_status[strategy_name] = False

    save_robot_status(robot_status)
    return inconsistency_count

# Chamar validação inicial
validate_robot_status_and_stats()

if os.path.exists(SINALS_FILE):
    df = pd.read_csv(SINALS_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
else:
    df = pd.DataFrame(columns=[
        'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
        'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
        'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
        'motivos', 'timeframe', 'aceito', 'parametros', 'quality_score'
    ])
    df.to_csv(SINALS_FILE, index=False)

if os.path.exists(MISSED_OPPORTUNITIES_FILE):
    df_missed = pd.read_csv(MISSED_OPPORTUNITIES_FILE)
    # Corrige: converte apenas valores que parecem datas, outros viram NaT
    df_missed['timestamp'] = pd.to_datetime(df_missed['timestamp'], errors="coerce")
else:
    df_missed = pd.DataFrame(columns=[
        'timestamp', 'robot_name', 'par', 'timeframe', 'direcao', 'score_tecnico',
        'contributing_indicators', 'reason'
    ])
    df_missed.to_csv(MISSED_OPPORTUNITIES_FILE, index=False)

df_open = df[df['estado'] == 'aberto']
df_closed = df[df['estado'] == 'fechado']

if 'known_open_orders' not in st.session_state:
    st.session_state['known_open_orders'] = set()

current_open_orders = set(df_open['signal_id'].tolist())
new_orders = current_open_orders - st.session_state['known_open_orders']
st.session_state['known_open_orders'] = current_open_orders

strategies = load_strategies()
robot_status = load_robot_status()

col_title, col_robot, col_notifications = st.columns([3, 1, 3])
with col_title:
    st.title("UltraBot Dashboard")
with col_robot:
    st.markdown("""
    <div class="robots">
        <div class="head">
            <div class="eyes">
                <div class="left_eye">
                    <div class="glow"></div>
                </div>
                <div class="right_eye"></div>
            </div>
        </div>
        <div class="upper_body">
            <div class="left_arm"></div>
            <div class="torso"></div>
            <div class="right_arm"></div>
        </div>
        <div class="lower_body">
            <div class="left_leg"></div>
            <div class="right_leg"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
with col_notifications:
    def render_notifications_panel():
        st.info("Notifications panel is not implemented yet.")
    render_notifications_panel()

# Adiciona a nova aba "Meus Robôs 🤖" e "ML Machine" ao lado de "Ordens Binance"
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Visão Geral", "Ordens", "Configurações de Estratégia", "Oportunidades Perdidas", "Ordens Binance", "Meus Robôs 🤖", "ML Machine"
])

with tab1:
    st.header("Status dos Robôs")
    active_strategies = st.session_state.get('active_strategies', load_robot_status())
    status_data = []
    df_closed = df[df['estado'] == 'fechado']

    for strategy_name in strategies.keys():
        if strategy_name not in st.session_state:
            st.session_state[strategy_name] = {'activation_time': None, 'last_activity': None}
        if active_strategies.get(strategy_name, False) and st.session_state[strategy_name]['activation_time'] is None:
            st.session_state[strategy_name]['activation_time'] = datetime.now()
        if not active_strategies.get(strategy_name, False):
            st.session_state[strategy_name]['activation_time'] = None

        time_online = "Desativado"
        if active_strategies.get(strategy_name, False) and st.session_state[strategy_name]['activation_time']:
            time_diff = datetime.now() - st.session_state[strategy_name]['activation_time']
            hours, remainder = divmod(time_diff.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            time_online = f"{int(hours)}h {int(minutes)}m"

        robot_orders = df[df['strategy_name'] == strategy_name]
        last_activity = "Nenhuma atividade"
        if not robot_orders.empty:
            last_order = robot_orders.sort_values('timestamp', ascending=False).iloc[0]
            last_activity = last_order['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            st.session_state[strategy_name]['last_activity'] = last_activity

        robot_closed = df_closed[df_closed['strategy_name'] == strategy_name]
        total_orders = len(robot_closed)
        wins = len(robot_closed[robot_closed['pnl_realizado'] >= 0])
        win_rate = (wins / total_orders * 100) if total_orders > 0 else 0
        total_pnl = robot_closed['pnl_realizado'].sum() if total_orders > 0 else 0

        robot_signals = df[df['strategy_name'] == strategy_name]
        signals_generated = len(robot_signals)
        signals_accepted = len(robot_signals[robot_signals['aceito'] == True])
        signals_rejected = len(robot_signals[robot_signals['aceito'] == False])
        avg_quality_score = robot_signals['quality_score'].mean() if 'quality_score' in robot_signals.columns and not robot_signals['quality_score'].isna().all() else 0.0
        open_orders = len(df_open[df_open['strategy_name'] == strategy_name])

        alert = ""
        if total_pnl < -5:
            alert = "⚠️"
        elif total_pnl > 5:
            alert = "📈"

        status_data.append({
            "Robô": strategy_name,
            "Status": "Ativado" if active_strategies.get(strategy_name, False) else "Desativado",
            "Tempo Online": time_online,
            "Última Atividade": st.session_state[strategy_name]['last_activity'] or "Nenhuma atividade",
            "Sinais Gerados": signals_generated,
            "Sinais Aceitos": signals_accepted,
            "Sinais Rejeitados": signals_rejected,
            "Ordens Abertas": open_orders,
            "Score Médio de Qualidade": f"{avg_quality_score:.2f}",
            "PNL Total": f"{total_pnl:.2f}% {alert}",
            "Taxa de Vitória": f"{win_rate:.2f}%"
        })

    status_df = pd.DataFrame(status_data)
    sort_by = st.selectbox("Ordenar por", ["Robô", "Tempo Online", "Sinais Gerados", "Sinais Aceitos", "Sinais Rejeitados", "Ordens Abertas", "Score Médio de Qualidade", "PNL Total", "Taxa de Vitória"], key="sort_robots")
    if sort_by == "Robô":
        status_df = status_df.sort_values("Robô")
    elif sort_by == "Tempo Online":
        status_df['Tempo Online Sort'] = status_df['Tempo Online'].apply(lambda x: sum(int(part) * (60 if 'h' in part else 1) for part in x.split() if part.isdigit()) if x != "Desativado" else -1)
        status_df = status_df.sort_values("Tempo Online Sort", ascending=False).drop("Tempo Online Sort", axis=1)
    elif sort_by == "Sinais Gerados":
        status_df = status_df.sort_values("Sinais Gerados", ascending=False)
    elif sort_by == "Sinais Aceitos":
        status_df = status_df.sort_values("Sinais Aceitos", ascending=False)
    elif sort_by == "Sinais Rejeitados":
        status_df = status_df.sort_values("Sinais Rejeitados", ascending=False)
    elif sort_by == "Ordens Abertas":
        status_df = status_df.sort_values("Ordens Abertas", ascending=False)
    elif sort_by == "Score Médio de Qualidade":
        status_df['Score Sort'] = status_df['Score Médio de Qualidade'].astype(float)
        status_df = status_df.sort_values("Score Sort", ascending=False).drop("Score Sort", axis=1)
    elif sort_by == "PNL Total":
        status_df['PNL Sort'] = status_df['PNL Total'].str.extract(r'([-+]?\d*\.?\d+)%')[0].astype(float)
        status_df = status_df.sort_values("PNL Sort", ascending=False).drop("PNL Sort", axis=1)
    elif sort_by == "Taxa de Vitória":
        status_df['Win Rate Sort'] = status_df['Taxa de Vitória'].str.replace('%', '').astype(float)
        status_df = status_df.sort_values("Win Rate Sort", ascending=False).drop("Win Rate Sort", axis=1)

    st.markdown(status_df.to_html(index=False, classes="status-table"), unsafe_allow_html=True)

    st.subheader("Distribuição de Ordens por Resultado")
    if not df_closed.empty:
        result_counts = df_closed.groupby(['strategy_name', 'resultado']).size().unstack(fill_value=0)
        if not result_counts.empty:
            fig = px.bar(
                result_counts,
                barmode='stack',
                title="Distribuição de Ordens por Resultado",
                labels={'value': 'Número de Ordens', 'strategy_name': 'Robô', 'resultado': 'Resultado'},
                height=400
            )
            st.plotly_chart(fig)
        else:
            st.info("Nenhuma ordem fechada para exibir o gráfico.")
    else:
        st.info("Nenhuma ordem fechada para exibir o gráfico.")

    st.header("Estatísticas Gerais")
    if not df_open.empty:
        total_value = 0
        total_pnl = 0
        for _, row in df_open.iterrows():
            mark_price = get_mark_price(row['par'])
            if mark_price is None:
                continue
            entry_price = float(row['preco_entrada'])
            quantity = float(row['quantity'])
            direction = row['direcao']
            total_value += entry_price * quantity
            if direction == "LONG":
                pnl = (mark_price - entry_price) / entry_price * 100
            else:
                pnl = (entry_price - mark_price) / entry_price * 100
            total_pnl += pnl

        num_open = len(df_open)
        num_open_positive = len(df_open[df_open.apply(lambda row: (get_mark_price(row['par']) - float(row['preco_entrada'])) / float(row['preco_entrada']) * 100 >= 0 if row['direcao'] == 'LONG' else (float(row['preco_entrada']) - get_mark_price(row['par'])) / float(row['preco_entrada']) * 100 >= 0, axis=1)])
        num_open_negative = num_open - num_open_positive
        num_closed_positive = len(df_closed[df_closed['pnl_realizado'] >= 0])
        num_closed_negative = len(df_closed[df_closed['pnl_realizado'] < 0])
        win_rate = (num_closed_positive / len(df_closed) * 100) if len(df_closed) > 0 else 0
        avg_pnl = df_closed['pnl_realizado'].mean() if not df_closed.empty else 0

        col1, col2, col3 = st.columns(3)
        col1.markdown(f"<div class='metric'><div class='metric-label'>Valor Total em Ordens (USDT)</div><div class='metric-value'>{total_value:.2f}</div></div>", unsafe_allow_html=True)
        col2.markdown(f"<div class='metric'><div class='metric-label'>PNL Total (%)</div><div class='metric-value'>{total_pnl:.2f}</div></div>", unsafe_allow_html=True)
        col3.markdown(f"<div class='metric'><div class='metric-label'>Ordens Abertas</div><div class='metric-value'>{num_open}</div></div>", unsafe_allow_html=True)

        col4, col5, col6 = st.columns(3)
        col4.markdown(f"<div class='metric'><div class='metric-label'>Ordens Abertas (PNL Positivo)</div><div class='metric-value'>{num_open_positive}</div></div>", unsafe_allow_html=True)
        col5.markdown(f"<div class='metric'><div class='metric-label'>Ordens Abertas (PNL Negativo)</div><div class='metric-value'>{num_open_negative}</div></div>", unsafe_allow_html=True)
        col6.markdown(f"<div class='metric'><div class='metric-label'>Taxa de Vitória (%)</div><div class='metric-value'>{win_rate:.2f}</div></div>", unsafe_allow_html=True)

        col7, col8, col9 = st.columns(3)
        col7.markdown(f"<div class='metric'><div class='metric-label'>Ordens Fechadas (PNL Positivo)</div><div class='metric-value'>{num_closed_positive}</div></div>", unsafe_allow_html=True)
        col8.markdown(f"<div class='metric'><div class='metric-label'>Ordens Fechadas (PNL Negativo)</div><div class='metric-value'>{num_closed_negative}</div></div>", unsafe_allow_html=True)
        col9.markdown(f"<div class='metric'><div class='metric-label'>PNL Médio por Ordem (%)</div><div class='metric-value'>{avg_pnl:.2f}</div></div>", unsafe_allow_html=True)
    else:
        st.info("Nenhuma ordem aberta para exibir estatísticas.")

    st.subheader("Distribuição de Ordens por Resultado (Geral)")
    if not df_closed.empty:
        result_counts = df_closed['resultado'].value_counts().reset_index()
        result_counts.columns = ['Resultado', 'Total']
        fig_result = px.pie(result_counts, names='Resultado', values='Total', title="Distribuição de Ordens por Resultado")
        st.plotly_chart(fig_result)
    else:
        st.info("Nenhuma ordem fechada para exibir o gráfico.")

    st.header("Desempenho por Combinação")
    if not df.empty:
        df['pnl_current'] = df.apply(
            lambda row: (get_mark_price(row['par']) - float(row['preco_entrada'])) / float(row['preco_entrada']) * 100
            if row['estado'] == 'aberto' and row['direcao'] == 'LONG'
            else (float(row['preco_entrada']) - get_mark_price(row['par'])) / float(row['preco_entrada']) * 100
            if row['estado'] == 'aberto' and row['direcao'] == 'SHORT'
            else row['pnl_realizado'], axis=1
        )
        grouped = df.groupby(['strategy_name', 'timeframe', 'direcao']).agg({
            'pnl_current': 'mean',
            'signal_id': 'count'
        }).reset_index()
        grouped.rename(columns={'pnl_current': 'PNL Médio (%)', 'signal_id': 'Total Ordens'}, inplace=True)

        fig = px.bar(
            grouped,
            x='timeframe',
            y='PNL Médio (%)',
            color='direcao',
            barmode='group',
            facet_col='strategy_name',
            title="PNL Médio por Combinação (Robô, Timeframe, Direção)",
            labels={'timeframe': 'Timeframe', 'PNL Médio (%)': 'PNL Médio (%)', 'direcao': 'Direção'},
            height=600
        )
        st.plotly_chart(fig)
        st.table(grouped)
    else:
                st.info("Nenhum dado disponível para exibir o desempenho por combinação.")

    st.header("Treinamento do Modelo")
    if st.button("Forçar Treinamento do Modelo"):
        try:
            learning_engine.train()
            st.success("Modelo treinado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao treinar o modelo: {e}")

    st.subheader("Acurácia do Modelo de Aprendizado")
    st.metric(label="Acurácia Atual", value=f"{learning_engine.accuracy * 100:.2f}%")

    st.subheader("Indicadores Utilizados pelo Modelo")
    st.write(", ".join(learning_engine.features))

    st.header("Configurações Atuais")
    config = load_config()
    col1, col2, col3, col4 = st.columns(4)
    col1.write(f"**TP Percentual Padrão:** {config.get('tp_percent', 2.0)}%")
    col2.write(f"**SL Percentual Padrão:** {config.get('sl_percent', 1.0)}%")
    col3.write(f"**Leverage:** {config.get('leverage', 22)}x")
    col4.write(f"**Máximo de Trades Simultaneos:** {config.get('max_trades_simultaneos', 50)}")

    st.header("Métricas Quantitativas Avançadas por Robô")
    if not df_closed.empty:
        advanced_metrics = calculate_advanced_metrics(df_closed)
        if advanced_metrics:
            metrics_df = pd.DataFrame.from_dict(advanced_metrics, orient='index')
            metrics_df = metrics_df.rename_axis('Robô').reset_index()
            # Formatação segura para evitar erro de colunas ausentes ou tipos incompatíveis
            format_dict = {
                'total_pnl': '{:.2f}',
                'win_rate': '{:.2f}',
                'avg_win': '{:.2f}',
                'avg_loss': '{:.2f}',
                'payoff_ratio': '{:.2f}',
                'expectancia': '{:.2f}',
                'sharpe': '{:.2f}',
                'max_drawdown': '{:.2f}'
            }
            format_dict = {k: v for k, v in format_dict.items() if k in metrics_df.columns}
            # Garante que só formata colunas numéricas
            for k in list(format_dict.keys()):
                if not pd.api.types.is_numeric_dtype(metrics_df[k]):
                    del format_dict[k]
            if format_dict:
                st.dataframe(metrics_df.style.format(format_dict), use_container_width=True)
            else:
                st.dataframe(metrics_df, use_container_width=True)
        else:
            st.info("Ainda não há dados suficientes para calcular as métricas avançadas.")
    else:
        st.info("Nenhuma ordem fechada para exibir métricas avançadas.")

    # Filtros para ativar/desativar cada robô
    st.subheader("Ativar/Desativar Robôs")
    if 'active_strategies' not in st.session_state:
        st.session_state['active_strategies'] = load_robot_status()
    for strategy_name in strategies.keys():
        ativo = st.session_state['active_strategies'].get(strategy_name, True)
        novo_ativo = st.checkbox(f"{strategy_name}", value=ativo, key=f"toggle_{strategy_name}")
        st.session_state['active_strategies'][strategy_name] = novo_ativo

with tab2:
    st.header("Ordens")
    st.info("Visualize e filtre ordens simuladas (dry run), ordens fechadas e sinais gerados.")

    # Card global de resumo acima dos filtros
    st.subheader("Resumo Geral de Ordens")
    total_abertas = len(df[df['estado'] == 'aberto'])
    total_fechadas = len(df[df['estado'] == 'fechado'])
    pnl_aberto = df[df['estado'] == 'aberto']['lucro_percentual'].sum(skipna=True)
    pnl_fechado = df[df['estado'] == 'fechado']['pnl_realizado'].sum(skipna=True)
    colA, colB, colC, colD = st.columns([2,2,2,2])
    colA.metric("Ordens em Aberto", total_abertas)
    colB.metric("Ordens Fechadas", total_fechadas)
    colC.metric("PNL Ordens Abertas (%)", f"{pnl_aberto:.2f}")
    colD.metric("PNL Ordens Fechadas (%)", f"{pnl_fechado:.2f}")
    # Botão de fechar todas as ordens
    if colD.button("Fechar Todas as Ordens", key="close_all_orders", help="Fecha todas as ordens em aberto", use_container_width=True):
        for _, row in df[df['estado'] == 'aberto'].iterrows():
            mark_price = get_mark_price(row['par'])
            if mark_price is not None:
                close_order_manually(row['signal_id'], mark_price)
        st.success("Todas as ordens em aberto foram fechadas!")
        st.rerun()

    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        date_filter = st.date_input("Filtrar por Data", value=(datetime.now() - timedelta(days=7), datetime.now()))
    with col2:
        state_filter = st.multiselect("Estado", ["Todas", "Abertas", "Fechadas"], default=["Todas", "Abertas", "Fechadas"])

    col3, col4 = st.columns(2)
    with col3:
        direction_filter = st.multiselect("Direção", ["LONG", "SHORT"], default=["LONG", "SHORT"])
    with col4:
        par_filter = st.multiselect("Par", options=df['par'].unique(), default=df['par'].unique())

    col5, col6 = st.columns(2)
    with col5:
        tp_values = sorted(df.apply(lambda row: get_tp_sl(row, 'tp_percent'), axis=1).unique())
        tp_filter = st.multiselect("TP (%)", options=tp_values, default=tp_values)
    with col6:
        sl_values = sorted(df.apply(lambda row: get_tp_sl(row, 'sl_percent'), axis=1).unique())
        sl_filter = st.multiselect("SL (%)", options=sl_values, default=sl_values)

    col7 = st.columns(1)[0]
    with col7:
        robot_names = list(strategies.keys())
        robot_filter = st.multiselect("Nome do Robô", options=robot_names, default=robot_names)

    # Filtrar dados com base nos filtros
    filtered_df = df[
        (df['timestamp'].dt.date >= date_filter[0]) &
        (df['timestamp'].dt.date <= date_filter[1]) &
        (df['direcao'].isin(direction_filter)) &
        (df['par'].isin(par_filter)) &
        (df['strategy_name'].isin(robot_filter))
    ]

    if "Todas" not in state_filter:
        filtered_df = filtered_df[filtered_df['estado'].isin([state.lower() for state in state_filter])]

    filtered_df = filtered_df[
        (filtered_df.apply(lambda row: get_tp_sl(row, 'tp_percent'), axis=1).isin(tp_filter)) &
        (filtered_df.apply(lambda row: get_tp_sl(row, 'sl_percent'), axis=1).isin(sl_filter))
    ]

    # Seção: Posições Simuladas (Dry Run)
    st.subheader("Posições Simuladas (Dry Run)")
    filtered_open = filtered_df[filtered_df['estado'] == 'aberto'].sort_values(by='timestamp', ascending=False)
    logger.info(f"Ordens abertas após filtros: {len(filtered_open)}")

    if not filtered_open.empty:
        display_data = []
        for _, row in filtered_open.iterrows():
            mark_price = get_mark_price(row['par'])
            if mark_price is None:
                continue
            entry_price = float(row['preco_entrada'])
            direction = row['direcao']
            params = json.loads(row['parametros'])
            tp_percent = params.get('tp_percent', 2.0)
            sl_percent = params.get('sl_percent', 1.0)
            leverage = params.get('leverage', 22)

            liq_price = calculate_liq_price(entry_price, leverage, direction)
            distance_to_tp, distance_to_sl = calculate_distances(entry_price, mark_price, tp_percent, sl_percent, direction)
            if direction == "LONG":
                pnl = (mark_price - entry_price) / entry_price * 100
            else:
                pnl = (entry_price - mark_price) / entry_price * 100
            open_time = row['timestamp'].to_pydatetime()
            time_elapsed = (datetime.now() - open_time).total_seconds() / 60
            win_rate, avg_pnl, total_signals = calcular_confiabilidade_historica(
                row['strategy_name'], row['direcao'], df_closed
            )
            # Correção: definir status_emoji e resumo
            status_emoji = "🟠🟢" if pnl >= 0 else "🟠🔴"
            valores_indicadores = json.loads(row['localizadores'])
            resumo = gerar_resumo([row['contributing_indicators']], valores_indicadores)

            display_data.append({
                "Status": status_emoji,
                "Par": row['par'],
                "Direction": row['direcao'],
                "Entry Price": f"{entry_price:.4f}",
                "Mark Price": f"{mark_price:.4f}",
                "Liq. Price": f"{liq_price:.4f}",
                "Distance to TP (%)": f"{distance_to_tp:.2f}%",
                "Distance to SL (%)": f"{distance_to_sl:.2f}%",
                "PNL (%)": f"{pnl:.2f}%",
                "Time (min)": f"{time_elapsed:.2f}",
                "Strategy": row['strategy_name'],
                "Signal ID": row['signal_id'],
                "Motivos": row['motivos'],
                "Resumo": resumo,
                "Timeframe": row['timeframe'],
                "Quantity": row['quantity'],
                "Historical Win Rate (%)": f"{win_rate:.1f}",
                "Avg PNL (%)": f"{avg_pnl:.2f}",
                "Total Signals": total_signals,
                "Aceito": "Sim" if row['aceito'] else "Não",
                "TP Percent": params['tp_percent'],
                "SL Percent": params['sl_percent'],
                "Quality Score": f"{row['quality_score']:.2f}" if 'quality_score' in row else "N/A",
                "Contributing Indicators": row['contributing_indicators']
            })

        if display_data:
            display_df = pd.DataFrame(display_data)
            display_df = display_df[["Status", "Par", "Direction", "Entry Price", "Mark Price", "Liq. Price", "Distance to TP (%)", "Distance to SL (%)", "PNL (%)", "Time (min)", "Strategy", "Signal ID", "Motivos", "Resumo", "Timeframe", "Quantity", "Historical Win Rate (%)", "Avg PNL (%)", "Total Signals", "Aceito", "TP Percent", "SL Percent", "Quality Score", "Contributing Indicators"]]

            # Inicializar estados para paginação e expansão
            if 'open_orders_page' not in st.session_state:
                st.session_state['open_orders_page'] = 1
            if 'expanded_open_orders' not in st.session_state:
                st.session_state['expanded_open_orders'] = {}

            page_size = 10  # Exibir 10 ordens por página
            start_idx = (st.session_state['open_orders_page'] - 1) * page_size
            end_idx = min(start_idx + page_size, len(display_df))
            total_pages = (len(display_df) + page_size - 1) // page_size

            # Exibir ordens da página atual
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            for idx, row in display_df.iloc[start_idx:end_idx].iterrows():
                order_id = row['Signal ID']
                order_key = f"toggle_open_{order_id}"

                # Verificar se a ordem está expandida
                is_expanded = st.session_state['expanded_open_orders'].get(order_id, False)

                # Layout com botão de expandir/recolher ao lado
                col1, col2, col3 = st.columns([7, 1, 1])
                with col1:
                    st.table(row[["Status", "Par", "Direction", "Entry Price", "Mark Price", "Liq. Price", "Distance to TP (%)", "Distance to SL (%)", "PNL (%)", "Time (min)", "Strategy"]].to_frame().T)
                with col2:
                    if st.button(
                        "Recolher" if is_expanded else "Expandir",
                        key=order_key,
                        help="Expandir/recolher os detalhes da estratégia"
                    ):
                        st.session_state['expanded_open_orders'][order_id] = not is_expanded
                        # Fechar outras ordens expandidas
                        for other_id in list(st.session_state['expanded_open_orders'].keys()):
                            if other_id != order_id:
                                st.session_state['expanded_open_orders'][other_id] = False
                        st.rerun()
                with col3:
                    if st.button("Fechar Ordem", key=f"close_{order_id}"):
                        close_order_manually(order_id, float(row['Mark Price']))
                        st.rerun()

                # Exibir detalhes se expandido
                if is_expanded:
                    st.markdown(f"""
<div class="strategy-header">
🟦 [ULTRABOT] SINAL GERADO - {row['Par']} ({row['Timeframe']}) - {row['Direction']} 🟦
</div>
<div class="strategy-section">
<p><strong>Id da ordem:</strong> {row['Signal ID']}</p>
<p>💰 <strong>Preço de Entrada:</strong> {row['Entry Price']} | <strong>Quantidade:</strong> {row['Quantity']}</p>
<p>🎯 <strong>TP:</strong> <span style="color: green;">+{row['TP Percent']}%</span> | <strong>SL:</strong> <span style="color: red;">-{row['SL Percent']}%</span></p>
<p>🧠 <strong>Estratégia:</strong> {row['Strategy']}</p>
<p>📌 <strong>Motivos do Sinal:</strong> {row['Resumo']}</p>
<p>📊 <strong>Indicadores Utilizados:</strong></p>
<p>- {row['Contributing Indicators']}</p>
<p>📈 <strong>Confiabilidade Histórica:</strong> {row['Historical Win Rate (%)']}% ({row['Total Signals']} sinais)</p>
<p>💵 <strong>PnL Médio por Sinal:</strong> {row['Avg PNL (%)']}%</p>
<p>✅ <strong>Status:</strong> Sinal {row['Aceito']} (Dry-Run Interno)</p>
<p>🌟 <strong>Score de Qualidade:</strong> {row['Quality Score']}</p>
</div>
                    """, unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

            # Controles de navegação para paginação
            if total_pages > 1:
                col_prev, col_next = st.columns(2)
                with col_prev:
                    if st.session_state['open_orders_page'] > 1:
                        if st.button("Carregar Anteriores", key="prev_open"):
                            st.session_state['open_orders_page'] -= 1
                            st.session_state['expanded_open_orders'] = {}
                            st.rerun()
                with col_next:
                    if st.session_state['open_orders_page'] < total_pages:
                        if st.button("Carregar Mais", key="next_open"):
                            st.session_state['open_orders_page'] += 1
                            st.session_state['expanded_open_orders'] = {}
                            st.rerun()
        else:
            st.info("Nenhuma posição simulada corresponde aos filtros selecionados.")
    else:
        st.info("Nenhuma posição simulada no modo Dry Run.")

    # Seção: Histórico de Ordens Fechadas
    st.subheader("Histórico de Ordens Fechadas")
    filtered_closed = filtered_df[filtered_df['estado'] == 'fechado'].sort_values(by='timestamp_saida', ascending=False)
    if not filtered_closed.empty:
        closed_display = []
        for _, row in filtered_closed.iterrows():
            status_emoji = "🟠🟢" if row['pnl_realizado'] >= 0 else "🟠🔴"
            valores_indicadores = json.loads(row['localizadores'])
            resumo = gerar_resumo([row['contributing_indicators']], valores_indicadores)
            win_rate, avg_pnl, total_signals = calcular_confiabilidade_historica(
                row['strategy_name'], row['direcao'], df_closed
            )
            params = json.loads(row['parametros'])

            closed_display.append({
                "Status": status_emoji,
                "Par": row['par'],
                "Direction": row['direcao'],
                "Entry Price": f"{float(row['preco_entrada']):.4f}",
                "Exit Price": f"{float(row['preco_saida']):.4f}",
                "PNL (%)": f"{float(row['pnl_realizado']):.2f}%",
                "Resultado": row['resultado'],
                "Strategy": row['strategy_name'],
                "Open Time": row['timestamp'],
                "Close Time": row['timestamp_saida'],
                "Motivos": row['motivos'],
                "Resumo": resumo,
                "Timeframe": row['timeframe'],
                "Quantity": row['quantity'],
                "Historical Win Rate (%)": f"{win_rate:.1f}",
                "Avg PNL (%)": f"{avg_pnl:.2f}",
                "Total Signals": total_signals,
                "Aceito": "Sim" if row['aceito'] else "Não",
                "TP Percent": params['tp_percent'],
                "SL Percent": params['sl_percent'],
                "Quality Score": f"{row['quality_score']:.2f}" if 'quality_score' in row else "N/A",
                "Contributing Indicators": row['contributing_indicators'],
                "Signal ID": row['signal_id']
            })

        if closed_display:
            closed_df = pd.DataFrame(closed_display)
            closed_df = closed_df[["Status", "Par", "Direction", "Entry Price", "Exit Price", "PNL (%)", "Resultado", "Strategy", "Open Time", "Close Time", "Motivos", "Resumo", "Timeframe", "Quantity", "Historical Win Rate (%)", "Avg PNL (%)", "Total Signals", "Aceito", "TP Percent", "SL Percent", "Quality Score", "Contributing Indicators", "Signal ID"]]

            # Inicializar estados para paginação e expansão
            if 'closed_orders_page' not in st.session_state:
                st.session_state['closed_orders_page'] = 1
            if 'expanded_closed_orders' not in st.session_state:
                st.session_state['expanded_closed_orders'] = {}

            page_size = 10  # Exibir 10 ordens por página
            start_idx = (st.session_state['closed_orders_page'] - 1) * page_size
            end_idx = min(start_idx + page_size, len(closed_df))
            total_pages = (len(closed_df) + page_size - 1) // page_size

            # Exibir ordens da página atual
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            for idx, row in closed_df.iloc[start_idx:end_idx].iterrows():
                order_id = row['Signal ID']
                order_key = f"toggle_closed_{order_id}_{idx}"

                # Verificar se a ordem está expandida
                is_expanded = st.session_state['expanded_closed_orders'].get(order_id, False)

                # Layout com botão de expandir/recolher ao lado
                col1, col2 = st.columns([8, 1])
                with col1:
                    st.table(row[["Status", "Par", "Direction", "Entry Price", "Exit Price", "PNL (%)", "Resultado", "Strategy", "Open Time", "Close Time"]].to_frame().T)
                with col2:
                    if st.button(
                        "Recolher" if is_expanded else "Expandir",
                        key=order_key,
                        help="Expandir/recolher os detalhes da estratégia"
                    ):
                        st.session_state['expanded_closed_orders'][order_id] = not is_expanded
                        # Fechar outras ordens expandidas
                        for other_id in list(st.session_state['expanded_closed_orders'].keys()):
                            if other_id != order_id:
                                st.session_state['expanded_closed_orders'][other_id] = False
                        st.rerun()

                # Exibir detalhes se expandido
                if is_expanded:
                    st.markdown(f"""
<div class="strategy-header">
🟦 [ULTRABOT] SINAL GERADO - {row['Par']} ({row['Timeframe']}) - {row['Direction']} 🟦
</div>
<div class="strategy-section">
<p><strong>Id da ordem:</strong> {row['Signal ID']}</p>
<p>💰 <strong>Preço de Entrada:</strong> {row['Entry Price']} | <strong>Quantidade:</strong> {row['Quantity']}</p>
<p>🎯 <strong>TP:</strong> <span style="color: green;">+{row['TP Percent']}%</span> | <strong>SL:</strong> <span style="color: red;">-{row['SL Percent']}%</span></p>
<p>🧠 <strong>Estratégia:</strong> {row['Strategy']}</p>
<p>📌 <strong>Motivos do Sinal:</strong> {row['Resumo']}</p>
<p>📊 <strong>Indicadores Utilizados:</strong></p>
<p>- {row['Contributing Indicators']}</p>
<p>📈 <strong>Confiabilidade Histórica:</strong> {row['Historical Win Rate (%)']}% ({row['Total Signals']} sinais)</p>
<p>💵 <strong>PnL Médio por Sinal:</strong> {row['Avg PNL (%)']}%</p>
<p>✅ <strong>Status:</strong> Sinal {row['Aceito']} (Dry-Run Interno)</p>
<p>🌟 <strong>Score de Qualidade:</strong> {row['Quality Score']}</p>
</div>
                    """, unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

            # Controles de navegação para paginação
            if total_pages > 1:
                col_prev, col_next = st.columns(2)
                with col_prev:
                    if st.session_state['closed_orders_page'] > 1:
                        if st.button("Carregar Anteriores", key="prev_closed"):
                            st.session_state['closed_orders_page'] -= 1
                            st.session_state['expanded_closed_orders'] = {}
                            st.rerun()
                with col_next:
                    if st.session_state['closed_orders_page'] < total_pages:
                        if st.button("Carregar Mais", key="next_closed"):
                            st.session_state['closed_orders_page'] += 1
                            st.session_state['expanded_closed_orders'] = {}
                            st.rerun()
        else:
            st.info("Nenhuma ordem fechada corresponde aos filtros selecionados.")
    else:
        st.info("Nenhuma ordem fechada no modo Dry Run.")

    # Seção: Sinais Gerados
    st.subheader("Sinais Gerados")
    if not filtered_df.empty:
        signals_display = []
        for _, row in filtered_df.iterrows():
            signals_display.append({
                "Timestamp": row['timestamp'],
                "Par": row['par'],
                "Direção": row['direcao'],
                "Estratégia": row['strategy_name'],
                "Timeframe": row['timeframe'],
                "Aceito": "Sim" if row['aceito'] else "Não",
                "Quality Score": f"{row['quality_score']:.2f}" if 'quality_score' in row else "N/A"
            })

        signals_df = pd.DataFrame(signals_display)
        signals_df = signals_df[["Timestamp", "Par", "Direção", "Estratégia", "Timeframe", "Aceito", "Quality Score"]]

        # Inicializar estado para paginação
        if 'signals_page' not in st.session_state:
            st.session_state['signals_page'] = 1

        page_size = 10  # Exibir 10 sinais por página
        start_idx = (st.session_state['signals_page'] - 1) * page_size
        end_idx = min(start_idx + page_size, len(signals_df))
        total_pages = (len(signals_df) + page_size - 1) // page_size

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.table(signals_df.iloc[start_idx:end_idx])
        st.markdown('</div>', unsafe_allow_html=True)

        # Controles de navegação para paginação
        if total_pages > 1:
            col_prev, col_next = st.columns(2)
            with col_prev:
                if st.session_state['signals_page'] > 1:
                    if st.button("Carregar Anteriores", key="prev_signals"):
                        st.session_state['signals_page'] -= 1
                        st.rerun()
            with col_next:
                if st.session_state['signals_page'] < total_pages:
                    if st.button("Carregar Mais", key="next_signals"):
                        st.session_state['signals_page'] += 1
                        st.rerun()
    else:
        st.info("Nenhum sinal gerado para exibir.")

    # Seção: Alertas e Notificações
    st.header("Alertas e Notificações")
    alerts = []
    for signal_id in new_orders:
        order = df_open[df_open['signal_id'] == signal_id].iloc[0]
        alerts.append(f"🔔 {order['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} - Robô {order['strategy_name']}: Nova ordem aberta: {signal_id} ({order['par']}) - {order['direcao']}")

    alerts.extend(check_alerts(filtered_open))

    # Recarregar o DataFrame após fechar ordens
    df = pd.read_csv(SINALS_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df_open = df[df['estado'] == 'aberto']
    df_closed = df[df['estado'] == 'fechado']
    filtered_df = df[
        (df['timestamp'].dt.date >= date_filter[0]) &
        (df['timestamp'].dt.date <= date_filter[1]) &
        (df['direcao'].isin(direction_filter)) &
        (df['par'].isin(par_filter)) &
        (df['strategy_name'].isin(robot_filter))
    ]
    if "Todas" not in state_filter:
        filtered_df = filtered_df[filtered_df['estado'].isin([state.lower() for state in state_filter])]
    filtered_df = filtered_df[
        (filtered_df.apply(lambda row: get_tp_sl(row, 'tp_percent'), axis=1).isin(tp_filter)) &
        (filtered_df.apply(lambda row: get_tp_sl(row, 'sl_percent'), axis=1).isin(sl_filter))
    ]

    if alerts:
        robots = set([alert.split(":")[0].replace("🔔 ", "").replace("🚨 ", "").replace("⚠️ ", "").replace("📈 ", "").replace("📉 ", "") for alert in alerts])
        for robot in robots:
            with st.expander(f"Alertas - {robot}"):
                robot_alerts = [alert for alert in alerts if alert.startswith(robot)]
                for alert in robot_alerts:
                    if "🚨" in alert:
                        st.markdown(f"<div class='alert alert-warning'>{alert}</div>", unsafe_allow_html=True)
                    elif "⚠️" in alert:
                        st.markdown(f"<div class='alert alert-danger'>{alert}</div>", unsafe_allow_html=True)
                    elif "🔔" in alert:
                        st.markdown(f"<div class='alert alert-success'>{alert}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='alert alert-success'>{alert}</div>", unsafe_allow_html=True)
    else:
        st.info("Nenhum alerta ou notificação no momento.")

with tab3:
    st.header("Configurações de Estratégia")
    st.info("Configure os parâmetros das estratégias de trading.")

    # Lista de indicadores
    indicadores_simples = [
        "SMA", "EMA", "RSI", "MACD", "ADX", "Volume", "Bollinger",
        "Estocastico", "VWAP", "OBV", "Fibonacci", "Sentimento"
    ]
    indicadores_compostos = [
        "Swing Trade Composite"
    ]

    # Inicializar config se não existir
    if 'config' not in st.session_state:
        st.session_state.config = {
            "indicadores_ativos": {ind: True for ind in (indicadores_simples + indicadores_compostos)},
            "confianca_minima": {ind: 0.5 for ind in ["Sentimento", "Swing Trade Composite"]},
            "tp_percent": 2.0,
            "sl_percent": 1.0,
            "leverage": 22,
            "max_trades_simultaneos": 1,
            "score_tecnico_min": 0.3,
            "ml_confidence_min": 0.5,
            "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]
        }

    config = st.session_state.config

    # Controles para Indicadores Simples
    st.subheader("Indicadores Simples")
    for indicador in indicadores_simples:
        config["indicadores_ativos"][indicador] = st.checkbox(
            f"Ativar {indicador}", value=config["indicadores_ativos"].get(indicador, True)
        )
        if config["indicadores_ativos"][indicador] and indicador in ["Sentimento"]:
            config["confianca_minima"][indicador] = st.slider(
                f"Confiança Mínima para {indicador}",
                min_value=0.0,
                max_value=1.0,
                value=config["confianca_minima"].get(indicador, 0.5),
                step=0.01
            )

    # Controles para Indicadores Compostos
    st.subheader("Indicadores Compostos")
    for indicador in indicadores_compostos:
        config["indicadores_ativos"][indicador] = st.checkbox(
            f"Ativar {indicador}", value=config["indicadores_ativos"].get(indicador, True)
        )
        if config["indicadores_ativos"][indicador]:
            config["confianca_minima"][indicador] = st.slider(
                f"Confiança Mínima para {indicador}",
                min_value=0.0,
                max_value=1.0,
                value=config["confianca_minima"].get(indicador, 0.5),
                step=0.01
            )

    # Controles para Timeframes
    st.subheader("Timeframes")
    config["timeframes"] = st.multiselect(
        "Selecione os Timeframes",
        options=["1m", "5m", "15m", "1h", "4h", "1d"],
        default=config.get("timeframes", ["1m", "5m", "15m", "1h", "4h", "1d"])
    )

    # Controles para Parâmetros Gerais
    st.subheader("Parâmetros Gerais")
    config["tp_percent"] = st.number_input(
        "TP (%)", min_value=0.1, max_value=100.0, value=config.get("tp_percent", 2.0), step=0.1
    )
    config["sl_percent"] = st.number_input(
        "SL (%)", min_value=0.1, max_value=100.0, value=config.get("sl_percent", 1.0), step=0.1
    )
    config["leverage"] = st.number_input(
        "Leverage (x)", min_value=1, max_value=125, value=config.get("leverage", 22), step=1
    )
    config["max_trades_simultaneos"] = st.number_input(
        "Máximo de Trades Simultaneos", min_value=1, max_value=100, value=config.get("max_trades_simultaneos", 1), step=1
    )
    config["score_tecnico_min"] = st.slider(
        "Score Técnico Mínimo", min_value=0.0, max_value=1.0, value=config.get("score_tecnico_min", 0.3), step=0.01
    )
    config["ml_confidence_min"] = st.slider(
        "Confiança ML Mínima", min_value=0.0, max_value=1.0, value=config.get("ml_confidence_min", 0.5), step=0.01
    )

    # Salvar como Nova Estratégia
    st.subheader("Salvar Estratégia")
    strategy_name = st.text_input("Nome da Estratégia")
    if st.button("Salvar como Nova Estratégia"):
        if strategy_name:
            strategies = load_strategies()
            strategies[strategy_name] = config.copy()
            save_strategies(strategies)
            st.success(f"Estratégia '{strategy_name}' salva com sucesso!")
        else:
            st.error("Por favor, insira um nome para a estratégia.")

with tab4:
    st.header("Oportunidades Perdidas")
    st.info("Visualize os sinais que foram rejeitados devido a limites de ordens.")

    if not df_missed.empty:
        # Filtros para oportunidades perdidas
        col1, col2 = st.columns(2)
        with col1:
            missed_date_filter = st.date_input("Filtrar por Data (Oportunidades Perdidas)", value=(datetime.now() - timedelta(days=7), datetime.now()))
        with col2:
            missed_robot_filter = st.multiselect("Nome do Robô", options=df_missed['robot_name'].unique(), default=df_missed['robot_name'].unique())

        filtered_missed = df_missed[
            (df_missed['timestamp'].dt.date >= missed_date_filter[0]) &
            (df_missed['timestamp'].dt.date <= missed_date_filter[1]) &
            (df_missed['robot_name'].isin(missed_robot_filter))
        ].sort_values(by='timestamp', ascending=False)

        # Exibir as últimas 5 oportunidades perdidas
        st.subheader("Últimas 5 Oportunidades Perdidas")
        st.table(filtered_missed.head(5)[['timestamp', 'robot_name', 'par', 'timeframe', 'direcao', 'score_tecnico', 'reason']])

        # Infinite scroll simulado para oportunidades perdidas
        if 'missed_opportunities_page' not in st.session_state:
            st.session_state['missed_opportunities_page'] = 1

        page_size = 5
        start_idx = (st.session_state['missed_opportunities_page'] - 1) * page_size
        end_idx = min(start_idx + page_size, len(filtered_missed))
        total_pages = (len(filtered_missed) + page_size - 1) // page_size

        st.table(filtered_missed.iloc[start_idx:end_idx][['timestamp', 'robot_name', 'par', 'timeframe', 'direcao', 'score_tecnico', 'reason']])

        if total_pages > 1:
            col_prev, col_next = st.columns(2)
            with col_prev:
                if st.session_state['missed_opportunities_page'] > 1:
                    if st.button("Carregar Anteriores", key="prev_missed"):
                        st.session_state['missed_opportunities_page'] -= 1
                        st.rerun()
            with col_next:
                if st.session_state['missed_opportunities_page'] < total_pages:
                    if st.button("Carregar Mais", key="next_missed"):
                        st.session_state['missed_opportunities_page'] += 1
                        st.rerun()

        # Gráfico de Oportunidades Perdidas por Robô
        st.subheader("Distribuição de Oportunidades Perdidas por Robô")
        missed_by_robot = filtered_missed.groupby('robot_name').size().reset_index(name='Total')
        fig_missed = px.pie(missed_by_robot, names='robot_name', values='Total', title="Oportunidades Perdidas por Robô")
        st.plotly_chart(fig_missed)
    else:
        st.info("Nenhuma oportunidade perdida registrada.")

with tab5:
    # --- Identidade Visual Binance ---
    st.markdown("""
    <style>
    body, .stApp { background-color: #1A1D26 !important; color: #F5F5F5; font-family: 'Inter', 'Roboto', sans-serif; }
    .binance-table th, .binance-table td { border: 1px solid #23262F; padding: 8px; }
    .binance-table { width: 100%; border-collapse: collapse; background: #23262F; color: #F5F5F5; }
    .binance-table tr:nth-child(even) { background: #181A20; }
    .binance-table tr:hover { background: #262930; }
    .binance-long { color: #0ECB81; font-weight: bold; }
    .binance-short { color: #F6465D; font-weight: bold; }
    .binance-yellow { background: #F0B90B !important; color: #181A20 !important; font-weight: bold; border-radius: 4px; border: none; padding: 4px 12px; margin-right: 4px; }
    .binance-yellow:hover { background: #FFD700 !important; }
    .binance-gray { background: #23262F !important; color: #F5F5F5 !important; border-radius: 4px; border: 1px solid #393C49; padding: 4px 12px; }
    .binance-gray:hover { background: #F0B90B !important; color: #181A20 !important; }
    .binance-pnl-pos { color: #0ECB81; font-weight: bold; }
    .binance-pnl-neg { color: #F6465D; font-weight: bold; }
    .binance-nav { background: #181A20; border-radius: 8px; padding: 8px 0; margin-bottom: 16px; display: flex; gap: 16px; }
    .binance-nav-btn { color: #F5F5F5; background: none; border: none; font-size: 16px; padding: 8px 20px; cursor: pointer; border-radius: 6px; }
    .binance-nav-btn.selected, .binance-nav-btn:hover { background: #23262F; color: #F0B90B; }
    .binance-refresh { background: #23262F; color: #F0B90B; border: none; border-radius: 4px; padding: 4px 16px; margin-left: 8px; }
    .binance-refresh:hover { background: #F0B90B; color: #181A20; }
    .binance-closeall { background: #F0B90B; color: #181A20; border: none; border-radius: 4px; padding: 6px 18px; font-weight: bold; margin-bottom: 12px; }
    .binance-closeall:hover { background: #FFD700; }
    .binance-delay { color: #F0B90B; font-size: 12px; margin-bottom: 8px; }
    </style>
    """, unsafe_allow_html=True)

    # --- Menu de Navegação Binance ---
    if 'binance_nav_selected' not in st.session_state:
        st.session_state['binance_nav_selected'] = "Open Orders"
    nav_options = ["Open Orders", "Closed Orders"]
    # Remover os botões brancos antigos:
    # nav_cols = st.columns(len(nav_options))
    # for i, opt in enumerate(nav_options):
    #     if nav_cols[i].button(opt, key=f"nav_{opt}", help=f"Ver {opt}", use_container_width=True):
    #         st.session_state['binance_nav_selected'] = opt

    # Substituir por apenas o menu visual (fundo escuro, texto dourado)
    st.markdown('<div class="binance-nav">' + ''.join([
        f'<button class="binance-nav-btn {"selected" if st.session_state["binance_nav_selected"]==opt else ""}" onclick="window.location.reload();">{opt}</button>' for opt in nav_options
    ]) + '</div>', unsafe_allow_html=True)

    # --- Dados reais da Binance ---
    from binance.client import Client
    from config import DRY_RUN, REAL_API_KEY, REAL_API_SECRET, DRY_RUN_API_KEY, DRY_RUN_API_SECRET

    # Inicializa o client com as chaves corretas
    if DRY_RUN:
        binance_client = Client(DRY_RUN_API_KEY, DRY_RUN_API_SECRET)
    else:
        binance_client = Client(REAL_API_KEY, REAL_API_SECRET)

    def get_open_binance_orders():
        try:
            positions = binance_client.futures_account()['positions']
            open_orders = []
            for pos in positions:
                amt = float(pos['positionAmt'])
                if amt != 0:
                    symbol = pos['symbol']
                    entry = float(pos['entryPrice'])
                    # Corrige erro de ausência de markPrice
                    if 'markPrice' in pos and pos['markPrice']:
                        mark = float(pos['markPrice'])
                    else:
                        mark = float(binance_client.futures_mark_price(symbol=symbol)['markPrice'])
                    pnl = float(pos['unrealizedProfit'])
                    side = 'Long' if amt > 0 else 'Short'
                    leverage = int(pos['leverage'])
                    size = abs(amt) * mark
                    roi = (pnl / (abs(amt) * entry) * 100) if entry > 0 else 0
                    open_orders.append({
                        'symbol': symbol,
                        'size': size,
                        'entry': entry,
                        'mark': mark,
                        'pnl': pnl,
                        'roi': roi,
                        'side': side,
                        'leverage': leverage,
                        'positionAmt': amt  # Adiciona o valor real da posição
                    })
            return open_orders
        except Exception as e:
            st.error(f"Erro ao buscar ordens abertas da Binance: {e}")
            return []

    def get_closed_binance_orders(limit=20):
        try:
            closed = binance_client.futures_account_trades()
            # Filtra apenas ordens fechadas (isBuyer/isMaker pode ser usado para lógica mais avançada)
            closed_orders = []
            for o in closed[-limit:][::-1]:
                closed_orders.append({
                    'symbol': o['symbol'],
                    'type': 'Perp',
                    'status': 'Closed',
                    'closing_pnl': float(o.get('realizedPnl', 0)),
                    'entry': float(o.get('price', 0)),
                    'close': float(o.get('price', 0)),
                    'oi': float(o.get('qty', 0)),
                    'vol': float(o.get('qty', 0)),
                    'opened': pd.to_datetime(o['time'], unit='ms').strftime('%d/%m/%Y %H:%M:%S'),
                    'closed': pd.to_datetime(o['time'], unit='ms').strftime('%d/%m/%Y %H:%M:%S')
                })
            return closed_orders
        except Exception as e:
            st.error(f"Erro ao buscar ordens fechadas da Binance: {e}")
            return []

    # --- Open Orders (reais) ---
    if st.session_state['binance_nav_selected'] == "Open Orders":
        st.markdown('<div class="binance-delay">Atualização automática a cada 1-2 minutos. <b>Delay esperado!</b></div>', unsafe_allow_html=True)
        # Remover botões duplicados de refresh/closeall se existirem acima do menu
        # st.button("Refresh", key="refresh_open_orders", help="Atualizar ordens", use_container_width=True)
        # st.button("Close All Positions", key="close_all_binance", help="Fechar todas as posições", use_container_width=True, type="primary")
        open_orders = get_open_binance_orders()
        total_pnl = sum([o['pnl'] for o in open_orders])
        pnl_class_total = 'binance-pnl-pos' if total_pnl >= 0 else 'binance-pnl-neg'
        st.markdown(f'<div style="font-size:18px;font-weight:bold;margin-bottom:8px;">Total PNL: <span class="{pnl_class_total}">{total_pnl:.2f} USDT</span></div>', unsafe_allow_html=True)

        for o in open_orders:
            pnl_class = 'binance-pnl-pos' if o['pnl'] >= 0 else 'binance-pnl-neg'
            side_class = 'binance-long' if o['side'] == 'Long' else 'binance-short'
            market_btn_key = f"close_market_{o['symbol']}"
            limit_btn_key = f"close_limit_{o['symbol']}"

            cols = st.columns([2, 2, 2, 2, 2, 2, 2, 2])
            with cols[0]:
                st.markdown(f"{o['symbol']}")
            with cols[1]:
                st.markdown(f"{o['size']:.6f} USDT")
            with cols[2]:
                st.markdown(f"{o['entry']:.6f}")
            with cols[3]:
                st.markdown(f"{o['mark']:.6f}")
            with cols[4]:
                st.markdown(f"<span class='{pnl_class}'>{o['pnl']:.2f} USDT ({o['roi']:.2f}%)</span>", unsafe_allow_html=True)
            with cols[5]:
                st.markdown(f"<span class='{side_class}'>{o['side']}</span>", unsafe_allow_html=True)
            with cols[6]:
                st.markdown(f"Perp {o['leverage']}x")
            with cols[7]:
                # Botão Market funcional (já fecha a posição na Binance)
                if st.button("Market", key=market_btn_key, help="Fechar posição a mercado", use_container_width=True):
                    try:
                        qty = abs(o['positionAmt'])
                        if qty == 0:
                            st.warning(f"Sem posição aberta em {o['symbol']}.")
                        else:
                            side = 'SELL' if o['side'] == 'Long' else 'BUY'
                            binance_client.futures_create_order(
                                symbol=o['symbol'],
                                side=side,
                                type='MARKET',
                                quantity=qty,
                                reduceOnly=True
                            )
                            st.success(f"Posição {o['symbol']} fechada com sucesso via Market!")
                            st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Erro ao fechar posição {o['symbol']}: {e}")
                # Botão Limit funcional
                limit_price = st.number_input(
                    f"Preço limite para {o['symbol']}",
                    min_value=0.0,
                    value=float(o['mark']),
                    key=f"limit_price_{o['symbol']}"
                )
                if st.button("Limit", key=limit_btn_key, help="Fechar posição a limite", use_container_width=True):
                    try:
                        qty = abs(o['positionAmt'])
                        if qty == 0:
                            st.warning(f"Sem posição aberta em {o['symbol']}.")
                        else:
                            side = 'SELL' if o['side'] == 'Long' else 'BUY'
                            binance_client.futures_create_order(
                                symbol=o['symbol'],
                                side=side,
                                type='LIMIT',
                                quantity=qty,
                                price=limit_price,
                                timeInForce='GTC',
                                reduceOnly=True
                            )
                            st.success(f"Ordem LIMIT enviada para fechar {o['symbol']} ({side}) em {limit_price}.")
                            st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Erro ao enviar ordem LIMIT para {o['symbol']}: {e}")

    # --- Closed Orders (reais) ---
    if st.session_state['binance_nav_selected'] == "Closed Orders":
        st.markdown('<div style="margin-bottom:12px;">'
            '<select style="margin-right:8px;padding:4px 8px;border-radius:4px;background:#23262F;color:#F5F5F5;">'
            '<option>1 Day</option><option>1 Week</option><option>1 Month</option><option>3 Months</option>'
            '</select>'
            '<select style="margin-right:8px;padding:4px 8px;border-radius:4px;background:#23262F;color:#F5F5F5;">'
            '<option>All Symbols</option><option>DOGEUSDT</option><option>XRPUSDT</option>'
            '</select>'
            '<button class="binance-refresh">Reset</button>'
            '</div>', unsafe_allow_html=True)
        closed_orders = get_closed_binance_orders()
        for o in closed_orders:
            pnl_class = 'binance-pnl-pos' if o['closing_pnl'] >= 0 else 'binance-pnl-neg'
            st.markdown(f'<div style="background:#23262F;border-radius:8px;padding:16px;margin-bottom:12px;">'
                f'<div style="font-size:18px;font-weight:bold;">{o["symbol"]}</div>'
                f'<div style="font-size:14px;color:#F0B90B;">{o["type"]} | {o["status"]}</div>'
                f'<div style="margin:8px 0 4px 0;">Closing PNL: <span class="{pnl_class}">{o["closing_pnl"]:+.2f} USDT</span></div>'
                f'<div>Entry Price: {o["entry"]:.6f} USDT | Avg. Close Price: {o["close"]:.6f} USDT</div>'
                f'<div>Max Open Interest: {o["oi"]:,} | Closed Vol.: {o["vol"]:,}</div>'
                f'<div>Opened: {o["opened"]} | Closed: {o["closed"]}</div>'
                '</div>', unsafe_allow_html=True)

# Nova aba "Meus Robôs 🤖"
with tab6:
    # Ajuste no CSS para o emoji de robô e botões deslizantes
    st.markdown("""
    <style>
    .profile-pic {
        width: 60px;
        height: 60px;
        background: linear-gradient(135deg, #00d4ff, #1e3c72); /* Gradiente moderno */
        border-radius: 50%;
        position: absolute;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 36px; /* Tamanho maior para o emoji */
        color: #ffffff; /* Cor do emoji */
        box-shadow: 0 0 8px rgba(0, 212, 255, 0.5); /* Sombra para destaque */
    }
    .toggle-switch {
        position: relative;
        width: 40px;
        height: 20px;
        background-color: #ccc; /* Cinza quando desligado */
        border-radius: 20px;
        cursor: pointer;
        transition: background-color 0.3s ease;
        margin: 0 5px;
    }
    .toggle-switch.active {
        background-color: #28a745; /* Verde quando ligado */
    }
    .toggle-switch .toggle-circle {
        position: absolute;
        top: 2px;
        left: 2px;
        width: 16px;
        height: 16px;
        background-color: white;
        border-radius: 50%;
        transition: transform 0.3s ease;
    }
    .toggle-switch.active .toggle-circle {
        transform: translateX(20px); /* Move o círculo para a direita quando ligado */
    }
    .toggle-switch:hover {
        opacity: 0.9;
    }
    .toggle-label {
        font-size: 0.9em;
        color: #666;
        margin-right: 5px;
    }
    .robot-card .toggle-container {
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 5px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    st.header("Meus Robôs 🤖")
    st.info("Visualize o desempenho de cada robô com base nas negociações fechadas.")

    # Filtrar apenas negociações fechadas (sem filtro de par específico)
    df_closed = df[df['estado'] == 'fechado']

    if not df_closed.empty:
        # Converter timestamps para datetime
        df_closed['timestamp'] = pd.to_datetime(df_closed['timestamp'])
        df_closed['timestamp_saida'] = pd.to_datetime(df_closed['timestamp_saida'])

        # Agrupar por strategy_name para calcular métricas gerais
        summary = df_closed.groupby('strategy_name').agg(
            num_negociacoes=('signal_id', 'count'),
            pnl_total=('pnl_realizado', 'sum'),
            negociacoes_positivas=('pnl_realizado', lambda x: (x > 0).sum()),
            lucro_percentual_medio=('lucro_percentual', 'mean'),
            duracao_media=('timestamp', lambda x: ((df_closed.loc[x.index, 'timestamp_saida'] - x).dt.total_seconds() / 3600).mean()),
            taxa_aceitas=('aceito', lambda x: (x == True).sum()),
            score_qualidade_medio=('quality_score', 'mean'),
            percent_long=('direcao', lambda x: (x == 'LONG').sum()),
            percent_short=('direcao', lambda x: (x == 'SHORT').sum()),
            taxa_sl=('resultado', lambda x: (x == 'SL').sum()),
            indicadores_frequentes=('contributing_indicators', lambda x: get_frequent_indicators(x)),
            timeframe_mais_usado=('timeframe', lambda x: x.mode().iloc[0] if not x.mode().empty else 'N/A')
        ).reset_index()

        # Ajustar métricas
        summary['taxa_vitoria'] = (summary['negociacoes_positivas'] / summary['num_negociacoes'] * 100).round(2)
        summary['media_pnl'] = (summary['pnl_total'] / summary['num_negociacoes']).round(4)
        summary['lucro_percentual_medio'] = summary['lucro_percentual_medio'].round(2)
        summary['duracao_media'] = summary['duracao_media'].round(1)
        summary['taxa_aceitas'] = (summary['taxa_aceitas'] / summary['num_negociacoes'] * 100).round(2)
        summary['score_qualidade_medio'] = summary['score_qualidade_medio'].round(2)
        summary['percent_long'] = (summary['percent_long'] / summary['num_negociacoes'] * 100).round(2)
        summary['percent_short'] = (summary['percent_short'] / summary['num_negociacoes'] * 100).round(2)
        summary['taxa_sl'] = (summary['taxa_sl'] / summary['num_negociacoes'] * 100).round(2)

        # Calcular par mais lucrativo por robô
        par_summary = df_closed.groupby(['strategy_name', 'par'])['pnl_realizado'].sum().reset_index()
        par_most_profitable = par_summary.loc[par_summary.groupby('strategy_name')['pnl_realizado'].idxmax()][['strategy_name', 'par', 'pnl_realizado']]

        # Calcular timeframe mais lucrativo e direção mais lucrativa para o par mais lucrativo
        timeframe_direction_summary = df_closed.groupby(['strategy_name', 'par', 'timeframe', 'direcao'])['pnl_realizado'].sum().reset_index()
        par_timeframe_direction = {}
        for _, row in par_most_profitable.iterrows():
            strategy = row['strategy_name']
            par = row['par']
            # Filtrar para o par mais lucrativo
            df_par = timeframe_direction_summary[(timeframe_direction_summary['strategy_name'] == strategy) & (timeframe_direction_summary['par'] == par)]
            # Timeframe mais lucrativo
            timeframe_profitable = df_par.groupby('timeframe')['pnl_realizado'].sum().idxmax()
            # Direção mais lucrativa
            direction_profitable = df_par.groupby('direcao')['pnl_realizado'].sum().idxmax()
            par_timeframe_direction[strategy] = {
                'par': par,
                'timeframe': timeframe_profitable,
                'direction': direction_profitable
            }

        # Exibir os cards lado a lado usando st.columns
        num_cols_per_row = 4  # Número de cards por linha
        for i in range(0, len(summary), num_cols_per_row):
            cols = st.columns(num_cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(summary):
                    row = summary.iloc[idx]
                    strategy_name = row['strategy_name']
                    # Obter status do robô
                    is_active = st.session_state.get('active_strategies', {}).get(strategy_name, False)
                    # Obter par mais lucrativo, timeframe e direção
                    par_info = par_timeframe_direction.get(strategy_name, {'par': 'N/A', 'timeframe': 'N/A', 'direction': 'N/A'})

                    with col:
                        card_html = f"""
                        <div class="robot-card">
                            <div class="profile-pic">🤖</div>
                            <div class="more-options">⋮</div>
                            <h3>{strategy_name}</h3>
                            <div class="stats">
                                <div><span>{row['num_negociacoes']}</span> Negociações</div>
                                <div><span>{row['pnl_total']:.4f}</span> PNL Total</div>
                            </div>
                            <div class="toggle-container">
                                <span class="toggle-label">{'Ativado' if is_active else 'Desativado'}</span>
                                <div class="toggle-switch {'active' if is_active else ''}">
                                    <div class="toggle-circle"></div>
                                </div>
                            </div>
                            <div class="toggle-container">
                                <span class="toggle-label">Dry Run {'Ativado' if is_active else 'Desativado'}</span>
                                <div class="toggle-switch {'active' if is_active else ''}">
                                    <div class="toggle-circle"></div>
                                </div>
                            </div>
                            <div class="toggle-container">
                                <span class="toggle-label">Binance {'Ativado' if is_active else 'Desativado'}</span>
                                <div class="toggle-switch {'active' if is_active else ''}">
                                    <div class="toggle-circle"></div>
                                </div>
                            </div>
                            <p><strong>Taxa de Vitória:</strong> {row['taxa_vitoria']:.2f}%</p>
                            <p><strong>Média de PNL:</strong> {row['media_pnl']:.4f}</p>
                            <p><strong>Lucro Percentual Médio:</strong> {row['lucro_percentual_medio']:.2f}%</p>
                            <p><strong>Duração Média (horas):</strong> {row['duracao_media']:.1f}</p>
                            <p><strong>Taxa de Negociações Aceitas:</strong> {row['taxa_aceitas']:.2f}%</p>
                            <p><strong>Score de Qualidade Médio:</strong> {row['score_qualidade_medio']:.2f}</p>
                            <p><strong>Percentual LONG/SHORT:</strong> {row['percent_long']:.2f}% / {row['percent_short']:.2f}%</p>
                            <p><strong>Taxa de Stop-Loss:</strong> {row['taxa_sl']:.2f}%</p>
                            <p><strong>Indicadores Frequentes:</strong> {row['indicadores_frequentes']}</p>
                            <p><strong>Timeframe Mais Usado:</strong> {row['timeframe_mais_usado']}</p>
                            <p><strong>Timeframe Vencedor:</strong> 1h</p>
                            <p><strong>Par Mais Lucrativo:</strong> {par_info['par']}</p>
                            <p><strong>Timeframe Mais Lucrativo (Par):</strong> {par_info['timeframe']}</p>
                            <p><strong>Direção Mais Lucrativa (Par):</strong> {par_info['direction']}</p>
                        </div>
                        """
                        st.markdown(card_html, unsafe_allow_html=True)
    else:
        st.info("Nenhuma negociação fechada encontrada.")

# Seção de Robôs Ativos
st.markdown("**Robôs Ativos**")
st.markdown('<div class="robot-container">', unsafe_allow_html=True)
active_strategies = st.session_state.get('active_strategies', load_robot_status())

# Verificar mudanças no status dos robôs e gerar ordens
previous_active_strategies = st.session_state.get('previous_active_strategies', {})
for strategy_name, strategy_config in strategies.items():
    if strategy_name in active_strategies and active_strategies[strategy_name]:
        if strategy_name not in previous_active_strategies or not previous_active_strategies[strategy_name]:
            generate_orders(strategy_name, strategy_config)

with tab7:
    st.header("ML Machine - Treinamento e Métricas do Modelo de Aprendizado")
    st.info("Acompanhe o desempenho do modelo de Machine Learning, treine novamente e visualize métricas detalhadas.")

    # Visualização da acurácia
    st.subheader("Acurácia do Modelo de Aprendizado")
    st.metric(label="Acurácia Atual", value=f"{learning_engine.accuracy * 100:.2f}%")

    # Botão para treinar o modelo
    if st.button("Forçar Treinamento do Modelo ML", key="ml_train_button"):
        try:
            learning_engine.train()
            st.success("Modelo treinado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao treinar o modelo: {e}")

    # Visualização dos indicadores/features
    st.subheader("Indicadores Utilizados pelo Modelo")
    st.write(", ".join(learning_engine.features))

    # Exemplo de visualização de matriz de confusão e importância das features (se disponíveis)
    if hasattr(learning_engine, 'confusion_matrix_'):
        import plotly.figure_factory as ff
        cm = learning_engine.confusion_matrix_
        z = cm.tolist() if hasattr(cm, 'tolist') else cm
        fig = ff.create_annotated_heatmap(z, x=["Negativo", "Positivo"], y=["Negativo", "Positivo"], colorscale='Blues')
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Matriz de Confusão do Modelo")
    if hasattr(learning_engine, 'feature_importances_'):
        import plotly.graph_objects as go
        fig = go.Figure([go.Bar(x=learning_engine.features, y=learning_engine.feature_importances_)])
        fig.update_layout(title="Importância das Features", xaxis_title="Feature", yaxis_title="Importância")
        st.plotly_chart(fig, use_container_width=True)

    # Outras métricas customizadas
    if hasattr(learning_engine, 'classification_report_'):
        st.subheader("Relatório de Classificação")
        st.text(learning_engine.classification_report_)