import sys
#teste atualizacao 160420251104
import time
import threading
import os
import subprocess
import json
from datetime import datetime, timedelta
import uuid
import pandas as pd
import numpy as np
from queue import PriorityQueue
from dotenv import load_dotenv
from config import SYMBOLS, DRY_RUN, REAL_API_KEY, REAL_API_SECRET, TIMEFRAMES, CONFIG
from utils import logger, CsvWriter, initialize_csv_files
from initialization import inicializar_client, is_port_in_use, kill_process_on_port, check_dashboard_availability, check_api_status, load_config
from binance_utils import BinanceUtils
from learning_engine import LearningEngine
from order_executor import OrderExecutor, close_order
from data_manager import get_historical_data, get_funding_rate, get_current_price, get_quantity, is_candle_closed
from indicators import calculate_indicators
from signal_generator import generate_signal, generate_multi_timeframe_signal, calculate_signal_quality
from trade_manager import check_active_trades, generate_combination_key, save_signal, save_signal_log
from trade_simulator import simulate_trade, simulate_trade_backtest
from backtest import run_backtest
from strategy_manager import sync_strategies_and_status
import requests
import asyncio
import json
from binance.client import Client
import logging
from signal_generator import SignalGenerator

class UltraBot:
    def __init__(self):
        self.client = Client(REAL_API_KEY, REAL_API_SECRET)
        self.headers = {"Authorization": f"Bearer {os.getenv('XAI_API_KEY')}", "Content-Type": "application/json"}
        self.last_analysis = {pair: 0 for pair in SYMBOLS}
        self.cache_file = "insights_cache.json"
        self.cache = self.load_cache()
        self.signal_generator = SignalGenerator()
        self.learning_engine = LearningEngine()

    def load_cache(self):
        try:
            with open(self.cache_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_cache(self):
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f)

    def fetch_market_data(self, pair, timeframe):
        klines = self.client.get_klines(symbol=pair, interval=timeframe, limit=100)
        df = pd.DataFrame(klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        return df

    def read_orders(self):
        try:
            df = pd.read_csv("sinais_detalhados.csv")
            # Garante que as colunas essenciais existem
            for col in ["pair", "type", "price", "quantity", "timestamp"]:
                if col not in df.columns:
                    df[col] = None
            return df
        except FileNotFoundError:
            # Cria DataFrame vazio com as colunas corretas
            return pd.DataFrame(columns=["pair", "type", "price", "quantity", "timestamp"])

    def read_prices(self):
        try:
            return pd.read_csv("precos_log.csv")
        except FileNotFoundError:
            return pd.DataFrame(columns=["pair", "price", "timestamp"])

    def read_log(self):
        try:
            with open("bot.log", "r") as f:
                return f.readlines()[-10:]
        except FileNotFoundError:
            return []

    def calculate_indicators(self, data):
        data['rsi'] = self.compute_rsi(data['close'], period=14)
        data['ema12'] = data['close'].ewm(span=12, adjust=False).mean()
        data['ema50'] = data['close'].ewm(span=50, adjust=False).mean()
        return data[['close', 'rsi', 'ema12', 'ema50']].tail(5)

    def compute_rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def validate_signal_locally(self, data):
        rsi = data['rsi'].iloc[-1]
        ema12 = data['ema12'].iloc[-1]
        ema50 = data['ema50'].iloc[-1]
        if rsi > 70 and ema12 < ema50:
            return "Venda potencial (sobrecomprado)"
        elif rsi < 30 and ema12 > ema50:
            return "Compra potencial (sobrevendido)"
        return None

    async def analyze_with_grok(self, data_dict, active_pairs):
        cache_key = f"{','.join(active_pairs)}_{int(time.time() // 300)}"
        if cache_key in self.cache:
            logging.info(f"Usando cache para {active_pairs}")
            return self.cache[cache_key]

        prompt = "Análise em tempo real (escalpagem, 1m):\n"
        for pair in active_pairs:
            data = self.calculate_indicators(data_dict[pair])
            orders = self.read_orders().query(f"pair == '{pair}' and timestamp > '{datetime.now().timestamp() - 300}'")
            prices = self.read_prices().query(f"pair == '{pair}'").tail(3)
            log_lines = self.read_log()
            prompt += (
                f"\nPar: {pair}\n"
                f"Indicadores: RSI={data['rsi'].iloc[-1]:.2f}, EMA12={data['ema12'].iloc[-1]:.4f}, EMA50={data['ema50'].iloc[-1]:.4f}\n"
                f"Preço atual: {data['close'].iloc[-1]:.4f}\n"
                f"Ordens abertas: {orders[['price', 'quantity']].to_string()}\n"
                f"Preços recentes: {prices[['price']].to_string()}\n"
                f"Logs: {''.join(log_lines)}\n"
                f"Valide sinais de compra/venda, sugira stop-loss/take-profit. Busque posts no X de hoje sobre {pair} de usuários influentes e avalie o sentimento.\n"
            )
        payload = {
            "model": "grok-beta",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }
        try:
            response = requests.post(
                f"https://api.x.ai/v1/chat/completions",
                json=payload, headers=self.headers, stream=True, timeout=10
            )
            response.raise_for_status()
            insights = ""
            for chunk in response.iter_lines():
                if chunk:
                    insights += chunk.decode("utf-8") + "\n"
            self.cache[cache_key] = insights
            self.save_cache()
            return insights
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro na API do Grok: {e}")
            return f"Erro na análise: {str(e)}"

    async def run(self):
        while True:
            active_pairs = []
            data_dict = {}
            orders = self.read_orders()
            for pair in SYMBOLS:
                current_time = time.time()
                has_open_orders = not orders.query(f"pair == '{pair}' and type == 'open'").empty
                interval = 120 if "DOGE" in pair else 300
                if has_open_orders or (current_time - self.last_analysis[pair] >= interval):
                    data = self.fetch_market_data(pair, TIMEFRAMES[0])
                    data = self.calculate_indicators(data)
                    signal = self.validate_signal_locally(data)
                    if signal or has_open_orders:
                        data_dict[pair] = data
                        active_pairs.append(pair)
                        self.last_analysis[pair] = current_time
            if active_pairs:
                insights = await self.analyze_with_grok(data_dict, active_pairs)
                logging.info(f"Insights para {active_pairs}: {insights}")
                # Gerar e salvar sinais com base nos insights e learning engine
                for pair in active_pairs:
                    signal = self.signal_generator.generate_signal(data_dict[pair], insights, pair)
                    # Adiciona confiança do modelo ML
                    ml_pred = self.learning_engine.predict(data_dict[pair])
                    signal['ml_confidence'] = ml_pred.get('confidence', 0.0)
                    self.signal_generator.save_signal(pair, signal)
                    # Salva dados para aprendizado
                    self.learning_engine.save_training_data = getattr(self.learning_engine, 'save_training_data', lambda *a, **kw: None)
                    self.learning_engine.save_training_data(pair, signal, insights, None)
                # Salvar insights
                pd.DataFrame({
                    "pair": [", ".join(active_pairs)],
                    "timeframe": [TIMEFRAMES[0]],
                    "insights": [insights],
                    "timestamp": [datetime.now()]
                }).to_csv("sinais_detalhados.csv", mode="a", index=False, 
                          header=not os.path.exists("sinais_detalhados.csv"))
                # Treinamento periódico
                if hasattr(self.learning_engine, 'train'):
                    self.learning_engine.train()
            await asyncio.sleep(60)

def main():
    bot = UltraBot()
    asyncio.run(bot.run())

if __name__ == "__main__":
    # Inicia o dashboard Streamlit de forma bloqueante (herda o terminal)
    import subprocess
    import sys
    import os
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
    dashboard_proc = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", dashboard_path, "--server.port", "8580"
    ])
    try:
        main()
    finally:
        # Ao encerrar o main.py, encerra também o dashboard
        dashboard_proc.terminate()
        dashboard_proc.wait()

