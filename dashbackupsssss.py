import streamlit as st
import pandas as pd
import numpy as np
import json
import time
import os
import random
import ta
import plotly.express as px
import plotly.figure_factory as ff
import plotly.graph_objects as go
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException
from learning_engine import LearningEngine
from utils import logger, gerar_resumo, calcular_confiabilidade_historica
from strategy_manager import load_strategies, save_strategies
from trade_manager import check_timeframe_direction_limit, check_active_trades, save_signal_log, close_order
from notification_manager import send_telegram_alert
import uuid
import toml
import logging
from dashboard_utils import calculate_advanced_metrics
from config_grok import XAI_API_KEY
from xai import GrokAPI  # Placeholder para API do Grok

# Configuração inicial
st.set_page_config(page_title="UltraBot Dashboard", layout="wide", page_icon="🤖")
logging.basicConfig(level=logging.DEBUG)

# Carregar CSS e FontAwesome
if os.path.exists("static/style.css"):
    with open("static/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    st.markdown(
        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">',
        unsafe_allow_html=True
    )

# Inicializar API do Grok
grok_api = GrokAPI(api_key=XAI_API_KEY)

# Arquivos
SINALS_FILE = "sinais_detalhados.csv"
CONFIG_FILE = "config.json"
STRATEGIES_FILE = "strategies.json"
ROBOT_STATUS_FILE = "robot_status.json"
MISSED_OPPORTUNITIES_FILE = "oportunidades_perdidas.csv"

# Verificar credenciais Binance
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

# Inicializar LearningEngine
learning_engine = LearningEngine()

# Função para consultar Grok com cache
@st.cache_data(ttl=300)  # Cache de 5 minutos
def query_grok(prompt):
    try:
        response = grok_api.query(prompt)
        return response.get("answer", "Sem resposta")
    except Exception as e:
        logger.error(f"Erro na consulta ao Grok: {e}")
        return "Erro ao consultar Grok"

# Funções de suporte
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
        robot_open_orders = [t for t in active_trades if t['strategy_name'] == robot_name and t['estado'] == 'aberto']
        if len(robot_open_orders) >= 36:
            logger.warning(f"Limite de 36 ordens abertas por robô atingido para {robot_name}.")
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
        already_open = [t for t in robot_open_orders if t['par'] == selected_pair and t['timeframe'] == timeframe and t['direcao'] == direction]
        if already_open:
            logger.warning(f"Já existe ordem aberta para {robot_name} em {selected_pair}/{timeframe}/{direction}.")
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
    logger preço_entrada = historical_data['close'].iloc[-1]
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
        if 'strategy_name' not in df.columns or df.empty:
            logger.warning("Arquivo sinais_detalhados.csv está vazio ou sem a coluna 'strategy_name'.")
            return
        df = df.dropna(subset=['strategy_name'])
        df = df[df['strategy_name'].apply(lambda x: isinstance(x, str))]
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

# Inicializar dados
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

# Barra lateral
with st.sidebar:
    st.image("static/logo.png", width=150)  # Adicione um logo em static/
    st.markdown("<h2 class='sidebar-title'>UltraBot</h2>", unsafe_allow_html=True)
    page = st.radio(
        "Navegação",
        [
            "Visão Geral",
            "Pesquisa Grok",
            "Ordens",
            "Configurações de Estratégia",
            "Oportunidades Perdidas",
            "Ordens Binance",
            "Meus Robôs",
            "ML Machine"
        ],
        format_func=lambda x: {
            "Visão Geral": "<i class='fas fa-home'></i> Visão Geral",
            "Pesquisa Grok": "<i class='fas fa-search'></i> Pesquisa Grok",
            "Ordens": "<i class='fas fa-list'></i> Ordens",
            "Configurações de Estratégia": "<i class='fas fa-cog'></i> Configurações",
            "Oportunidades Perdidas": "<i class='fas fa-ban'></i> Oportunidades Perdidas",
            "Ordens Binance": "<i class='fas fa-exchange-alt'></i> Ordens Binance",
            "Meus Robôs": "<i class='fas fa-robot'></i> Meus Robôs",
            "ML Machine": "<i class='fas fa-chart-line'></i> ML Machine"
        }[x]
    )

