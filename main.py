import sys
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

LOCK_FILE = "dashboard.lock"

# Verificar se o arquivo de lock já existe
if os.path.exists(LOCK_FILE):
    print("O bot já está em execução. Saindo...")
    sys.exit(1)

# Criar o arquivo de lock
with open(LOCK_FILE, "w") as lock:
    lock.write("lock")

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
        """Gera sinais em tempo real para timeframes menores."""
        if tf not in ["1m", "5m"] or not config.get("realtime_signals_enabled", False):
            return None, None, None, None, None

        current_price = get_current_price(client, pair, config)
        if current_price is None:
            return None, None, None, None, None

        historical_data = get_historical_data(client, pair, tf, limit=50)
        if historical_data.empty:
            return None, None, None, None, None

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
                print(f"│ Sinais Gerados: {bot_status['signals_generated']}")
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

                # Processar a fila de sinais
                global_max_trades = config.get("max_trades_simultaneos", 50)  # Limite global
                while not signal_queue.empty() and len(active_trades_dry_run) < global_max_trades:
                    _, signal_data = signal_queue.get()
                    strategy_name = signal_data['strategy_name']
                    strategy_config = active_strategies[strategy_name]
                    strategy_active_trades = [trade for trade in active_trades_dry_run if trade['strategy_name'] == strategy_name]
                    combo_key = signal_data['combination_key']
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

                # Reavaliar sinais rejeitados
                while len(active_trades_dry_run) < global_max_trades and not rejected_signals.empty():
                    _, signal_data = rejected_signals.get()
                    strategy_name = signal_data['strategy_name']
                    strategy_config = active_strategies[strategy_name]
                    strategy_active_trades = [trade for trade in active_trades_dry_run if trade['strategy_name'] == strategy_name]
                    combo_key = signal_data['combination_key']
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

    if __name__ == "__main__":
        logger.info("Iniciando execução do script main.py...")
        main()
        logger.info("Execução do script main.py finalizada.")
finally:
    # Remover o arquivo de lock ao finalizar
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
    print("Bot finalizado e lock removido.")