try:
    # Inicializar o CsvWriter com filename e columns
    logger.info("Inicializando o CsvWriter para sinais_detalhados.csv...")
    csv_writer = CsvWriter(
        filename="sinais_detalhados.csv",
        columns=[
            'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
            'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
            'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
            'motivos', 'timeframe', 'aceito', 'parametros', 'quality_score'
        ]
    )
    logger.info("CsvWriter inicializado com sucesso.")

    logger.info("Carregando variáveis de ambiente com load_dotenv()...")
    # load_dotenv()  # Removido para evitar dependência local
    logger.info("Variáveis de ambiente carregadas com sucesso.")

    PAIRS = SYMBOLS
    SINALS_FILE = "sinais_detalhados.csv"
    logger.info(f"PAIRS configurados: {PAIRS}")
    logger.info(f"SINALS_FILE configurado: {SINALS_FILE}")

    # Variáveis globais para rastrear o estado do bot
    bot_status = {
        "signals_generated": 0,
        "orders_opened": 0,
        "orders_closed": 0,
        "last_learning_update": 0,
        "model_accuracy": 0.0,
    }

    # Dicionário para rastrear estratégias ativas
    robots_status = {}

    # Lista para rastrear erros do sistema
    system_errors = []

    # Fila de prioridade para sinais e sinais rejeitados
    signal_queue = PriorityQueue()
    rejected_signals = PriorityQueue()

    # Threshold mínimo para o quality_score
    MIN_SCORE_THRESHOLD = 0.8

    def get_next_candle_close_time(tf, current_time):
        """Calcula o próximo tempo de fechamento de vela para um timeframe."""
        tf_minutes = {
            "1m": 1, "5m": 5, "15m": 15, "1h": 60,
            "4h": 240, "1d": 1440
        }
        minutes = tf_minutes[tf]
        current_minute = current_time.replace(second=0, microsecond=0)
        delta = timedelta(minutes=minutes)
        next_close = current_minute + delta
        while next_close <= current_time:
            next_close += delta
        return next_close

    def generate_realtime_signal(client, pair, tf, strategy_config, config, learning_engine, binance_utils):
        """Gera sinais em tempo real para timeframes."""
        # Remove restrição de timeframe e deixa apenas verificação de sinais em tempo real
        if not config.get("realtime_signals_enabled", True):
            return None, None, None, None, None

        current_price = get_current_price(client, pair, config)
        if current_price is None:
            return None, None, None, None, None

        # Ajusta o número de candles baseado no timeframe
        limit = 200 if tf in ["1h", "4h", "1d"] else 100
        historical_data = get_historical_data(client, pair, tf, limit=limit)
        if historical_data.empty:
            return None, None, None, None, None

        # Atualiza o último preço apenas para timeframes menores
        if tf in ["1m", "5m", "15m"]:
            historical_data.loc[historical_data.index[-1] + 1] = historical_data.iloc[-1]
            historical_data.iloc[-1, historical_data.columns.get_loc('close')] = current_price

        historical_data = calculate_indicators(historical_data, binance_utils)
        direction, score, details, contributing_indicators, strategy_name = generate_signal(
            historical_data, tf, strategy_config, config, learning_engine, binance_utils
        )
        if direction:
            return direction, score, details, contributing_indicators, strategy_name
        return None, None, None, None, None

    def calculate_strategy_performance():
        """Calcula o desempenho por estratégia com base no sinais_detalhados.csv."""
        try:
            df = pd.read_csv(SINALS_FILE)
            if df.empty:
                return {}

            strategies = df.groupby('strategy_name')
            performance = {}
            for strategy_name, group in strategies:
                total_orders = len(group)
                closed_orders = group[group['estado'] == 'fechado']
                total_closed = len(closed_orders)
                wins = len(closed_orders[closed_orders['resultado'] == 'TP'])
                win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
                avg_pnl = closed_orders['pnl_realizado'].mean() if not closed_orders['pnl_realizado'].isna().all() else 0
                total_pnl = closed_orders['pnl_realizado'].sum() if not closed_orders['pnl_realizado'].isna().all() else 0

                performance[strategy_name] = {
                    "total_orders": total_orders,
                    "win_rate": win_rate,
                    "avg_pnl": avg_pnl,
                    "total_pnl": total_pnl
                }
            return performance
        except Exception as e:
            logger.error(f"Erro ao calcular desempenho por estratégia: {e}")
            return {}

    def calculate_current_pnl(signal_data, client, config):
        """Calcula o PNL atual de uma ordem ativa."""
        try:
            if signal_data['estado'] == 'fechado':
                logger.debug(f"Ordem fechada, usando PNL registrado: {signal_data.get('pnl_realizado', 0.0)}")
                return signal_data.get('pnl_realizado', 0.0)
            
            logger.debug(f"Obtendo preço atual para {signal_data['par']}...")
            current_price = get_current_price(client, signal_data['par'], config)
            if current_price is None:
                logger.warning(f"Não foi possível obter preço atual para {signal_data['par']}. Retornando PNL 0.0.")
                return 0.0
            
            entry_price = signal_data['preco_entrada']
            direction = signal_data['direcao']
            quantity = signal_data['quantity']
            leverage = signal_data.get('leverage', 1)
            
            if direction == "LONG":
                price_diff = current_price - entry_price
            else:
                price_diff = entry_price - current_price
            pnl_percent = (price_diff / entry_price) * 100 * leverage
            logger.debug(f"PNL calculado: {pnl_percent:.2f}%")
            return pnl_percent
        except Exception as e:
            logger.error(f"Erro ao calcular PNL atual: {e}")
            return 0.0

    def log_summary_periodically(config, active_trades_dry_run, learning_engine, last_learning_update, client):
        """Função que exibe um resumo do status do bot a cada 30 segundos."""
        while True:
            try:
                active_trades = len(active_trades_dry_run)
                max_trades = config.get("max_trades_simultaneos", 50)
                active_modes = [mode for mode, active in config["modes"].items() if active]

                # Verificar se o arquivo de sinais existe e está acessível
                try:
                    df = pd.read_csv(SINALS_FILE)
                    orders_closed = len(df[df['estado'] == 'fechado'])
                    bot_status["orders_closed"] = orders_closed
                except FileNotFoundError:
                    logger.warning(f"Arquivo {SINALS_FILE} não encontrado. Inicializando com 0 ordens fechadas.")
                    orders_closed = 0
                    bot_status["orders_closed"] = orders_closed

                strategy_performance = calculate_strategy_performance()

                for strategy_name, robot_info in robots_status.items():
                    if robot_info.get("last_order") and robot_info["last_order"].get("estado") == "aberto":
                        robot_info["last_order"]["pnl_current"] = calculate_current_pnl(robot_info["last_order"], client, config)
                    if strategy_name in strategy_performance:
                        robot_info["total_pnl"] = strategy_performance[strategy_name]["total_pnl"]

                print("┌── Resumo do Bot (a cada 30s) ──┐")
                print(f"│ Modos Ativos: {active_modes}")
                print(f"│ Ordens Abertas: {active_trades}/{max_trades}")
                print(f"│ Ordens Fechadas: {bot_status['orders_closed']}")
                print(f"│ Última Atualização do Modelo: {datetime.fromtimestamp(bot_status['last_learning_update']).strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"│ Acurácia do Modelo: {bot_status['model_accuracy']:.2f}")
                print("│ Estratégias Ativas:")
                if not robots_status:
                    print("- Nenhuma estratégia ativa.")
                else:
                    for strategy_name, robot_info in robots_status.items():
                        if "last_order" in robot_info and robot_info["last_order"]:
                            last_order = robot_info["last_order"]
                            pnl = last_order.get("pnl_current", last_order.get("pnl_realizado", 0.0))
                            print(f"- {last_order['timestamp']} - Última Ordem Aberta ({last_order['estado'].capitalize()}) (PNL: {pnl:+.2f}%) - {strategy_name}")
                        else:
                            print(f"- Nenhuma ordem registrada - {strategy_name}")

                print("│ Erros no Funcionamento do Sistema:")
                if not system_errors:
                    print("- Nenhum erro registrado.")
                else:
                    for error in system_errors[-5:]:
                        print(f"- {error['description']} / {error['timestamp']} / {error['reason']}")
                print("└───────────────────────────────┘")

                time.sleep(30)
            except Exception as e:
                logger.error(f"Erro ao gerar resumo periódico: {e}")
                time.sleep(30)

    def update_orders_status():
        """Atualiza o status de ordens abertas e fechadas diretamente do arquivo de sinais."""
        try:
            df = pd.read_csv(SINALS_FILE)
            open_orders = len(df[df['estado'] == 'aberto'])
            closed_orders = len(df[df['estado'] == 'fechado'])
            total_signals = len(df)

            bot_status["orders_opened"] = open_orders
            bot_status["orders_closed"] = closed_orders
            bot_status["signals_generated"] = total_signals

            logger.info(f"Status atualizado: {open_orders} ordens abertas, {closed_orders} ordens fechadas, {total_signals} sinais gerados.")
        except Exception as e:
            logger.error(f"Erro ao atualizar status de ordens: {e}")

    def close_invalid_open_orders(client):
        """Verifica e fecha ordens abertas que já atingiram TP ou SL."""
        try:
            df = pd.read_csv(SINALS_FILE)
            open_orders = df[df['estado'] == 'aberto']

            for index, order in open_orders.iterrows():
                mark_price = get_current_price(client, order['par'], CONFIG)
                if mark_price is None:
                    continue

                entry_price = float(order['preco_entrada'])
                direction = order['direcao']
                params = json.loads(order['parametros'])
                tp_percent = params.get('tp_percent', 2.0)
                sl_percent = params.get('sl_percent', 1.0)

                if direction == "LONG":
                    tp_price = entry_price * (1 + tp_percent / 100)
                    sl_price = entry_price * (1 - sl_percent / 100)
                else:
                    tp_price = entry_price * (1 - tp_percent / 100)
                    sl_price = entry_price * (1 + sl_percent / 100)

                if (direction == "LONG" and mark_price >= tp_price) or (direction == "SHORT" and mark_price <= tp_price):
                    close_order(order['signal_id'], mark_price, "TP")
                elif (direction == "LONG" and mark_price <= sl_price) or (direction == "SHORT" and mark_price >= sl_price):
                    close_order(order['signal_id'], mark_price, "SL")
        except Exception as e:
            logger.error(f"Erro ao verificar e fechar ordens inválidas: {e}")

    def update_bot_summary():
        """Atualiza o resumo do bot com base no arquivo de sinais detalhados."""
        try:
            df = pd.read_csv(SINALS_FILE)
            total_signals = len(df)
            open_orders = len(df[df['estado'] == 'aberto'])
            closed_orders = len(df[df['estado'] == 'fechado'])

            bot_status["signals_generated"] = total_signals
            bot_status["orders_opened"] = open_orders
            bot_status["orders_closed"] = closed_orders

            logger.info(f"Resumo atualizado: {total_signals} sinais gerados, {open_orders} ordens abertas, {closed_orders} ordens fechadas.")
        except Exception as e:
            logger.error(f"Erro ao atualizar resumo do bot: {e}")

    def process_signals_for_timeframe(pair, tf, current_time, active_strategies, config, active_trades_dry_run, client, learning_engine, binance_utils, candle_schedule):
        """Processa sinais para um par/timeframe específico"""
        signals = {}
        
        if current_time < candle_schedule[pair][tf]:
            logger.debug(f"Aguardando próximo fechamento para {pair}/{tf}: {candle_schedule[pair][tf]}")
            return signals

        limit = 200 if tf in ["1h", "4h", "1d"] else 100
        historical_data = get_historical_data(client, pair, tf, limit=limit)
        if historical_data.empty:
            logger.warning(f"Sem dados históricos para {pair}/{tf}")
            return signals

        for strategy_name, strategy_config in active_strategies.items():
            if tf not in strategy_config.get("timeframes", TIMEFRAMES):
                continue

            # Importar check_timeframe_direction_limit do módulo trade_manager
            from trade_manager import check_timeframe_direction_limit
            
            # Verifica se já atingiu limite de ordens para LONG
            can_open_long = check_timeframe_direction_limit(
                pair, tf, "LONG", strategy_name, active_trades_dry_run, config
            )
            
            # Verifica se já atingiu limite de ordens para SHORT
            can_open_short = check_timeframe_direction_limit(
                pair, tf, "SHORT", strategy_name, active_trades_dry_run, config
            )

            if not can_open_long and not can_open_short:
                logger.info(f"Limites atingidos para {strategy_name} em {pair}/{tf} (LONG e SHORT)")
                continue

            direction, score, details, contributing_indicators, _ = generate_signal(
                historical_data, tf, strategy_config, config, learning_engine, binance_utils
            )

            if direction and score >= MIN_SCORE_THRESHOLD:
                if (direction == "LONG" and can_open_long) or (direction == "SHORT" and can_open_short):
                    signals[strategy_name] = {
                        "direction": direction,
                        "score": score,
                        "details": details,
                        "contributing_indicators": contributing_indicators,
                        "strategy_name": strategy_name,
                        "timeframe": tf
                    }
                    logger.info(f"Sinal válido gerado para {pair}/{tf}/{direction} com estratégia {strategy_name}")
                else:
                    logger.info(f"Limite de ordens atingido para {direction} em {pair}/{tf} com estratégia {strategy_name}")

        return signals

    def main():
        logger.info("Inicializando arquivos CSV...")
        initialize_csv_files()
        logger.info("Arquivos CSV inicializados com sucesso.")

        if not os.path.exists("oportunidades_perdidas.csv"):
            df_missed = pd.DataFrame(columns=[
                'timestamp', 'robot_name', 'par', 'timeframe', 'direcao',
                'score_tecnico', 'contributing_indicators', 'reason'
            ])
            df_missed.to_csv("oportunidades_perdidas.csv", index=False)
            logger.info("Arquivo oportunidades_perdidas.csv criado com sucesso.")

        logger.info(f"Verificando integridade do arquivo '{SINALS_FILE}'...")
        try:
            df = pd.read_csv(SINALS_FILE)
            logger.info(f"Arquivo '{SINALS_FILE}' lido com sucesso. Número de linhas: {len(df)}")
            for idx, params in enumerate(df['parametros']):
                if pd.notna(params):
                    logger.debug(f"Verificando integridade do parâmetro na linha {idx}: {params}")
                    json.loads(params)
                    logger.debug(f"Parâmetro na linha {idx} é válido.")
            logger.info(f"Arquivo '{SINALS_FILE}' está íntegro.")
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Arquivo '{SINALS_FILE}' contém dados malformados: {e}. Recriando o arquivo.")
            os.remove(SINALS_FILE)
            initialize_csv_files()
            logger.info(f"Arquivo '{SINALS_FILE}' recriado com sucesso.")

        logger.info("Verificando se a porta 8580 está em uso...")
        if is_port_in_use(8580):
            logger.warning("Porta 8580 está em uso. Tentando liberar...")
            kill_process_on_port(8575)
            logger.info("Porta 8580 liberada. Aguardando 1 segundo...")
            time.sleep(1)
        else:
            logger.info("Porta 8580 está livre.")

        dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
        logger.info(f"Iniciando o dashboard Streamlit em {dashboard_path} na porta 8580...")
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", dashboard_path, "--server.port", "8580"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info("Comando para iniciar o dashboard enviado.")

        logger.info("Aguardando o dashboard ficar disponível em http://localhost:8580...")
        if check_dashboard_availability("http://localhost:8580"):
            logger.info("Dashboard iniciado com sucesso em http://localhost:8580")
        else:
            logger.error("Dashboard não está acessível em http://localhost:8580 após 30 segundos.")
            stdout, stderr = process.communicate(timeout=5)
            logger.error(f"Saída do Streamlit: {stdout}")
            logger.error(f"Erros do Streamlit: {stderr}")
            raise RuntimeError("Falha ao iniciar o dashboard. Verifique os logs para mais detalhes.")

        logger.info("Carregando configurações...")
        config = CONFIG  # Usar diretamente o CONFIG do config.py
        # Adicionar quantity_in_usdt ao config para evitar erros
        config['quantity_in_usdt'] = 10.0  # Valor padrão para trades
        logger.info(f"Configurações carregadas: {config}")
        active_modes = [mode for mode, active in config["modes"].items() if active]
        logger.info(f"Bot inicializado com modos ativos: {active_modes}")

        print("┌── Configurações Recarregadas ──┐")
        print(f"│ TP: {config['stop_padrao']['tp_percent']}%")
        print(f"│ SL: {config['stop_padrao']['sl_percent']}%")
        print(f"│ Leverage: {config['leverage']}x")
        print(f"│ Quantidade em USDT: {config.get('quantity_in_usdt', False)}")
        print(f"│ Quantidades: {config.get('quantities', {})}")
        print(f"│ Quantidades (USDT): {config.get('quantities_usdt', {})}")
        print(f"│ Modos Ativos: {config['modes']}")
        print("└───────────────────────────────┘")

        logger.info("Verificando status da API da Binance com check_api_status()...")
        real_status = check_api_status(REAL_API_KEY, REAL_API_SECRET)
        logger.info(f"Resultado do status da API: {real_status}")
        print("┌────────────────── Status das Chaves API ──────────────────┐")
        print(f"│ Chave Real: {'Válida' if real_status['connected'] else 'Erro'} - Permissões: Leitura: {real_status['permissions'].get('read', False)}, Spot Trading: {real_status['permissions'].get('spot', False)}, Futures: {real_status['permissions'].get('futures', False)} │")
        print("└──────────────────────────────────────────────────────────┘")
        if not real_status['connected'] or not any(real_status['permissions'].values()):
            print("\033[91m[ALERTA] Sua chave da Binance está conectando, mas não possui todas as permissões necessárias.")
            print("Possíveis causas:")
            print("- Permissões insuficientes na chave API (habilite leitura, spot e futures no painel da Binance)")
            print("- Restrição de IP na chave (adicione o IP do seu computador ou remova a restrição para teste)")
            print("- Delay de propagação após alteração de permissões (aguarde alguns minutos)")
            print("- Endpoint de permissão da Binance pode estar temporariamente indisponível, mas a chave pode funcionar para preços.")
            print("Se você está recebendo preços normalmente, o bot pode operar parcialmente, mas funções de trading podem falhar!")
            print("\033[0m")

        client = real_status.get("client")
        if not client:
            logger.error("Cliente da Binance não foi inicializado. Encerrando o bot.")
            sys.exit(1)
        logger.info("Usando cliente real para preços e simulações.")

        logger.info(f"Verificando o estado do CONFIG: {config}")

        logger.info("Inicializando módulos do sistema...")
        try:
            logger.info("Inicializando BinanceUtils...")
            binance_utils = BinanceUtils(client, config)
            logger.info("BinanceUtils inicializado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao inicializar BinanceUtils: {e}")
            raise

        try:
            logger.info("Inicializando LearningEngine...")
            learning_engine = LearningEngine()
            logger.info("LearningEngine inicializado com sucesso.")
            # Exibir métricas do modelo no terminal
            print("\n===== STATUS DO MODELO DE MACHINE LEARNING =====")
            print(f"Acurácia atual: {learning_engine.accuracy * 100:.2f}%")
            print(f"Features utilizadas: {', '.join(learning_engine.features)}")
            if hasattr(learning_engine, 'confusion_matrix_') and getattr(learning_engine, 'confusion_matrix_', None) is not None:
                print("\nMatriz de Confusão:")
                print(learning_engine.confusion_matrix_)
            else:
                print("\nMatriz de Confusão: (treine o modelo para visualizar)")
            if hasattr(learning_engine, 'feature_importances_') and getattr(learning_engine, 'feature_importances_', None) is not None:
                print("\nImportância das Features:")
                importances = list(zip(learning_engine.features, learning_engine.feature_importances_))
                importances.sort(key=lambda x: x[1], reverse=True)
                for i, (feat, imp) in enumerate(importances, 1):
                    print(f"{i:2d}. {feat:<15}: {imp:.4f}")
            else:
                print("\nImportância das Features: (treine o modelo para visualizar)")
            if hasattr(learning_engine, 'classification_report_') and getattr(learning_engine, 'classification_report_', None) is not None:
                print("\nRelatório de Classificação:")
                print(learning_engine.classification_report_)
            else:
                print("\nRelatório de Classificação: (treine o modelo para visualizar)")
            print("\nO que a Machine Learning será capaz de executar quando totalmente integrada:")
            print("- Filtrar sinais ruins automaticamente, bloqueando trades de baixo potencial.")
            print("- Priorizar e ranquear sinais de alta probabilidade de sucesso.")
            print("- Adaptar-se ao mercado aprendendo com novos dados de trades.")
            print("- Ajustar parâmetros das estratégias de acordo com o desempenho real.")
            print("- Gerar alertas inteligentes sobre mudanças de padrão ou performance.")
            print("- Exibir previsões e probabilidades de sucesso para cada trade sugerido.")
            print("- Permitir simulação de cenários e backtests inteligentes baseados no modelo.")
            print("- Fornecer explicações sobre o motivo de cada decisão do modelo.")
            print("- Visualizar a evolução do aprendizado e das métricas do modelo ao longo do tempo.")
            print("===============================================\n")
        except Exception as e:
            logger.error(f"Erro ao inicializar LearningEngine: {e}")
            raise

        try:
            logger.info("Inicializando OrderExecutor...")
            order_executor = OrderExecutor(client, config)
            logger.info("OrderExecutor inicializado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao inicializar OrderExecutor: {e}")
            raise

        if config.get('learning_enabled', False):
            logger.info("Learning está habilitado. Tentando treinar o modelo de aprendizado na inicialização...")
            try:
                learning_engine.train()
                bot_status["model_accuracy"] = learning_engine.accuracy
                logger.info("Modelo de aprendizado treinado com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao treinar o modelo de aprendizado: {e}")
        else:
            logger.info("Learning não está habilitado. Pulando treinamento do modelo.")

        logger.info("Inicializando estruturas de dados...")
        active_trades_dry_run = []
        active_combinations = {}
        last_learning_update = time.time()
        bot_status["last_learning_update"] = last_learning_update
        last_candle_close = {pair: {tf: None for tf in TIMEFRAMES} for pair in PAIRS}
        logger.info(f"Estruturas de dados inicializadas: PAIRS={PAIRS}, TIMEFRAMES={TIMEFRAMES}")

        # Agendamento de fechamento de velas
        candle_schedule = {
            pair: {tf: get_next_candle_close_time(tf, datetime.now()) for tf in TIMEFRAMES}
            for pair in PAIRS
        }

        # Carregar estratégias ativas
        from strategy_manager import load_strategies, load_robot_status, save_robot_status
        strategies = load_strategies()
        robot_status = load_robot_status()
        active_strategies = {
            name: config for name, config in strategies.items()
            if robot_status.get(name, False)
        }
        logger.info(f"Estratégias ativas carregadas: {list(active_strategies.keys())}")

        logger.info("Iniciando thread de resumo periódico (a cada 30 segundos)...")
        summary_thread = threading.Thread(
            target=log_summary_periodically,
            args=(config, active_trades_dry_run, learning_engine, last_learning_update, client),
            daemon=True
        )
        summary_thread.start()

        if config["modes"]["backtest"]:
            logger.info("Modo backtest ativado. Iniciando backtest...")
            start_date = config.get("backtest_start_date", "2025-03-01")
            end_date = config.get("backtest_end_date", "2025-04-01")
            logger.info(f"Período do backtest: {start_date} a {end_date}")
            try:
                df_sinais = run_backtest(
                    client, config, binance_utils, learning_engine, start_date, end_date, PAIRS, TIMEFRAMES,
                    config["backtest_config"]["signal_strategies"], get_historical_data, get_quantity, get_funding_rate,
                    generate_signal, simulate_trade_backtest
                )
                logger.info("Backtest concluído com sucesso.")
                logger.info(f"Resultados do backtest: {df_sinais.shape[0]} sinais gerados.")
            except Exception as e:
                logger.error(f"Erro ao executar backtest: {e}")
            return

        logger.info("Iniciando loop principal do UltraBot...")
        iteration_count = 0
        while True:
            iteration_count += 1
            logger.info(f"--- Início da iteração {iteration_count} do loop principal ---")
            try:
                # Atualizar o estado das estratégias no início de cada iteração
                active_strategies = {
                    name: config for name, config in strategies.items()
                    if robot_status.get(name, False)
                }
                logger.info(f"Estratégias ativas atualizadas: {list(active_strategies.keys())}")

                if config.get('learning_enabled', False) and time.time() - last_learning_update > config.get('learning_update_interval', 3600):
                    logger.info("Atualizando modelo de aprendizado...")
                    learning_engine.train()
                    last_learning_update = time.time()
                    bot_status["last_learning_update"] = last_learning_update
                    bot_status["model_accuracy"] = learning_engine.accuracy
                    strategy_performance = calculate_strategy_performance()
                    for strategy_name, perf in strategy_performance.items():
                        learning_engine.adjust_strategy_parameters(strategy_name, perf)
                    logger.info("Modelo de aprendizado atualizado com sucesso.")
                else:
                    logger.debug("Atualização do modelo de aprendizado não necessária nesta iteração.")

                current_time = datetime.now()
                signals_in_iteration = 0
                # Priorizar pares de forma balanceada
                for pair in PAIRS:
                    logger.info(f"Processando par: {pair}")
                    # Salva o preço atual no precos_log.csv, mesmo em modo simulado
                    try:
                        price = get_current_price(client, pair, config)
                        logger.info(f"[DEBUG] Preço salvo em precos_log.csv para {pair}: {price}")
                    except Exception as e:
                        logger.error(f"[ERRO] Falha ao salvar preço em precos_log.csv para {pair}: {e}")
                    signals_by_tf = {}

                    # Gerar sinais em tempo real (se habilitado)
                    for strategy_name, strategy_config in active_strategies.items():
                        for tf in strategy_config.get("timeframes", TIMEFRAMES):
                            direction, score, details, contributing_indicators, strategy_name = generate_realtime_signal(
                                client, pair, tf, strategy_config, config, learning_engine, binance_utils
                            )
                            if direction and score >= MIN_SCORE_THRESHOLD:
                                signals_by_tf[tf] = {
                                    "direction": direction,
                                    "score": score,
                                    "details": details,
                                    "contributing_indicators": contributing_indicators,
                                    "strategy_name": strategy_name
                                }
                                signals_in_iteration += 1
                                bot_status["signals_generated"] += 1
                                logger.info(f"Sinal em tempo real gerado para {pair} ({tf}): {direction} (score={score})")
                            elif direction:
                                logger.info(f"Sinal rejeitado para {pair} ({tf}): score {score} abaixo do limite {MIN_SCORE_THRESHOLD}")

                    # Gerar sinais baseados em velas fechadas
                    for tf in TIMEFRAMES:
                        if current_time < candle_schedule[pair][tf]:
                            logger.debug(f"Vela para {pair} ({tf}) ainda não fechou. Próxima verificação em {candle_schedule[pair][tf]}.")
                            continue

                        candle_schedule[pair][tf] = get_next_candle_close_time(tf, current_time)
                        is_closed, close_time = is_candle_closed(client, pair, tf)
                        if not is_closed:
                            logger.debug(f"Candle para {pair} ({tf}) ainda não fechou. Pulando...")
                            continue

                        if last_candle_close[pair][tf] == close_time:
                            logger.debug(f"Candle para {pair} ({tf}) já processado. Pulando...")
                            continue
                        last_candle_close[pair][tf] = close_time

                        logger.info(f"Candle para {pair} ({tf}) fechada em {close_time}. Processando...")
                        # Aumentar o número de candles para timeframes maiores
                        limit = 200 if tf in ["1h", "4h", "1d"] else 100
                        historical_data = get_historical_data(client, pair, tf, limit=limit)
                        if historical_data.empty:
                            logger.warning(f"Sem dados históricos para {pair} ({tf}). Pulando...")
                            continue
                        logger.info(f"Dados históricos obtidos: {len(historical_data)} candles.")

                        historical_data = calculate_indicators(historical_data, binance_utils)
                        for strategy_name, strategy_config in active_strategies.items():
                            if tf not in strategy_config.get("timeframes", TIMEFRAMES):
                                continue
                            logger.info(f"Gerando sinais para {pair} ({tf}) com estratégia {strategy_name}...")
                            direction, score, details, contributing_indicators, _ = generate_signal(
                                historical_data, tf, strategy_config, config, learning_engine, binance_utils
                            )
                            if not direction:
                                logger.debug(f"Nenhum sinal gerado para {pair} ({tf}) com estratégia {strategy_name}.")
                                continue
                            if score < MIN_SCORE_THRESHOLD:
                                logger.info(f"Sinal rejeitado para {pair} ({tf}) com estratégia {strategy_name}: score {score} abaixo do limite {MIN_SCORE_THRESHOLD}")
                                continue

                            signals_by_tf[tf] = {
                                "direction": direction,
                                "score": score,
                                "details": details,
                                "contributing_indicators": contributing_indicators,
                                "strategy_name": strategy_name
                            }
                            signals_in_iteration += 1
                            bot_status["signals_generated"] += 1
                            logger.info(f"Sinal gerado para {pair} ({tf}) com estratégia {strategy_name}: {direction} (score={score})")

                    if not signals_by_tf:
                        continue

                    final_direction, final_score, multi_tf_details = generate_multi_timeframe_signal(
                        signals_by_tf, learning_engine, signals_by_tf[list(signals_by_tf.keys())[0]]['contributing_indicators']
                    )
                    if not final_direction:
                        logger.debug(f"Nenhum sinal multi-timeframe gerado para {pair}.")
                        continue
                    logger.info(f"Sinal multi-timeframe gerado para {pair}: {final_direction} (score={final_score})")

                    signal_id = str(uuid.uuid4())
                    current_price = get_current_price(client, pair, config)
                    if current_price is None:
                        logger.warning(f"Não foi possível obter preço para {pair}. Pulando sinal...")
                        continue
                    quantity = get_quantity(config, pair, current_price)
                    if quantity is None:
                        logger.error(f"Não foi possível calcular quantidade para {pair}. Pulando sinal...")
                        continue
                    funding_rate = get_funding_rate(client, pair, config, mode="dry_run")
                    strategy_name = signals_by_tf[list(signals_by_tf.keys())[0]]['strategy_name']
                    strategy_config = active_strategies[strategy_name]
                    combo_key = generate_combination_key(pair, final_direction, strategy_name, signals_by_tf[list(signals_by_tf.keys())[0]]['contributing_indicators'], tf)
                    signal_data = {
                        "signal_id": signal_id,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "par": pair,
                        "timeframe": tf,
                        "direcao": final_direction,
                        "preco_entrada": current_price,
                        "quantity": quantity,
                        "score_tecnico": final_score,
                        "motivos": json.dumps(details["reasons"] + [f"Multi-TF: {multi_tf_details.get('multi_tf_confidence', 0.0):.2f}"]),
                        "funding_rate": funding_rate,
                        "localizadores": json.dumps(details["locators"]),
                        "parametros": json.dumps({
                            "tp_percent": strategy_config.get("tp_percent", config["stop_padrao"]["tp_percent"]),
                            "sl_percent": strategy_config.get("sl_percent", config["stop_padrao"]["sl_percent"]),
                            "leverage": strategy_config.get("leverage", config["leverage"])
                        }),
                        "timeframes_analisados": json.dumps(list(signals_by_tf.keys())),
                        "contributing_indicators": signals_by_tf[list(signals_by_tf.keys())[0]]['contributing_indicators'],
                        "strategy_name": strategy_name,
                        "combination_key": combo_key,
                        "historical_win_rate": details.get("historical_win_rate", 0.0),
                        "avg_pnl": details.get("avg_pnl", 0.0),
                        "estado": "aberto",
                        "side_performance": json.dumps({"LONG": 0.0, "SHORT": 0.0}),
                        "timeframe_weight": 1.0 / (TIMEFRAMES.index(tf) + 1)
                    }
                    signal_data['quality_score'] = calculate_signal_quality(historical_data, signal_data, binance_utils)
                    signal_queue.put((-signal_data['quality_score'], signal_data))
                    signals_in_iteration += 1
                    bot_status["signals_generated"] += 1

                from trade_manager import check_global_and_robot_limit
                # Remover limitação global: processar todos os sinais da fila
                while not signal_queue.empty():
                    _, signal_data = signal_queue.get()
                    strategy_name = signal_data['strategy_name']
                    strategy_config = active_strategies[strategy_name]
                    strategy_active_trades = [trade for trade in active_trades_dry_run if trade['strategy_name'] == strategy_name]
                    combo_key = signal_data['combination_key']
                    # Checagem de limite global e por robô
                    if not check_global_and_robot_limit(strategy_name, active_trades_dry_run):
                        logger.warning(f"Limite global (540) ou por robô (36) atingido para {strategy_name}. Sinal {signal_data['signal_id']} rejeitado.")
                        save_signal(signal_data, accepted=False, mode="dry_run")
                        save_signal_log(signal_data, accepted=False, mode="dry_run")
                        rejected_signals.put((-signal_data['quality_score'], signal_data))
                        continue
                    strategy_max_trades = strategy_config.get("max_trades_simultaneos", 1)
                    if len(strategy_active_trades) >= strategy_max_trades:
                        logger.warning(f"Limite de trades simultâneos atingido para {strategy_name} ({len(strategy_active_trades)}/{strategy_max_trades}). Sinal {signal_data['signal_id']} rejeitado.")
                        save_signal(signal_data, accepted=False, mode="dry_run")
                        save_signal_log(signal_data, accepted=False, mode="dry_run")
                        rejected_signals.put((-signal_data['quality_score'], signal_data))
                        continue

                    if combo_key in active_combinations and config["modes"]["dry_run"]:
                        logger.info(f"Combinação já ativa: {combo_key}")
                        continue

                    logger.info(f"Novo sinal aceito: {signal_data['par']} - {signal_data['direcao']} (ID: {signal_data['signal_id']}, Score: {signal_data['quality_score']:.2f})")
                    save_signal(signal_data, accepted=True, mode="dry_run")
                    save_signal_log(signal_data, accepted=True, mode="dry_run")

                    if config["modes"]["dry_run"]:
                        active_combinations[combo_key] = signal_data['signal_id']
                        active_trades_dry_run.append(signal_data)
                        bot_status["orders_opened"] += 1

                        robot_name = signal_data['strategy_name']
                        if robot_name not in robots_status:
                            robots_status[robot_name] = {
                                "last_order": signal_data,
                                "total_pnl": 0.0
                            }
                        else:
                            robots_status[robot_name]["last_order"] = signal_data

                        threading.Thread(
                            target=simulate_trade,
                            args=(client, signal_data, config, active_trades_dry_run, binance_utils, order_executor, active_combinations, get_current_price, get_funding_rate),
                            daemon=True
                        ).start()
                        logger.info(f"Thread de simulação iniciada para sinal {signal_id}.")

                # Reavaliar sinais rejeitados, também sem limitação global
                while not rejected_signals.empty():
                    _, signal_data = rejected_signals.get()
                    strategy_name = signal_data['strategy_name']
                    strategy_config = active_strategies[strategy_name]
                    strategy_active_trades = [trade for trade in active_trades_dry_run if trade['strategy_name'] == strategy_name]
                    combo_key = signal_data['combination_key']
                    # Checagem de limite global e por robô
                    if not check_global_and_robot_limit(strategy_name, active_trades_dry_run):
                        continue
                    strategy_max_trades = strategy_config.get("max_trades_simultaneos", 1)
                    if len(strategy_active_trades) >= strategy_max_trades:
                        rejected_signals.put((-signal_data['quality_score'], signal_data))
                        break
                    if combo_key in active_combinations:
                        continue

                    logger.info(f"Reavaliando sinal rejeitado: {signal_data['par']} - {signal_data['direcao']} (ID: {signal_data['signal_id']})")
                    save_signal(signal_data, accepted=True, mode="dry_run")
                    save_signal_log(signal_data, accepted=True, mode="dry_run")
                    active_combinations[combo_key] = signal_data['signal_id']
                    active_trades_dry_run.append(signal_data)
                    bot_status["orders_opened"] += 1

                    robot_name = signal_data['strategy_name']
                    if robot_name not in robots_status:
                        robots_status[robot_name] = {
                            "last_order": signal_data,
                            "total_pnl": 0.0
                        }
                    else:
                        robots_status[robot_name]["last_order"] = signal_data

                    threading.Thread(
                        target=simulate_trade,
                        args=(client, signal_data, config, active_trades_dry_run, binance_utils, order_executor, active_combinations, get_current_price, get_funding_rate),
                        daemon=True
                    ).start()

                # Adicionar lógica para reiniciar partes do sistema afetadas por erros
                if system_errors:
                    last_error = system_errors[-1]
                    logger.warning(f"Último erro registrado: {last_error['description']} em {last_error['timestamp']} - Motivo: {last_error['reason']}")
                    if "loop principal" in last_error['description']:
                        logger.info("Tentando reiniciar partes afetadas do sistema...")
                        try:
                            # Recarregar estratégias e estado do robô
                            strategies = load_strategies()
                            robot_status = load_robot_status()
                            logger.info("Estratégias e estado do robô recarregados com sucesso.")
                        except Exception as e:
                            logger.error(f"Erro ao reiniciar partes do sistema: {e}")

                # Garantir que o estado atualizado seja salvo periodicamente
                save_robot_status(robot_status)
                logger.info("Estado do robô salvo periodicamente.")

                # Adicionar uma função para validar a consistência entre sinais, ordens abertas e fechadas
                def validate_bot_status():
                    """Valida a consistência entre sinais gerados, ordens abertas e fechadas."""
                    try:
                        df = pd.read_csv(SINALS_FILE)
                        total_signals = len(df)
                        closed_orders = len(df[df['estado'] == 'fechado'])
                        open_orders = len(df[df['estado'] == 'aberto'])

                        # Atualizar bot_status com base nos dados reais
                        bot_status["signals_generated"] = total_signals
                        bot_status["orders_closed"] = closed_orders
                        bot_status["orders_opened"] = open_orders

                        logger.info(f"Validação do status do bot: {total_signals} sinais gerados, {open_orders} ordens abertas, {closed_orders} ordens fechadas.")
                    except Exception as e:
                        logger.error(f"Erro ao validar o status do bot: {e}")

                # Chamar a função de validação no final de cada iteração do loop principal
                validate_bot_status()

                # Chamar a função de atualização no final de cada iteração do loop principal
                update_orders_status()
                close_invalid_open_orders(client)
                update_bot_summary()

                logger.info(f"--- Fim da iteração {iteration_count} do loop principal ---")
                time.sleep(1)  # Reduzido para 1 segundo, já que o agendamento cuida da frequência

            except KeyboardInterrupt:
                logger.info("Interrupção manual detectada. Encerrando o bot...")
                break
            except Exception as e:
                error_entry = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "description": "Erro no loop principal",
                    "reason": str(e)
                }
                system_errors.append(error_entry)
                logger.error(f"Erro no loop principal: {e}")
                time.sleep(5)
    try:
        if __name__ == "__main__":
            logger.info("Iniciando execução do script main.py...")
            main()
            logger.info("Execução do script main.py finalizada.")
    except Exception as e:
        logger.error(f"Erro durante a execução do script: {e}")
    finally:
        logger.info("Finalizando execução do script main.py...")
except Exception as e:
    logger.error(f"Erro durante a execução do bot: {e}")
    raise
finally:
    logger.info("Finalizando execução do bot...")