# Aba: Visão Geral
if page == "Visão Geral":
    st.markdown("<h1 class='main-title'>UltraBot Dashboard</h1>", unsafe_allow_html=True)
    
    # Insights do Grok
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("<h2 class='section-title'>Sentimento do Mercado (X)</h2>", unsafe_allow_html=True)
        sentiment_prompt = (
            "Analise posts recentes no X sobre XRP, DOGE, TRX de @CoinDesk, @WatcherGuru, @crypto. "
            "Resuma o sentimento (bullish, bearish, neutro) e estime o impacto no preço."
        )
        sentiment = query_grok(sentiment_prompt)
        st.markdown(f"<div class='insight-card'>{sentiment}</div>", unsafe_allow_html=True)
        
        st.markdown("<h2 class='section-title'>Oportunidades e Alertas</h2>", unsafe_allow_html=True)
        anomaly_prompt = (
            "Detecte anomalias ou oportunidades de arbitragem para XRP/USDT, DOGE/USDT, TRX/USDT "
            "entre Binance e Coinbase."
        )
        anomaly = query_grok(anomaly_prompt)
        st.markdown(f"<div class='insight-card'>{anomaly}</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<h2 class='section-title'>Tendências de Mercado</h2>", unsafe_allow_html=True)
        trend_prompt = (
            "Preveja tendências de 6 horas para XRP/USDT, DOGE/USDT, TRX/USDT com base em notícias "
            "e preços das últimas 24 horas."
        )
        trend = query_grok(trend_prompt)
        st.markdown(f"<div class='insight-card'>{trend}</div>", unsafe_allow_html=True)
        
        # Gráfico de preços
        prices_df = pd.read_csv("precos_log.csv") if os.path.exists("precos_log.csv") else pd.DataFrame()
        if not prices_df.empty:
            fig = px.line(
                prices_df,
                x="timestamp",
                y="price",
                color="pair",
                title="Preços Recentes (XRP/USDT, DOGE/USDT, TRX/USDT)"
            )
            fig.update_layout(
                template="plotly_dark",
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font=dict(family="Inter", color="#d1d5db"),
                title_font=dict(size=20, color="#ffffff")
            )
            st.plotly_chart(fig, use_container_width=True)

    # Status dos Robôs
    st.markdown("<h2 class='section-title'>Status dos Robôs</h2>", unsafe_allow_html=True)
    active_strategies = st.session_state.get('active_strategies', load_robot_status())
    status_data = []
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
    st.markdown("<div class='table-container'>", unsafe_allow_html=True)
    st.table(status_df)
    st.markdown("</div>", unsafe_allow_html=True)

    # Distribuição de Ordens
    st.markdown("<h2 class='section-title'>Distribuição de Ordens por Resultado</h2>", unsafe_allow_html=True)
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
            fig.update_layout(
                template="plotly_dark",
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font=dict(family="Inter", color="#d1d5db")
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma ordem fechada para exibir o gráfico.")
    else:
        st.info("Nenhuma ordem fechada para exibir o gráfico.")

    # Estatísticas Gerais
    st.markdown("<h2 class='section-title'>Estatísticas Gerais</h2>", unsafe_allow_html=True)
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
        st.markdown(f"<div class='metric'><div class='metric-label'>Valor Total das Posições</div><div class='metric-value'>{total_value:.2f} USDT</div></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric'><div class='metric-label'>PNL Total (%)</div><div class='metric-value'>{total_pnl:.2f}%</div></div>", unsafe_allow_html=True)
    else:
        st.info("Nenhuma ordem aberta para exibir estatísticas.")

# Aba: Pesquisa Grok
elif page == "Pesquisa Grok":
    st.markdown("<h1 class='main-title'>Pesquisa Grok</h1>", unsafe_allow_html=True)
    query = st.text_input(
        "Digite sua consulta sobre criptomoedas:",
        placeholder="Ex.: Qual a tendência de XRP/USDT hoje?"
    )
    if st.button("Pesquisar", key="search_grok"):
        with st.spinner("Consultando Grok..."):
            response = query_grok(query)
            st.markdown(f"<div class='insight-card'>{response}</div>", unsafe_allow_html=True)

# Aba: Ordens
elif page == "Ordens":
    st.markdown("<h1 class='main-title'>Ordens</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        date_filter = st.date_input("Filtrar por Data", value=(datetime.now() - timedelta(days=7), datetime.now()))
    with col2:
        direction_filter = st.multiselect("Direção", options=["LONG", "SHORT"], default=["LONG", "SHORT"])
    with col3:
        par_filter = st.multiselect("Par", options=["XRPUSDT", "DOGEUSDT", "TRXUSDT"], default=["XRPUSDT", "DOGEUSDT", "TRXUSDT"])
    col4, col5, col6 = st.columns(3)
    with col4:
        robot_filter = st.multiselect("Nome do Robô", options=strategies.keys(), default=list(strategies.keys()))
    with col5:
        state_filter = st.multiselect("Estado", options=["Aberto", "Fechado", "Todas"], default=["Todas"])
    with col6:
        tp_filter = st.multiselect("TP (%)", options=[0.5, 1.0, 2.0, 3.0, 5.0], default=[0.5, 1.0, 2.0, 3.0, 5.0])
        sl_filter = st.multiselect("SL (%)", options=[0.5, 1.0, 2.0, 3.0, 5.0], default=[0.5, 1.0, 2.0, 3.0, 5.0])
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
    filtered_open = filtered_df[filtered_df['estado'] == 'aberto'].sort_values(by='timestamp', ascending=False)
    st.subheader("Posições Simuladas Abertas (Dry Run)")
    if 'open_orders_page' not in st.session_state:
        st.session_state['open_orders_page'] = 1
    if 'expanded_open_orders' not in st.session_state:
        st.session_state['expanded_open_orders'] = {}
    if not filtered_open.empty:
        open_display = []
        for _, row in filtered_open.iterrows():
            mark_price = get_mark_price(row['par'])
            if mark_price is None:
                continue
            entry_price = float(row['preco_entrada'])
            params = json.loads(row['parametros'])
            tp_percent = params.get('tp_percent', 2.0)
            sl_percent = params.get('sl_percent', 1.0)
            leverage = params.get('leverage', 22)
            direction = row['direcao']
            position_size = float(row['quantity']) * entry_price
            distance_to_tp, distance_to_sl = calculate_distances(entry_price, mark_price, tp_percent, sl_percent, direction)
            liq_price = calculate_liq_price(entry_price, leverage, direction)
            time_open = (datetime.now() - row['timestamp']).total_seconds() / 60
            if direction == "LONG":
                pnl = (mark_price - entry_price) / entry_price * 100
            else:
                pnl = (entry_price - mark_price) / entry_price * 100
            valores_indicadores = json.loads(row['localizadores'])
            resumo = gerar_resumo([row['contributing_indicators']], valores_indicadores)
            win_rate, avg_pnl, total_signals = calcular_confiabilidade_historica(
                row['strategy_name'], row['direcao'], df_closed
            )
            open_display.append({
                "Status": "🟢" if pnl >= 0 else "🔴",
                "Par": row['par'],
                "Direction": row['direcao'],
                "Entry Price": f"{entry_price:.4f}",
                "Mark Price": f"{mark_price:.4f}",
                "Liq. Price": f"{liq_price:.4f}",
                "Distance to TP (%)": f"{distance_to_tp:.2f}",
                "Distance to SL (%)": f"{distance_to_sl:.2f}",
                "PNL (%)": f"{pnl:.2f}",
                "Time (min)": f"{time_open:.1f}",
                "Strategy": row['strategy_name'],
                "Motivos": row['motivos'],
                "Resumo": resumo,
                "Timeframe": row['timeframe'],
                "Quantity": row['quantity'],
                "Historical Win Rate (%)": f"{win_rate:.1f}",
                "Avg PNL (%)": f"{avg_pnl:.2f}",
                "Total Signals": total_signals,
                "Aceito": "Sim" if row['aceito'] else "Não",
                "TP Percent": tp_percent,
                "SL Percent": sl_percent,
                "Quality Score": f"{row['quality_score']:.2f}" if 'quality_score' in row else "N/A",
                "Contributing Indicators": row['contributing_indicators'],
                "Signal ID": row['signal_id']
            })
        if open_display:
            open_df = pd.DataFrame(open_display)
            open_df = open_df[["Status", "Par", "Direction", "Entry Price", "Mark Price", "Liq. Price", "Distance to TP (%)", "Distance to SL (%)", "PNL (%)", "Time (min)", "Strategy", "Motivos", "Resumo", "Timeframe", "Quantity", "Historical Win Rate (%)", "Avg PNL (%)", "Total Signals", "Aceito", "TP Percent", "SL Percent", "Quality Score", "Contributing Indicators", "Signal ID"]]
            page_size = 10
            start_idx = (st.session_state['open_orders_page'] - 1) * page_size
            end_idx = min(start_idx + page_size, len(open_df))
            total_pages = (len(open_df) + page_size - 1) // page_size
            st.markdown("<div class='table-container'>", unsafe_allow_html=True)
            for idx, row in open_df.iloc[start_idx:end_idx].iterrows():
                order_id = row['Signal ID']
                order_key = f"toggle_open_{order_id}"
                is_expanded = st.session_state['expanded_open_orders'].get(order_id, False)
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
                        for other_id in list(st.session_state['expanded_open_orders'].keys()):
                            if other_id != order_id:
                                st.session_state['expanded_open_orders'][other_id] = False
                        st.rerun()
                with col3:
                    if st.button("Fechar Ordem", key=f"close_{order_id}"):
                        close_order_manually(order_id, float(row['Mark Price']))
                        st.rerun()
                if is_expanded:
                    st.markdown(f"""
<div class='strategy-header'>
🟦 [ULTRABOT] SINAL GERADO - {row['Par']} ({row['Timeframe']}) - {row['Direction']} 🟦
</div>
<div class='strategy-section'>
<p><strong>Id da ordem:</strong> {row['Signal ID']}</p>
<p>💰 <strong>Preço de Entrada:</strong> {row['Entry Price']} | <strong>Quantidade:</strong> {row['Quantity']}</p>
<p>🎯 <strong>TP:</strong> <span style='color: green;'>+{row['TP Percent']}%</span> | <strong>SL:</strong> <span style='color: red;'>-{row['SL Percent']}%</span></p>
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
            st.markdown("</div>", unsafe_allow_html=True)
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
            if 'closed_orders_page' not in st.session_state:
                st.session_state['closed_orders_page'] = 1
            if 'expanded_closed_orders' not in st.session_state:
                st.session_state['expanded_closed_orders'] = {}
            page_size = 10
            start_idx = (st.session_state['closed_orders_page'] - 1) * page_size
            end_idx = min(start_idx + page_size, len(closed_df))
            total_pages = (len(closed_df) + page_size - 1) // page_size
            st.markdown("<div class='table-container'>", unsafe_allow_html=True)
            for idx, row in closed_df.iloc[start_idx:end_idx].iterrows():
                order_id = row['Signal ID']
                order_key = f"toggle_closed_{order_id}_{idx}"
                is_expanded = st.session_state['expanded_closed_orders'].get(order_id, False)
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
                        for other_id in list(st.session_state['expanded_closed_orders'].keys()):
                            if other_id != order_id:
                                st.session_state['expanded_closed_orders'][other_id] = False
                        st.rerun()
                if is_expanded:
                    st.markdown(f"""
<div class='strategy-header'>
🟦 [ULTRABOT] SINAL GERADO - {row['Par']} ({row['Timeframe']}) - {row['Direction']} 🟦
</div>
<div class='strategy-section'>
<p><strong>Id da ordem:</strong> {row['Signal ID']}</p>
<p>💰 <strong>Preço de Entrada:</strong> {row['Entry Price']} | <strong>Quantidade:</strong> {row['Quantity']}</p>
<p>🎯 <strong>TP:</strong> <span style='color: green;'>+{row['TP Percent']}%</span> | <strong>SL:</strong> <span style='color: red;'>-{row['SL Percent']}%</span></p>
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
            st.markdown("</div>", unsafe_allow_html=True)
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
        if 'signals_page' not in st.session_state:
            st.session_state['signals_page'] = 1
        page_size = 10
        start_idx = (st.session_state['signals_page'] - 1) * page_size
        end_idx = min(start_idx + page_size, len(signals_df))
        total_pages = (len(signals_df) + page_size - 1) // page_size
        st.markdown("<div class='table-container'>", unsafe_allow_html=True)
        st.table(signals_df.iloc[start_idx:end_idx])
        st.markdown("</div>", unsafe_allow_html=True)
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
    st.header("Alertas e Notificações")
    alerts = []
    for signal_id in new_orders:
        order = df_open[df_open['signal_id'] == signal_id].iloc[0]
        alerts.append(f"🔔 {order['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} - Robô {order['strategy_name']}: Nova ordem aberta: {signal_id} ({order['par']}) - {order['direcao']}")
    alerts.extend(check_alerts(filtered_open))
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
                        st.markdown(f"<div class='notification notification-warning'>{alert}</div>", unsafe_allow_html=True)
                    elif "⚠️" in alert:
                        st.markdown(f"<div class='notification notification-error'>{alert}</div>", unsafe_allow_html=True)
                    elif "🔔" in alert:
                        st.markdown(f"<div class='notification notification-success'>{alert}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='notification notification-success'>{alert}</div>", unsafe_allow_html=True)
    else:
        st.info("Nenhum alerta ou notificação no momento.")

# Aba: Configurações de Estratégia
elif page == "Configurações de Estratégia":
    st.markdown("<h1 class='main-title'>Configurações de Estratégia</h1>", unsafe_allow_html=True)
    st.info("Configure os parâmetros das estratégias de trading.")
    indicadores_simples = [
        "SMA", "EMA", "RSI", "MACD", "ADX", "Volume", "Bollinger",
        "Estocastico", "VWAP", "OBV", "Fibonacci", "Sentimento"
    ]
    indicadores_compostos = [
        "Swing Trade Composite"
    ]
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
    st.subheader("Timeframes")
    config["timeframes"] = st.multiselect(
        "Selecione os Timeframes",
        options=["1m", "5m", "15m", "1h", "4h", "1d"],
        default=config.get("timeframes", ["1m", "5m", "15m", "1h", "4h", "1d"])
    )
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

# ... (código anterior até o início da aba "Oportunidades Perdidas")

# Aba: Oportunidades Perdidas
elif page == "Oportunidades Perdidas":
    st.markdown("<h1 class='main-title'>Oportunidades Perdidas</h1>", unsafe_allow_html=True)
    st.info("Visualize os sinais que foram rejeitados devido a limites de ordens ou outros critérios.")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        missed_date_filter = st.date_input(
            "Filtrar por Data",
            value=(datetime.now() - timedelta(days=7), datetime.now()),
            key="missed_date_filter"
        )
    with col2:
        missed_robot_filter = st.multiselect(
            "Nome do Robô",
            options=df_missed['robot_name'].unique(),
            default=df_missed['robot_name'].unique(),
            key="missed_robot_filter"
        )
    with col3:
        missed_pair_filter = st.multiselect(
            "Par",
            options=["XRPUSDT", "DOGEUSDT", "TRXUSDT"],
            default=["XRPUSDT", "DOGEUSDT", "TRXUSDT"],
            key="missed_pair_filter"
        )
    
    # Filtrar dados
    filtered_missed = df_missed[
        (df_missed['timestamp'].dt.date >= missed_date_filter[0]) &
        (df_missed['timestamp'].dt.date <= missed_date_filter[1]) &
        (df_missed['robot_name'].isin(missed_robot_filter)) &
        (df_missed['par'].isin(missed_pair_filter))
    ].sort_values(by='timestamp', ascending=False)
    
    # Exibir tabela
    st.markdown("<h2 class='section-title'>Oportunidades Perdidas</h2>", unsafe_allow_html=True)
    if not filtered_missed.empty:
        display_missed = filtered_missed[[
            'timestamp', 'robot_name', 'par', 'timeframe', 'direcao',
            'score_tecnico', 'contributing_indicators', 'reason'
        ]].rename(columns={
            'timestamp': 'Data/Hora',
            'robot_name': 'Robô',
            'par': 'Par',
            'timeframe': 'Timeframe',
            'direcao': 'Direção',
            'score_tecnico': 'Score Técnico',
            'contributing_indicators': 'Indicadores',
            'reason': 'Motivo'
        })
        
        # Paginação
        if 'missed_opportunities_page' not in st.session_state:
            st.session_state['missed_opportunities_page'] = 1
        page_size = 10
        start_idx = (st.session_state['missed_opportunities_page'] - 1) * page_size
        end_idx = min(start_idx + page_size, len(display_missed))
        total_pages = (len(display_missed) + page_size - 1) // page_size
        
        st.markdown("<div class='table-container'>", unsafe_allow_html=True)
        st.table(display_missed.iloc[start_idx:end_idx])
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Controles de paginação
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
    else:
        st.info("Nenhuma oportunidade perdida corresponde aos filtros selecionados.")
    
    # Gráfico de motivos mais comuns
    st.markdown("<h2 class='section-title'>Motivos Mais Comuns</h2>", unsafe_allow_html=True)
    if not filtered_missed.empty:
        reason_counts = filtered_missed['reason'].value_counts().reset_index()
        reason_counts.columns = ['Motivo', 'Contagem']
        fig = px.bar(
            reason_counts,
            x='Motivo',
            y='Contagem',
            title="Distribuição dos Motivos de Rejeição",
            height=400
        )
        fig.update_layout(
            template="plotly_dark",
            plot_bgcolor="#1a1a1a",
            paper_bgcolor="#1a1a1a",
            font=dict(family="Inter", color="#d1d5db"),
            title_font=dict(size=20, color="#ffffff")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nenhum dado disponível para o gráfico.")

# Aba: Ordens Binance
elif page == "Ordens Binance":
    st.markdown("<h1 class='main-title'>Ordens Binance</h1>", unsafe_allow_html=True)
    st.info("Visualize ordens reais executadas na Binance (fora do modo Dry Run).")
    
    try:
        # Obter ordens abertas
        open_orders = client.get_open_orders()
        open_orders_df = pd.DataFrame(open_orders)
        
        # Obter histórico de ordens (últimos 7 dias)
        all_orders = []
        for symbol in ["XRPUSDT", "DOGEUSDT", "TRXUSDT"]:
            orders = client.get_all_orders(symbol=symbol, limit=100)
            all_orders.extend(orders)
        orders_df = pd.DataFrame(all_orders)
        
        # Filtrar ordens dos últimos 7 dias
        if not orders_df.empty:
            orders_df['time'] = pd.to_datetime(orders_df['time'], unit='ms')
            orders_df = orders_df[orders_df['time'] >= datetime.now() - timedelta(days=7)]
        
        # Exibir ordens abertas
        st.markdown("<h2 class='section-title'>Ordens Abertas</h2>", unsafe_allow_html=True)
        if not open_orders_df.empty:
            display_open = open_orders_df[[
                'symbol', 'side', 'price', 'origQty', 'status', 'time'
            ]].rename(columns={
                'symbol': 'Par',
                'side': 'Direção',
                'price': 'Preço',
                'origQty': 'Quantidade',
                'status': 'Status',
                'time': 'Data/Hora'
            })
            st.markdown("<div class='table-container'>", unsafe_allow_html=True)
            st.table(display_open)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Nenhuma ordem aberta na Binance.")
        
        # Exibir histórico de ordens
        st.markdown("<h2 class='section-title'>Histórico de Ordens</h2>", unsafe_allow_html=True)
        if not orders_df.empty:
            display_closed = orders_df[[
                'symbol', 'side', 'price', 'origQty', 'status', 'time'
            ]].rename(columns={
                'symbol': 'Par',
                'side': 'Direção',
                'price': 'Preço',
                'origQty': 'Quantidade',
                'status': 'Status',
                'time': 'Data/Hora'
            })
            # Paginação
            if 'binance_orders_page' not in st.session_state:
                st.session_state['binance_orders_page'] = 1
            page_size = 10
            start_idx = (st.session_state['binance_orders_page'] - 1) * page_size
            end_idx = min(start_idx + page_size, len(display_closed))
            total_pages = (len(display_closed) + page_size - 1) // page_size
            
            st.markdown("<div class='table-container'>", unsafe_allow_html=True)
            st.table(display_closed.iloc[start_idx:end_idx])
            st.markdown("</div>", unsafe_allow_html=True)
            
            if total_pages > 1:
                col_prev, col_next = st.columns(2)
                with col_prev:
                    if st.session_state['binance_orders_page'] > 1:
                        if st.button("Carregar Anteriores", key="prev_binance"):
                            st.session_state['binance_orders_page'] -= 1
                            st.rerun()
                with col_next:
                    if st.session_state['binance_orders_page'] < total_pages:
                        if st.button("Carregar Mais", key="next_binance"):
                            st.session_state['binance_orders_page'] += 1
                            st.rerun()
        else:
            st.info("Nenhuma ordem encontrada no histórico da Binance.")
    
    except BinanceAPIException as e:
        st.error(f"Erro na API Binance: {e.message}")
        add_notification(
            message=f"Erro na API Binance: {e.message}",
            notification_type="ERROR",
            source="Ordens Binance"
        )
    except Exception as e:
        st.error(f"Erro inesperado: {e}")
        add_notification(
            message=f"Erro inesperado ao carregar ordens Binance: {e}",
            notification_type="ERROR",
            source="Ordens Binance"
        )

# Aba: Meus Robôs
elif page == "Meus Robôs":
    st.markdown("<h1 class='main-title'>Meus Robôs</h1>", unsafe_allow_html=True)
    st.info("Gerencie seus robôs de trading e visualize seu desempenho.")
    
    # Cards de robôs
    st.markdown("<h2 class='section-title'>Status dos Robôs</h2>", unsafe_allow_html=True)
    cols = st.columns(3)
    for idx, (strategy_name, is_active) in enumerate(robot_status.items()):
        with cols[idx % 3]:
            robot_orders = df[df['strategy_name'] == strategy_name]
            robot_closed = df_closed[df_closed['strategy_name'] == strategy_name]
            total_orders = len(robot_closed)
            wins = len(robot_closed[robot_closed['pnl_realizado'] >= 0])
            win_rate = (wins / total_orders * 100) if total_orders > 0 else 0
            total_pnl = robot_closed['pnl_realizado'].sum() if total_orders > 0 else 0
            
            status_color = "#28a745" if is_active else "#dc3545"
            status_text = "Ativado" if is_active else "Desativado"
            alert = "📈" if total_pnl > 5 else "⚠️" if total_pnl < -5 else ""
            
            st.markdown(
                f"""
                <div class='robot-card'>
                    <div class='robot-header' style='background-color: {status_color}'>
                        <h3>{strategy_name} 🤖</h3>
                        <p>{status_text}</p>
                    </div>
                    <div class='robot-body'>
                        <p><i class='fas fa-chart-line'></i> Taxa de Vitória: {win_rate:.2f}%</p>
                        <p><i class='fas fa-coins'></i> PNL Total: {total_pnl:.2f}% {alert}</p>
                        <p><i class='fas fa-list'></i> Total de Ordens: {total_orders}</p>
                    </div>
                    <div class='robot-footer'>
                """,
                unsafe_allow_html=True
            )
            
            # Botão de ligar/desligar com loader
            button_key = f"toggle_{strategy_name}_{idx}"
            if st.button(
                "Desligar" if is_active else "Ligar",
                key=button_key,
                help=f"{'Desligar' if is_active else 'Ligar'} o robô {strategy_name}"
            ):
                with st.spinner("Atualizando status..."):
                    robot_status[strategy_name] = not is_active
                    save_robot_status(robot_status)
                    action = "desligado" if is_active else "ligado"
                    st.success(f"Robô {strategy_name} {action} com sucesso!")
                    add_notification(
                        message=f"Robô {strategy_name} {action} com sucesso",
                        notification_type="SUCCESS",
                        source=strategy_name
                    )
                    st.rerun()
            
            st.markdown("</div></div>", unsafe_allow_html=True)
    
    # Reset do sistema
    st.markdown("<h2 class='section-title'>Reset do Sistema</h2>", unsafe_allow_html=True)
    with st.expander("Resetar Todos os Dados"):
        reset_password = st.text_input("Digite a senha para reset", type="password")
        if st.button("Resetar Sistema"):
            success, message = reset_bot_data(reset_password)
            if success:
                st.success(message)
                add_notification(
                    message="Sistema resetado com sucesso",
                    notification_type="SUCCESS",
                    source="Sistema"
                )
                st.rerun()
            else:
                st.error(message)
                add_notification(
                    message=message,
                    notification_type="ERROR",
                    source="Sistema"
                )

# Aba: ML Machine
elif page == "ML Machine":
    st.markdown("<h1 class='main-title'>ML Machine</h1>", unsafe_allow_html=True)
    st.info("Visualize o desempenho do modelo de Machine Learning e ajuste os parâmetros.")
    
    # Métricas do modelo
    st.markdown("<h2 class='section-title'>Métricas do Modelo</h2>", unsafe_allow_html=True)
    try:
        metrics = learning_engine.get_metrics()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                f"<div class='metric'><div class='metric-label'>Acurácia</div><div class='metric-value'>{metrics.get('accuracy', 0):.2%}</div></div>",
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(
                f"<div class='metric'><div class='metric-label'>Precisão</div><div class='metric-value'>{metrics.get('precision', 0):.2%}</div></div>",
                unsafe_allow_html=True
            )
        with col3:
            st.markdown(
                f"<div class='metric'><div class='metric-label'>Recall</div><div class='metric-value'>{metrics.get('recall', 0):.2%}</div></div>",
                unsafe_allow_html=True
            )
        
        # Gráfico de importância das features
        st.markdown("<h2 class='section-title'>Importância das Features</h2>", unsafe_allow_html=True)
        feature_importance = learning_engine.get_feature_importance()
        if feature_importance:
            fig = px.bar(
                x=feature_importance['importance'],
                y=feature_importance['feature'],
                orientation='h',
                title="Importância das Features no Modelo",
                height=400
            )
            fig.update_layout(
                template="plotly_dark",
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font=dict(family="Inter", color="#d1d5db"),
                title_font=dict(size=20, color="#ffffff")
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma informação de importância das features disponível.")
    
    except Exception as e:
        st.error(f"Erro ao carregar métricas do modelo: {e}")
        add_notification(
            message=f"Erro ao carregar métricas do modelo: {e}",
            notification_type="ERROR",
            source="ML Machine"
        )
    
    # Treinamento do modelo
    st.markdown("<h2 class='section-title'>Treinar Modelo</h2>", unsafe_allow_html=True)
    if st.button("Treinar Modelo Agora"):
        with st.spinner("Treinando modelo..."):
            try:
                learning_engine.train()
                st.success("Modelo treinado com sucesso!")
                add_notification(
                    message="Modelo de Machine Learning treinado com sucesso",
                    notification_type="SUCCESS",
                    source="ML Machine"
                )
            except Exception as e:
                st.error(f"Erro ao treinar modelo: {e}")
                add_notification(
                    message=f"Erro ao treinar modelo: {e}",
                    notification_type="ERROR",
                    source="ML Machine"
                )
                st.rerun()
    
    # Ajuste de hiperparâmetros
    st.markdown("<h2 class='section-title'>Hiperparâmetros</h2>", unsafe_allow_html=True)
    with st.expander("Ajustar Hiperparâmetros"):
        n_estimators = st.number_input(
            "Número de Árvores (n_estimators)",
            min_value=10,
            max_value=1000,
            value=100,
            step=10
        )
        max_depth = st.number_input(
            "Profundidade Máxima",
            min_value=1,
            max_value=100,
            value=10,
            step=1
        )
        if st.button("Aplicar Hiperparâmetros"):
            try:
                learning_engine.set_hyperparameters(
                    n_estimators=n_estimators,
                    max_depth=max_depth
                )
                st.success("Hiperparâmetros atualizados com sucesso!")
                add_notification(
                    message="Hiperparâmetros do modelo atualizados",
                    notification_type="SUCCESS",
                    source="ML Machine"
                )
            except Exception as e:
                st.error(f"Erro ao atualizar hiperparâmetros: {e}")
                add_notification(
                    message=f"Erro ao atualizar hiperparâmetros: {e}",
                    notification_type="ERROR",
                    source="ML Machine"
                )

# Notificações globais
st.markdown("<h2 class='section-title'>Notificações Recentes</h2>", unsafe_allow_html=True)
notifications = get_notifications(max_age_days=7, only_unread=False)
if notifications:
    for notification in notifications[:5]:
        n_type = notification.get('type', 'INFO')
        icon = NOTIFICATION_TYPES.get(n_type, NOTIFICATION_TYPES['INFO'])['icon']
        color = NOTIFICATION_TYPES.get(n_type, NOTIFICATION_TYPES['INFO'])['color']
        count = notification.get('count', 1)
        message = f"{icon} {notification['message']}"
        if count > 1:
            message += f" (x{count})"
        st.markdown(
            f"<div class='notification' style='background-color: {color};'>{message}</div>",
            unsafe_allow_html=True
        )
        if notification.get('details'):
            with st.expander("Detalhes"):
                st.write(notification['details'])
else:
    st.info("Nenhuma notificação recente.")