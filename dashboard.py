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

st.set_page_config(page_title="UltraBot Dashboard 9.0", layout="wide")

SINALS_FILE = "sinais_detalhados.csv"
CONFIG_FILE = "config.json"
STRATEGIES_FILE = "strategies.json"
ROBOT_STATUS_FILE = "robot_status.json"
MISSED_OPPORTUNITIES_FILE = "oportunidades_perdidas.csv"

# Verificar se as credenciais estão presentes no st.secrets
if "binance" not in st.secrets or "api_key" not in st.secrets["binance"] or "api_secret" not in st.secrets["binance"]:
    try:
        # Tentar carregar o arquivo secrets.toml manualmente
        secrets = toml.load("secrets.toml")
        st.secrets["binance"] = secrets.get("binance", {})
    except Exception as e:
        raise KeyError("As credenciais da API Binance não foram encontradas. Certifique-se de que o arquivo secrets.toml está configurado corretamente.") from e

api_key = st.secrets["binance"]["api_key"]
api_secret = st.secrets["binance"]["api_secret"]

if not api_key or not api_secret:
    raise ValueError("As credenciais da API da Binance não foram configuradas. Certifique-se de definir as chaves no arquivo secrets.toml.")

# Adicionar teste de conectividade com a API Binance e logs detalhados
logging.basicConfig(level=logging.DEBUG)

# Adicionar log para capturar o código de retorno da API Binance
try:
    logging.info("Testando conectividade com a API Binance...")
    client = Client(api_key=st.secrets["binance"]["api_key"], api_secret=st.secrets["binance"]["api_secret"])
    client.ping()  # Testa a conectividade com a API
    logging.info("Conexão com a API Binance bem-sucedida!")
except BinanceAPIException as e:
    logging.error(f"Erro na API Binance: Código de retorno {e.status_code}, Mensagem: {e.message}")
    raise
except Exception as e:
    logging.error(f"Erro inesperado: {e}")
    raise

learning_engine = LearningEngine()

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

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
        padding: 12px 24px;
        font-size: 16px;
        border: none;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.2);
        transition: background-color 0.3s ease, transform 0.2s ease;
    }

    .stButton>button:hover {
        background-color: #0056b3;
        transform: translateY(-2px);
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

    .stTable {
        border-collapse: collapse;
        width: 100%;
        background-color: #f5f5f5;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.1);
    }

    .stTable th {
        background-color: #007bff;
        color: white;
        padding: 12px;
        text-align: left;
        font-weight: 500;
    }

    .stTable td {
        padding: 12px;
        color: #333333;
        border-bottom: 1px solid #dddddd;
    }

    .stTable tr:nth-child(even) {
        background-color: #e9ecef;
    }

    .stTable tr:hover {
        background-color: #dee2e6;
        transition: background-color 0.2s ease;
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
        margin-top: 5px;
    }

    .robot-tag .toggle-button {
        background-color: #007bff;
        color: white;
        border: none;
        border-radius: 3px;
        padding: 3px 6px;
        cursor: pointer;
        font-family: 'Orbitron', sans-serif;
        font-size: 10px;
        transition: background-color 0.3s ease;
    }

    .robot-tag .toggle-button:hover {
        background-color: #0056b3;
    }

    .robot-tag .toggle-button-off {
        background-color: #ff5555;
        color: white;
    }

    .robot-tag .toggle-button-off:hover {
        background-color: #cc4444;
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

    .right_leg {
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

    .status-table {
        border-collapse: collapse;
        width: 100%;
        background-color: #f5f5f5;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 20px;
    }

    .status-table th {
        background-color: #007bff;
        color: white;
        padding: 12px;
        text-align: left;
        font-weight: 500;
    }

    .status-table td {
        padding: 12px;
        color: #333333;
        border-bottom: 1px solid #dddddd;
    }

    .status-table tr:nth-child(even) {
        background-color: #e9ecef;
    }

    .status-table tr:hover {
        background-color: #dee2e6;
        transition: background-color 0.2s ease;
    }
    </style>
""", unsafe_allow_html=True)

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

    timeframe = strategy_config.get('timeframes', ["1d"])[0]

    historical_data = download_historical_data(selected_pair, interval=timeframe, lookback='30 days')
    if historical_data is None or len(historical_data) < 50:
        logger.warning(f"Dados insuficientes para {selected_pair} no timeframe {timeframe}.")
        return

    indicators = calculate_indicators(historical_data, active_indicators)

    localizadores = {
        "EMA12>EMA50": str(indicators.get("EMA12>EMA50", False)).lower(),
        "RSI Sobrevendido": str(indicators.get("RSI Sobrevendido", False)).lower(),
        "MACD Cruzamento Alta": str(indicators.get("MACD Cruzamento Alta", False)).lower(),
        "Swing_Trade_Composite_LONG": str(indicators.get("Swing_Trade_Composite_LONG", False)).lower(),
        "Swing_Trade_Composite_SHORT": str(indicators.get("Swing_Trade_Composite_SHORT", False)).lower(),
        "ML_Confidence": strategy_config['ml_confidence_min']
    }

    should_generate_order = any([
        indicators.get("EMA12>EMA50", False),
        indicators.get("RSI Sobrevendido", False),
        indicators.get("MACD Cruzamento Alta", False),
        indicators.get("Swing_Trade_Composite_LONG", False),
        indicators.get("Swing_Trade_Composite_SHORT", False)
    ])

    if not should_generate_order:
        logger.info(f"Nenhuma condição de indicador atendida para {robot_name} no par {selected_pair}.")
        return

    direction = "LONG" if indicators.get("EMA12>EMA50", False) or indicators.get("MACD Cruzamento Alta", False) or indicators.get("Swing_Trade_Composite_LONG", False) else "SHORT"

    new_order = {
        'signal_id': str(uuid.uuid4()),
        'par': selected_pair,
        'direcao': direction,
        'preco_entrada': historical_data['close'].iloc[-1],
        'preco_saida': np.nan,
        'quantity': random.uniform(50.0, 200.0),
        'lucro_percentual': np.nan,
        'pnl_realizado': np.nan,
        'resultado': np.nan,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'timestamp_saida': np.nan,
        'estado': "aberto",
        'strategy_name': robot_name,
        'contributing_indicators': contributing_indicators,
        'localizadores': json.dumps(localizadores),
        'motivos': "Ordem gerada com base em indicadores reais",
        'timeframe': timeframe,
        'aceito': True,
        'parametros': json.dumps(params),
        'quality_score': 0.5  # Valor fictício para simulação
    }

    df = pd.concat([df, pd.DataFrame([new_order])], ignore_index=True)
    df.to_csv(SINALS_FILE, index=False)
    logger.info(f"Ordem simulada gerada para o robô {robot_name} no par {selected_pair}.")
    return new_order

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
            alerts.append(f"✅ Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) fechada: atingiu o TP! ({row['timeframe']}) ({direction})")
        elif distance_to_sl <= 0:
            close_order(row['signal_id'], mark_price, "SL")
            alerts.append(f"❌ Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) fechada: atingiu o SL! ({row['timeframe']}) ({direction})")
        else:
            if distance_to_tp > 0 and distance_to_tp <= 0.5:
                alerts.append(f"🚨 Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) está a {distance_to_tp:.2f}% do TP! ({row['timeframe']}) ({direction})")
            if distance_to_sl > 0 and distance_to_sl <= 0.5:
                alerts.append(f"⚠️ Robô {robot_name}: Ordem {row['signal_id']} ({symbol}) está a {distance_to_sl:.2f}% do SL! ({row['timeframe']}) ({direction})")

    log_file = "bot.log"
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = f.readlines()
        recent_logs = [log for log in logs if "ERROR" in log and datetime.strptime(log[:19], "%Y-%m-%d %H:%M:%S") > datetime.now() - timedelta(minutes=5)]
        for log in recent_logs:
            if "Erro ao verificar histórico de preços" in log:
                alerts.append(f"⚠️ Sistema: Erro detectado: {log.strip()}")

    df = pd.read_csv(SINALS_FILE)
    df_closed = df[df['estado'] == 'fechado']
    if len(df_closed[df_closed['resultado'].isin(['TP', 'SL'])]) < 5:
        alerts.append("⚠️ Sistema: Modelo de machine learning não treinado: menos de 5 ordens com TP/SL.")

    return alerts

def get_tp_sl(row, key, default=0.0):
    try:
        params = json.loads(row['parametros'])
        return params.get(key, default)
    except (json.JSONDecodeError, KeyError, TypeError):
        return default

# Adicionar validação para sincronizar o status dos robôs e as estatísticas gerais

def validate_robot_status_and_stats():
    # Carregar status dos robôs e dados do banco de dados
    robot_status = load_robot_status()
    df = pd.read_csv(SINALS_FILE)

    # Verificar inconsistências no status dos robôs
    for strategy_name, is_active in robot_status.items():
        active_orders = df[(df['strategy_name'] == strategy_name) & (df['estado'] == 'aberto')]
        if is_active and active_orders.empty:
            st.warning(f"Inconsistência detectada: Robô '{strategy_name}' está ativo, mas não possui ordens abertas.")
        elif not is_active and not active_orders.empty:
            st.warning(f"Inconsistência detectada: Robô '{strategy_name}' está inativo, mas possui ordens abertas.")

    # Desativar robôs não listados no status
    all_strategies = set(robot_status.keys())
    active_strategies_in_data = set(df['strategy_name'].unique())
    unlisted_strategies = active_strategies_in_data - all_strategies

    for strategy_name in unlisted_strategies:
        st.warning(f"Robô '{strategy_name}' não está listado no status dos robôs. Desativando automaticamente.")
        robot_status[strategy_name] = False

    # Salvar o status atualizado
    save_robot_status(robot_status)

# Chamar a validação no início do dashboard
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
    df_missed = pd.read_csv(MISSED_OPORTUNITIES_FILE)
    df_missed['timestamp'] = pd.to_datetime(df_missed['timestamp'])
else:
    df_missed = pd.DataFrame(columns=[
        'timestamp', 'robot_name', 'par', 'timeframe', 'direcao', 'score_tecnico',
        'contributing_indicators', 'reason'
    ])
    df_missed.to_csv(MISSED_OPORTUNITIES_FILE, index=False)

df_open = df[df['estado'] == 'aberto']
df_closed = df[df['estado'] == 'fechado']

if 'known_open_orders' not in st.session_state:
    st.session_state['known_open_orders'] = set()

current_open_orders = set(df_open['signal_id'].tolist())
new_orders = current_open_orders - st.session_state['known_open_orders']
st.session_state['known_open_orders'] = current_open_orders

# Carregar as estratégias e combinar com as fixas
strategies = load_strategies()
robot_status = load_robot_status()

# Cabeçalho com o robô decorativo
col_title, col_robot = st.columns([3, 1])
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

# Criar abas
tab1, tab2, tab3, tab4 = st.tabs(["Visão Geral", "Ordens", "Configurações de Estratégia", "Oportunidades Perdidas"])

# Aba 1: Visão Geral
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

        # Métricas adicionais
        robot_signals = df[df['strategy_name'] == strategy_name]
        signals_generated = len(robot_signals)
        signals_accepted = len(robot_signals[robot_signals['aceito'] == True])
        signals_rejected = len(robot_signals[robot_signals['aceito'] == False])
        avg_quality_score = robot_signals['quality_score'].mean() if 'quality_score' in robot_signals.columns and not robot_signals['quality_score'].isna().all() else 0.0
        # Contar ordens abertas
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
            "Ordens Abertas": open_orders,  # Nova coluna adicionada
            "Score Médio de Qualidade": f"{avg_quality_score:.2f}",
            "PNL Total": f"{total_pnl:.2f}% {alert}",
            "Taxa de Vitória": f"{win_rate:.2f}%"
        })

    # Exibir tabela com opção de ordenação
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

    # Gráfico de evolução do PNL por robô
    st.subheader("Evolução do PNL por Robô")
    if not df_closed.empty:
        chart_data = pd.DataFrame()
        for robot_name in status_df['Robô']:
            robot_df = df_closed[df_closed['strategy_name'] == robot_name].sort_values('timestamp')
            if not robot_df.empty:
                robot_df['timestamp'] = pd.to_datetime(robot_df['timestamp'])
                robot_df['Cumulative PNL'] = robot_df['pnl_realizado'].cumsum()
                chart_data[robot_name] = robot_df.set_index('timestamp')['Cumulative PNL']
        if not chart_data.empty:
            st.line_chart(chart_data)
        else:
            st.info("Nenhuma ordem fechada para exibir o gráfico.")
    else:
        st.info("Nenhuma ordem fechada para exibir o gráfico.")

    # Gráfico de distribuição de ordens por resultado
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

    st.header("Performance por Estratégia")
    if not df_closed.empty:
        strategy_stats = []
        for strategy in df_closed['strategy_name'].unique():
            strategy_df = df_closed[df_closed['strategy_name'] == strategy]
            total_orders = len(strategy_df)
            win_rate = len(strategy_df[strategy_df['pnl_realizado'] >= 0]) / total_orders * 100 if total_orders > 0 else 0
            avg_pnl = strategy_df['pnl_realizado'].mean() if total_orders > 0 else 0
            strategy_stats.append({
                "Estratégia": strategy,
                "Total de Ordens": total_orders,
                "Taxa de Vitória (%)": win_rate,
                "PNL Médio (%)": avg_pnl
            })
        strategy_df = pd.DataFrame(strategy_stats)
        st.table(strategy_df)
    else:
        st.info("Nenhuma ordem fechada para exibir a performance por estratégia.")

    # Gráfico de distribuição de ordens por resultado (geral)
    st.subheader("Distribuição de Ordens por Resultado (Geral)")
    if not df_closed.empty:
        result_counts = df_closed['resultado'].value_counts().reset_index()
        result_counts.columns = ['Resultado', 'Total']
        fig_result = px.pie(result_counts, names='Resultado', values='Total', title="Distribuição de Ordens por Resultado")
        st.plotly_chart(fig_result)
    else:
        st.info("Nenhuma ordem fechada para exibir o gráfico.")

    # Seção: Desempenho por Combinação (Robô, Timeframe, Direção)
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

    # Seção: Treinamento do Modelo
    st.header("Treinamento do Modelo")
    if st.button("Forçar Treinamento do Modelo"):
        try:
            learning_engine.train()
            st.success("Modelo treinado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao treinar o modelo: {e}")

    # Exibir Acurácia do Modelo
    st.subheader("Acurácia do Modelo de Aprendizado")
    st.metric(label="Acurácia Atual", value=f"{learning_engine.accuracy * 100:.2f}%")

    # Exibir Indicadores Utilizados
    st.subheader("Indicadores Utilizados pelo Modelo")
    st.write(", ".join(learning_engine.features))

    # Seção: Configurações Atuais
    st.header("Configurações Atuais")
    config = load_config()
    col1, col2, col3, col4 = st.columns(4)
    col1.write(f"**TP Percentual Padrão:** {config.get('tp_percent', 2.0)}%")
    col2.write(f"**SL Percentual Padrão:** {config.get('sl_percent', 1.0)}%")
    col3.write(f"**Leverage:** {config.get('leverage', 22)}x")
    col4.write(f"**Máximo de Trades Simultaneos:** {config.get('max_trades_simultaneos', 50)}")

    # Aba 2: Ordens
with tab2:
    st.header("Ordens")
    st.info("Visualize e filtre ordens simuladas (dry run), ordens fechadas e sinais gerados.")

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

    # Seção: Posições Simuladas (Dry Run) - Últimas 5
    st.subheader("Posições Simuladas (Dry Run) - Últimas 5")
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

            status_emoji = "🟢" if pnl >= 0 else "🔴"
            valores_indicadores = json.loads(row['localizadores'])
            resumo = gerar_resumo([row['contributing_indicators']], valores_indicadores)
            win_rate, avg_pnl, total_signals = calcular_confiabilidade_historica(
                row['strategy_name'], row['direcao'], df_closed
            )

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
                "Indicadores": row['contributing_indicators'],
                "Strategy": row['strategy_name'],
                "Signal ID": row['signal_id'],
                "Motivos": row['motivos'],
                "Resumo": resumo,
                "Timeframe": row['timeframe'],
                "Quantity": row['quantity'],
                "Historical Win Rate (%)": win_rate,
                "Avg PNL (%)": avg_pnl,
                "Total Signals": total_signals,
                "Aceito": "Sim" if row['aceito'] else "Não",
                "TP Percent": params['tp_percent'],
                "SL Percent": params['sl_percent'],
                "Quality Score": f"{row['quality_score']:.2f}" if 'quality_score' in row else "N/A"
            })

        if display_data:
            display_df = pd.DataFrame(display_data)
            display_df = display_df[["Status", "Par", "Direction", "Entry Price", "Mark Price", "Liq. Price", "Distance to TP (%)", "Distance to SL (%)", "PNL (%)", "Time (min)", "Indicadores", "Strategy", "Signal ID", "Motivos", "Resumo", "Timeframe", "Quantity", "Historical Win Rate (%)", "Avg PNL (%)", "Total Signals", "Aceito", "TP Percent", "SL Percent", "Quality Score"]]
            # Exibir as últimas 5 ordens abertas
            st.table(display_df.head(5).drop(['Signal ID', 'Motivos', 'Resumo', 'Timeframe', 'Quantity', 'Historical Win Rate (%)', 'Avg PNL (%)', 'Total Signals', 'Aceito', 'TP Percent', 'SL Percent', 'Quality Score'], axis=1))
            
            # Botão "Ver Mais"
            if len(display_df) > 5:
                if st.button("Ver Todas as Ordens Abertas"):
                    for idx, row in display_df.iterrows():
                        col1, col2 = st.columns([9, 1])
                        with col1:
                            st.table(row.drop(['Signal ID', 'Motivos', 'Resumo', 'Timeframe', 'Quantity', 'Historical Win Rate (%)', 'Avg PNL (%)', 'Total Signals', 'Aceito', 'TP Percent', 'SL Percent', 'Quality Score']).to_frame().T)
                            with st.expander(f"Detalhes da Estratégia: {row['Strategy']}"):
                                st.markdown(f"""
<div class="strategy-header">
🟦 [ULTRABOT] SINAL GERADO - {row['Par']} ({row['Timeframe']}) - {row['Direction']} 🟦
</div>
<div class="strategy-section">
<p>💰 <strong>Preço de Entrada:</strong> {row['Entry Price']} | <strong>Quantidade:</strong> {row['Quantity']}</p>
<p>🎯 <strong>TP:</strong> <span style="color: green;">+{row['TP Percent']}%</span> | <strong>SL:</strong> <span style="color: red;">-{row['SL Percent']}%</span></p>
<p>🧠 <strong>Estratégia:</strong> {row['Strategy']}</p>
<p>📌 <strong>Motivos do Sinal:</strong> {row['Resumo']}</p>
<p>📊 <strong>Indicadores Utilizados:</strong></p>
<p>- {row['Indicadores']}</p>
<p>📈 <strong>Confiabilidade Histórica:</strong> {row['Historical Win Rate (%)']}% ({row['Total Signals']} sinais)</p>
<p>💵 <strong>PnL Médio por Sinal:</strong> {row['Avg PNL (%)']}%</p>
<p>✅ <strong>Status:</strong> Sinal {row['Aceito']} (Dry-Run Interno)</p>
<p>🌟 <strong>Score de Qualidade:</strong> {row['Quality Score']}</p>
</div>
                                """, unsafe_allow_html=True)
                        with col2:
                            if st.button("Fechar Ordem", key=f"close_{row['Signal ID']}"):
                                close_order_manually(row['Signal ID'], float(row['Mark Price']))
                                st.rerun()
        else:
            st.info("Nenhuma posição simulada corresponde aos filtros selecionados.")
    else:
        st.info("Nenhuma posição simulada no modo Dry Run.")

    # Seção: Histórico de Ordens Fechadas - Últimas 5
    st.subheader("Histórico de Ordens Fechadas - Últimas 5")
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
                "Indicadores": row['contributing_indicators'],
                "Strategy": row['strategy_name'],
                "Open Time": row['timestamp'],
                "Close Time": row['timestamp_saida'],
                "Motivos": row['motivos'],
                "Resumo": resumo,
                "Timeframe": row['timeframe'],
                "Quantity": row['quantity'],
                "Historical Win Rate (%)": win_rate,
                "Avg PNL (%)": avg_pnl,
                "Total Signals": total_signals,
                "Aceito": "Sim" if row['aceito'] else "Não",
                "TP Percent": params['tp_percent'],
                "SL Percent": params['sl_percent'],
                "Quality Score": f"{row['quality_score']:.2f}" if 'quality_score' in row else "N/A"
            })

        if closed_display:
            closed_df = pd.DataFrame(closed_display)
            closed_df = closed_df[["Status", "Par", "Direction", "Entry Price", "Exit Price", "PNL (%)", "Resultado", "Indicadores", "Strategy", "Open Time", "Close Time", "Motivos", "Resumo", "Timeframe", "Quantity", "Historical Win Rate (%)", "Avg PNL (%)", "Total Signals", "Aceito", "TP Percent", "SL Percent", "Quality Score"]]
            # Exibir as últimas 5 ordens fechadas
            st.table(closed_df.head(5).drop(['Motivos', 'Resumo', 'Timeframe', 'Quantity', 'Historical Win Rate (%)', 'Avg PNL (%)', 'Total Signals', 'Aceito', 'TP Percent', 'SL Percent', 'Quality Score'], axis=1))

            # Botão "Ver Mais"
            if len(closed_df) > 5:
                if st.button("Ver Todas as Ordens Fechadas"):
                    for idx, row in closed_df.iterrows():
                        st.table(row.drop(['Motivos', 'Resumo', 'Timeframe', 'Quantity', 'Historical Win Rate (%)', 'Avg PNL (%)', 'Total Signals', 'Aceito', 'TP Percent', 'SL Percent', 'Quality Score']).to_frame().T)
                        with st.expander(f"Detalhes da Estratégia: {row['Strategy']}"):
                            st.markdown(f"""
<div class="strategy-header">
🟦 [ULTRABOT] SINAL GERADO - {row['Par']} ({row['Timeframe']}) - {row['Direction']} 🟦
</div>
<div class="strategy-section">
<p>💰 <strong>Preço de Entrada:</strong> {row['Entry Price']} | <strong>Quantidade:</strong> {row['Quantity']}</p>
<p>🎯 <strong>TP:</strong> <span style="color: green;">+{row['TP Percent']}%</span> | <strong>SL:</strong> <span style="color: red;">-{row['SL Percent']}%</span></p>
<p>🧠 <strong>Estratégia:</strong> {row['Strategy']}</p>
<p>📌 <strong>Motivos do Sinal:</strong> {row['Resumo']}</p>
<p>📊 <strong>Indicadores Utilizados:</p>
<p>- {row['Indicadores']}</p>
<p>📈 <strong>Confiabilidade Histórica:</strong> {row['Historical Win Rate (%)']}% ({row['Total Signals']} sinais)</p>
<p>💵 <strong>PnL Médio por Sinal:</strong> {row['Avg PNL (%)']}%</p>
<p>✅ <strong>Status:</strong> Sinal {row['Aceito']} (Dry-Run Interno)</p>
<p>🌟 <strong>Score de Qualidade:</strong> {row['Quality Score']}</p>
</div>
                            """, unsafe_allow_html=True)
        else:
            st.info("Nenhuma ordem fechada corresponde aos filtros selecionados.")
    else:
        st.info("Nenhuma ordem fechada no modo Dry Run.")

    # Seção: Sinais Gerados - Últimos 5
    st.subheader("Sinais Gerados - Últimos 5")
    if not filtered_df.empty:
        signals_display = []
        for _, row in filtered_df.iterrows():
            signals_display.append({
                "Timestamp": row['timestamp'],
                "Par": row['par'],
                "Direção": row['direcao'],
                "Estratégia": row['strategy_name'],
                "Timeframe": row['timeframe'],
                "Indicadores": row['contributing_indicators'],
                "Aceito": "Sim" if row['aceito'] else "Não",
                "Quality Score": f"{row['quality_score']:.2f}" if 'quality_score' in row else "N/A"
            })
        
        signals_df = pd.DataFrame(signals_display)
        signals_df = signals_df[["Timestamp", "Par", "Direção", "Estratégia", "Timeframe", "Indicadores", "Aceito", "Quality Score"]]
        # Exibir os últimos 5 sinais
        st.table(signals_df.head(5))

        # Botão "Ver Mais"
        if len(signals_df) > 5:
            if st.button("Ver Todos os Sinais"):
                st.table(signals_df)
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

    # Exibir alertas agrupados por robô
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
        st.info("Nenhum alerta no momento.")

# Aba 3: Configurações de Estratégia
with tab3:
    st.header("Configurações de Estratégia")

    # Seção de Reset do Bot
    st.header("Reset do Bot")
    st.warning("⚠️ Atenção: Esta ação irá resetar todas as ordens e estatísticas do bot!")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        reset_password = st.text_input("Senha de Reset", type="password")
    with col2:
        if st.button("Reset Bot", type="primary"):
            if reset_password:
                success, message = reset_bot_data(reset_password)
                if success:
                    st.success(message)
                    # Recarregar a página após 3 segundos
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Por favor, digite a senha de reset!")

    st.divider()  # Adiciona uma linha divisória

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

# Aba 4: Oportunidades Perdidas
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

        # Botão "Ver Mais"
        if len(filtered_missed) > 5:
            if st.button("Ver Todas as Oportunidades Perdidas"):
                st.table(filtered_missed[['timestamp', 'robot_name', 'par', 'timeframe', 'direcao', 'score_tecnico', 'reason']])

        # Gráfico de Oportunidades Perdidas por Robô
        st.subheader("Distribuição de Oportunidades Perdidas por Robô")
        missed_by_robot = filtered_missed.groupby('robot_name').size().reset_index(name='Total')
        fig_missed = px.pie(missed_by_robot, names='robot_name', values='Total', title="Oportunidades Perdidas por Robô")
        st.plotly_chart(fig_missed)
    else:
        st.info("Nenhuma oportunidade perdida registrada.")

# Seção de Robôs Ativos
st.markdown("**Robôs Ativos**")
st.markdown('<div class="robot-container">', unsafe_allow_html=True)
active_strategies = st.session_state.get('active_strategies', load_robot_status())

# Verificar mudanças no status dos robôs e gerar ordens
previous_active_strategies = st.session_state.get('previous_active_strategies', {})
for strategy_name, strategy_config in strategies.items():
    if strategy_name in active_strategies and active_strategies[strategy_name]:
        if strategy_name not in previous_active_strategies or not previous_active_strategies[strategy_name]:
            new_order = generate_orders(strategy_name, strategies[strategy_name])
            if new_order:
                signal_id = new_order['signal_id']
                alerts.append(f"🔔 {new_order['timestamp']} - Robô {strategy_name}: Nova ordem aberta: {signal_id} ({new_order['par']}) - {new_order['direcao']}")
    previous_active_strategies[strategy_name] = active_strategies.get(strategy_name, False)

st.session_state['previous_active_strategies'] = previous_active_strategies

# Exibir os robôs em containers lado a lado
cols = st.columns(3)  # Dividir em 3 colunas para organização
for idx, (strategy_name, strategy_config) in enumerate(strategies.items()):
    col = cols[idx % 3]  # Alternar entre as colunas
    with col:
        if strategy_name not in active_strategies:
            active_strategies[strategy_name] = False

        win_rate, avg_pnl, total_signals = calcular_confiabilidade_historica(strategy_name, "LONG", df_closed)
        open_orders = len(df_open[df_open['strategy_name'] == strategy_name])
        robot_df = df_closed[df_closed['strategy_name'] == strategy_name]
        num_tp = len(robot_df[robot_df['resultado'] == 'TP'])
        num_sl = len(robot_df[robot_df['resultado'] == 'SL'])
        roi = robot_df['pnl_realizado'].mean() if not robot_df.empty else 0

        if strategy_name not in st.session_state:
            st.session_state[strategy_name] = {'activation_time': None}
        if active_strategies[strategy_name] and st.session_state[strategy_name]['activation_time'] is None:
            st.session_state[strategy_name]['activation_time'] = datetime.now()
        if not active_strategies[strategy_name]:
            st.session_state[strategy_name]['activation_time'] = None

        online_time = "Desativado"
        if active_strategies[strategy_name] and st.session_state[strategy_name]['activation_time']:
            time_diff = datetime.now() - st.session_state[strategy_name]['activation_time']
            hours, remainder = divmod(time_diff.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            online_time = f"{int(hours)}h {int(minutes)}m"

        active_indicators = [ind for ind, active in strategy_config["indicadores_ativos"].items() if active]
        strategy_summary = f"{', '.join(active_indicators)}, TP: {strategy_config['tp_percent']}%, SL: {strategy_config['sl_percent']}%"

        st.markdown(f"""
        <div class="robot-tag">
            <h4>{strategy_name}</h4>
            <p>📊 {strategy_summary}</p>
            <p>🎯 Acertos: {win_rate:.2f}%</p>
            <p>📈 Ordens: {open_orders}</p>
            <p>⏳ Online: {online_time}</p>
            <p>✅ TP: {num_tp} | ❌ SL: {num_sl}</p>
            <p>💰 ROI%: {roi:.2f}%</p>
            <div class="button-container">
                <button class="toggle-button{' toggle-button-off' if not active_strategies[strategy_name] else ''}" onclick="this.closest('form').submit()">{ 'Desligar' if active_strategies[strategy_name] else 'Ligar' }</button>
                <button class="edit-button" onclick="this.closest('form').submit()">Editar</button>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Botões de controle
        col_toggle, col_edit = st.columns([1, 1])
        with col_toggle:
            button_label = "Desligar" if active_strategies[strategy_name] else "Ligar"
            if st.button(button_label, key=f"toggle_{strategy_name}"):
                active_strategies[strategy_name] = not active_strategies[strategy_name]
                st.session_state['active_strategies'] = active_strategies
                save_robot_status(active_strategies)
                st.rerun()
        with col_edit:
            if st.button("Editar", key=f"edit_{strategy_name}", help="Editar parâmetros do robô"):
                with st.expander(f"Editar Parâmetros - {strategy_name}"):
                    new_tp = st.number_input("TP (%)", min_value=0.1, max_value=100.0, value=strategy_config['tp_percent'], step=0.1, key=f"tp_{strategy_name}")
                    new_sl = st.number_input("SL (%)", min_value=0.1, max_value=100.0, value=strategy_config['sl_percent'], step=0.1, key=f"sl_{strategy_name}")
                    new_leverage = st.number_input("Leverage (x)", min_value=1, max_value=125, value=strategy_config['leverage'], step=1, key=f"leverage_{strategy_name}")
                    prioritize_signals = st.checkbox("Ativar Priorização de Sinais", value=strategy_config.get('prioritize_signals', False), key=f"prioritize_{strategy_name}")

                    # Configurar limites por timeframe e direção
                    st.subheader("Limites por Timeframe e Direção")
                    limits = strategy_config.get('limits', {tf: {"LONG": 1, "SHORT": 1} for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]})
                    new_limits = {}
                    for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
                        st.subheader(f"Limites para {tf}")
                        long_limit = st.number_input(f"Máximo de ordens LONG ({tf})", min_value=0, max_value=10, value=limits.get(tf, {}).get("LONG", 1), step=1, key=f"long_{tf}_{strategy_name}")
                        short_limit = st.number_input(f"Máximo de ordens SHORT ({tf})", min_value=0, max_value=10, value=limits.get(tf, {}).get("SHORT", 1), step=1, key=f"short_{tf}_{strategy_name}")
                        new_limits[tf] = {"LONG": long_limit, "SHORT": short_limit}

                    if st.button("Salvar Alterações", key=f"save_{strategy_name}"):
                        strategy_config['tp_percent'] = new_tp
                        strategy_config['sl_percent'] = new_sl
                        strategy_config['leverage'] = new_leverage
                        strategy_config['prioritize_signals'] = prioritize_signals
                        strategy_config['limits'] = new_limits
                        strategies[strategy_name] = strategy_config
                        save_strategies(strategies)
                        st.success(f"Parâmetros de {strategy_name} atualizados com sucesso!")
                        st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# Botão de Atualização
if st.button("Atualizar"):
    st.rerun()