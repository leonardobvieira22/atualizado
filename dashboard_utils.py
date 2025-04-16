# dashboard_utils.py
import pandas as pd
import json
import os
from datetime import datetime
import uuid
from config import CONFIG, SYMBOLS, TIMEFRAMES
from utils import logger
from trade_manager import check_timeframe_direction_limit, check_active_trades, check_global_and_robot_limit
from data_manager import get_quantity

def load_data(file_path="sinais_detalhados.csv", columns=None):
    """
    Carrega dados de um arquivo CSV especificado, opcionalmente filtrando por colunas.
    Padrão: sinais_detalhados.csv
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(f"Arquivo {file_path} não encontrado.")
            return pd.DataFrame(columns=columns if columns else [])
        
        df = pd.read_csv(file_path)
        if columns:
            missing_cols = [col for col in columns if col not in df.columns]
            if missing_cols:
                logger.warning(f"Colunas ausentes em {file_path}: {missing_cols}")
                for col in missing_cols:
                    df[col] = None
            df = df[columns]
        return df
    except Exception as e:
        logger.error(f"Erro ao carregar dados de {file_path}: {e}")
        return pd.DataFrame(columns=columns if columns else [])

def load_signals():
    """Carrega os sinais do arquivo sinais_detalhados.csv."""
    return load_data("sinais_detalhados.csv")

def load_missed_opportunities():
    """Carrega as oportunidades perdidas do arquivo oportunidades_perdidas.csv."""
    return load_data("oportunidades_perdidas.csv")

def load_robot_status():
    """Carrega o status dos robôs ativos."""
    try:
        with open("strategies.json", "r") as f:
            strategies = json.load(f)
        return {name: True for name in strategies.keys()}
    except FileNotFoundError:
        logger.warning("strategies.json não encontrado. Retornando status padrão.")
        return {"swing_trade_composite": True}
    except Exception as e:
        logger.error(f"Erro ao carregar status dos robôs: {e}")
        return {}

def save_robot_status(robot_status):
    """Salva o status dos robôs ativos."""
    try:
        with open("strategies_status.json", "w") as f:
            json.dump(robot_status, f, indent=4)
        logger.info("Status dos robôs salvo com sucesso.")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar status dos robôs: {e}")
        return False

def calculate_performance(df):
    """Calcula o desempenho com base nos sinais."""
    try:
        if df.empty:
            return {"total_signals": 0, "win_rate": 0.0, "avg_pnl": 0.0}

        total_signals = len(df)
        closed_signals = df[df['estado'] == 'fechado']
        wins = len(closed_signals[closed_signals['resultado'] == 'TP'])
        win_rate = (wins / len(closed_signals) * 100) if len(closed_signals) > 0 else 0.0
        avg_pnl = closed_signals['pnl_realizado'].mean() if not closed_signals['pnl_realizado'].isna().all() else 0.0

        return {
            "total_signals": total_signals,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl
        }
    except Exception as e:
        logger.error(f"Erro ao calcular desempenho: {e}")
        return {"total_signals": 0, "win_rate": 0.0, "avg_pnl": 0.0}

def generate_orders(strategy_name, strategy_config):
    """Gera ordens simuladas para exibição no dashboard, respeitando limites de ordens abertas e valor fixo de 10 USD por ordem."""
    try:
        tp_percent = strategy_config.get('tp_percent', CONFIG.get('tp_percent', 0.5))
        sl_percent = strategy_config.get('sl_percent', CONFIG.get('sl_percent', 0.3))
        leverage = strategy_config.get('leverage', CONFIG.get('leverage', 10))
        indicators = strategy_config.get('indicadores_ativos', {'EMA': True, 'RSI': True, 'MACD': True})
        orders = []
        active_trades = check_active_trades()  # Lê ordens abertas reais
        config = CONFIG
        config['quantity_in_usdt'] = 10.0  # Garante valor fixo de 10 USD por ordem
        # Checagem de limite global e por robô
        if not check_global_and_robot_limit(strategy_name, active_trades):
            logger.warning(f"Limite global (540) ou por robô (36) atingido para {strategy_name}. Nenhuma ordem será gerada no dashboard.")
            return []
        for pair in SYMBOLS:
            for tf in TIMEFRAMES:
                for direction in ['LONG', 'SHORT']:
                    if not check_timeframe_direction_limit(pair, tf, direction, strategy_name, active_trades, config):
                        continue
                    # Buscar preço de entrada simulado (último close do histórico)
                    historical_file = f"historical_data_{pair}_{tf}.csv"
                    if os.path.exists(historical_file):
                        df_hist = pd.read_csv(historical_file)
                        if not df_hist.empty:
                            entry_price = float(df_hist['close'].iloc[-1])
                        else:
                            entry_price = 1.0
                    else:
                        entry_price = 1.0
                    quantity = get_quantity(config, pair, entry_price) or 0.0
                    order = {
                        "signal_id": str(uuid.uuid4()),
                        "par": pair,
                        "direcao": direction,
                        "preco_entrada": entry_price,
                        "quantity": quantity,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "timeframe": tf,
                        "strategy_name": strategy_name,
                        "contributing_indicators": ";".join([k for k, v in indicators.items() if v]),
                        "motivos": json.dumps(["Simulado para dashboard"]),
                        "localizadores": json.dumps({}),
                        "parametros": json.dumps({
                            "tp_percent": tp_percent,
                            "sl_percent": sl_percent,
                            "leverage": leverage
                        }),
                        "estado": "aberto",
                        "aceito": True
                    }
                    orders.append(order)
                    # Atualiza lista local para impedir múltiplas simulações do mesmo tipo
                    active_trades.append({
                        'par': pair,
                        'timeframe': tf,
                        'direcao': direction,
                        'strategy_name': strategy_name,
                        'estado': 'aberto'
                    })
        return orders
    except Exception as e:
        logger.error(f"Erro ao gerar ordens para {strategy_name}: {e}")
        return []

def load_config():
    """Carrega configurações para o dashboard."""
    return CONFIG

def save_config(config):
    """Salva as configurações fornecidas."""
    try:
        global CONFIG
        CONFIG.update(config)
        logger.info("Configurações salvas com sucesso.")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar configurações: {e}")
        return False

def get_mark_price(client, symbol):
    """Obtém o preço de marcação para um símbolo."""
    try:
        if client is None:
            logger.warning(f"Cliente da Binance não inicializado para obter preço de {symbol}")
            return None
        price = client.get_symbol_ticker(symbol=symbol)
        return float(price.get('price', 0.0))
    except Exception as e:
        logger.error(f"Erro ao obter preço de marcação para {symbol}: {e}")
        return None

def calculate_liq_price(entry_price, leverage, direction, maintenance_margin_rate=0.005):
    """Calcula o preço de liquidação para uma posição."""
    try:
        entry_price = float(entry_price)
        leverage = float(leverage)
        if leverage <= 0:
            raise ValueError("Alavancagem deve ser maior que zero")
        if entry_price <= 0:
            raise ValueError("Preço de entrada deve ser maior que zero")

        if direction == "LONG":
            liq_price = entry_price * (1 - (1 / leverage) + maintenance_margin_rate)
        else:  # SHORT
            liq_price = entry_price * (1 + (1 / leverage) - maintenance_margin_rate)

        return round(liq_price, 8)
    except Exception as e:
        logger.error(f"Erro ao calcular preço de liquidação: {e}")
        return None

def calculate_distances(entry_price, current_price, tp_price, sl_price):
    """Calcula as distâncias percentuais do preço atual para TP e SL."""
    try:
        entry_price = float(entry_price)
        current_price = float(current_price)
        tp_price = float(tp_price)
        sl_price = float(sl_price)

        if entry_price <= 0:
            raise ValueError("Preço de entrada deve ser maior que zero")

        tp_distance = ((tp_price - current_price) / entry_price) * 100
        sl_distance = ((current_price - sl_price) / entry_price) * 100

        return {
            "tp_distance_percent": round(tp_distance, 2),
            "sl_distance_percent": round(sl_distance, 2)
        }
    except Exception as e:
        logger.error(f"Erro ao calcular distâncias: {e}")
        return {"tp_distance_percent": 0.0, "sl_distance_percent": 0.0}

def close_order_manually(signal_id, current_price):
    """
    Fecha uma ordem manualmente com base no signal_id e preço atual.
    """
    try:
        if not os.path.exists("sinais_detalhados.csv"):
            logger.error("Arquivo sinais_detalhados.csv não encontrado.")
            return False

        df = pd.read_csv("sinais_detalhados.csv")
        if signal_id not in df['signal_id'].values:
            logger.error(f"Ordem com signal_id {signal_id} não encontrada.")
            return False

        order_index = df[df['signal_id'] == signal_id].index[0]
        entry_price = float(df.loc[order_index, 'preco_entrada'])
        direction = df.loc[order_index, 'direcao']
        quantity = float(df.loc[order_index, 'quantity'])
        leverage = float(json.loads(df.loc[order_index, 'parametros'])['leverage'])

        if direction == "LONG":
            lucro_percentual = ((current_price - entry_price) / entry_price) * 100 * leverage
        else:  # SHORT
            lucro_percentual = ((entry_price - current_price) / entry_price) * 100 * leverage

        df.loc[order_index, 'preco_saida'] = current_price
        df.loc[order_index, 'lucro_percentual'] = lucro_percentual
        df.loc[order_index, 'pnl_realizado'] = lucro_percentual * quantity
        df.loc[order_index, 'resultado'] = "Manual"
        df.loc[order_index, 'timestamp_saida'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.loc[order_index, 'estado'] = "fechado"

        df.to_csv("sinais_detalhados.csv", index=False)
        logger.info(f"Ordem {signal_id} fechada manualmente: Preço de saída={current_price}, Lucro/Perda={lucro_percentual:.2f}%")
        return True
    except Exception as e:
        logger.error(f"Erro ao fechar ordem manualmente {signal_id}: {e}")
        return False

def close_order(signal_id, exit_price, result="Manual"):
    """
    Fecha uma ordem no arquivo sinais_detalhados.csv com preço de saída e resultado especificado.
    """
    try:
        if not os.path.exists("sinais_detalhados.csv"):
            logger.error("Arquivo sinais_detalhados.csv não encontrado.")
            return False

        df = pd.read_csv("sinais_detalhados.csv")
        if signal_id not in df['signal_id'].values:
            logger.error(f"Ordem com signal_id {signal_id} não encontrada.")
            return False

        order_index = df[df['signal_id'] == signal_id].index[0]
        entry_price = float(df.loc[order_index, 'preco_entrada'])
        direction = df.loc[order_index, 'direcao']
        quantity = float(df.loc[order_index, 'quantity'])
        leverage = float(json.loads(df.loc[order_index, 'parametros'])['leverage'])

        if direction == "LONG":
            lucro_percentual = ((exit_price - entry_price) / entry_price) * 100 * leverage
        else:  # SHORT
            lucro_percentual = ((entry_price - exit_price) / entry_price) * 100 * leverage

        df.loc[order_index, 'preco_saida'] = exit_price
        df.loc[order_index, 'lucro_percentual'] = lucro_percentual
        df.loc[order_index, 'pnl_realizado'] = lucro_percentual * quantity
        df.loc[order_index, 'resultado'] = result
        df.loc[order_index, 'timestamp_saida'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.loc[order_index, 'estado'] = "fechado"

        df.to_csv("sinais_detalhados.csv", index=False)
        logger.info(f"Ordem {signal_id} fechada: Preço de saída={exit_price}, Resultado={result}, Lucro/Perda={lucro_percentual:.2f}%")
        return True
    except Exception as e:
        logger.error(f"Erro ao fechar ordem {signal_id}: {e}")
        return False

def get_tp_sl(signal_id):
    """
    Obtém os valores de Take Profit (TP) e Stop Loss (SL) de uma ordem com base no signal_id.
    """
    try:
        if not os.path.exists("sinais_detalhados.csv"):
            logger.error("Arquivo sinais_detalhados.csv não encontrado.")
            return None

        df = pd.read_csv("sinais_detalhados.csv")
        if signal_id not in df['signal_id'].values:
            logger.error(f"Ordem com signal_id {signal_id} não encontrada.")
            return None

        order_index = df[df['signal_id'] == signal_id].index[0]
        entry_price = float(df.loc[order_index, 'preco_entrada'])
        direction = df.loc[order_index, 'direcao']
        parametros = json.loads(df.loc[order_index, 'parametros'])
        tp_percent = float(parametros['tp_percent'])
        sl_percent = float(parametros['sl_percent'])

        if direction == "LONG":
            tp_price = entry_price * (1 + tp_percent / 100)
            sl_price = entry_price * (1 - sl_percent / 100)
        else:  # SHORT
            tp_price = entry_price * (1 - tp_percent / 100)
            sl_price = entry_price * (1 + sl_percent / 100)

        return {
            "tp_price": round(tp_price, 8),
            "sl_price": round(sl_price, 8)
        }
    except Exception as e:
        logger.error(f"Erro ao obter TP/SL para ordem {signal_id}: {e}")
        return None

def check_alerts(client, threshold_percent=0.1):
    """
    Verifica alertas para ordens abertas com base na proximidade de TP ou SL.
    """
    try:
        if not os.path.exists("sinais_detalhados.csv"):
            logger.warning("Arquivo sinais_detalhados.csv não encontrado. Nenhum alerta verificado.")
            return []

        df = pd.read_csv("sinais_detalhados.csv")
        open_orders = df[df['estado'] == 'aberto']
        if open_orders.empty:
            logger.info("Nenhuma ordem aberta para verificar alertas.")
            return []

        alerts = []
        for _, order in open_orders.iterrows():
            signal_id = order['signal_id']
            symbol = order['par']
            direction = order['direcao']
            entry_price = float(order['preco_entrada'])
            parametros = json.loads(order['parametros'])
            tp_percent = float(parametros['tp_percent'])
            sl_percent = float(parametros['sl_percent'])

            current_price = get_mark_price(client, symbol)
            if current_price is None:
                logger.warning(f"Não foi possível obter preço atual para {symbol}. Pulando alerta.")
                continue

            if direction == "LONG":
                tp_price = entry_price * (1 + tp_percent / 100)
                sl_price = entry_price * (1 - sl_percent / 100)
            else:  # SHORT
                tp_price = entry_price * (1 - tp_percent / 100)
                sl_price = entry_price * (1 + sl_percent / 100)

            distances = calculate_distances(entry_price, current_price, tp_price, sl_price)
            tp_distance = abs(distances['tp_distance_percent'])
            sl_distance = abs(distances['sl_distance_percent'])

            if tp_distance <= threshold_percent:
                alerts.append({
                    "signal_id": signal_id,
                    "symbol": symbol,
                    "alert_type": "TP",
                    "message": f"Ordem {signal_id} ({symbol}) está a {tp_distance:.2f}% do TP ({tp_price:.8f}). Preço atual: {current_price:.8f}"
                })
            elif sl_distance <= threshold_percent:
                alerts.append({
                    "signal_id": signal_id,
                    "symbol": symbol,
                    "alert_type": "SL",
                    "message": f"Ordem {signal_id} ({symbol}) está a {sl_distance:.2f}% do SL ({sl_price:.8f}). Preço atual: {current_price:.8f}"
                })

        if alerts:
            for alert in alerts:
                logger.info(f"Alerta: {alert['message']}")
        else:
            logger.info("Nenhum alerta detectado para ordens abertas.")

        return alerts
    except Exception as e:
        logger.error(f"Erro ao verificar alertas: {e}")
        return []

def reset_bot_data(password_input):
    """
    Reseta todas as ordens e estatísticas do bot após validação da senha
    """
    from config import CONFIG
    import os
    import pandas as pd
    from datetime import datetime
    from utils import logger
    
    if password_input != CONFIG.get('reset_password'):
        return False, "Senha incorreta!"
    
    try:
        # Backup dos arquivos antes de resetar
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        files_to_reset = [
            "sinais_detalhados.csv",
            "oportunidades_perdidas.csv",
            "trades_dry_run.json",
            "wallet_dry_run.json",
            
        ]
        
        # Criar backups
        for file in files_to_reset:
            if os.path.exists(file):
                backup_name = f"{file}.backup_{timestamp}"
                os.rename(file, backup_name)
        
        # Recriar arquivos vazios com estrutura correta
        df_sinais = pd.DataFrame(columns=[
            'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
            'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
            'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
            'motivos', 'timeframe', 'aceito', 'parametros', 'quality_score'
        ])
        df_sinais.to_csv("sinais_detalhados.csv", index=False)
        
        df_missed = pd.DataFrame(columns=[
            'timestamp', 'robot_name', 'par', 'timeframe', 'direcao',
            'score_tecnico', 'contributing_indicators', 'reason'
        ])
        df_missed.to_csv("oportunidades_perdidas.csv", index=False)
        
        # Recriar arquivos JSON vazios
        for json_file in ["trades_dry_run.json", "wallet_dry_run.json", "strategy_confidence.json"]:
            with open(json_file, "w") as f:
                f.write("{}")
        
        logger.info("Reset do bot realizado com sucesso")
        return True, "Reset realizado com sucesso! Os dados anteriores foram backupeados com timestamp."
        
    except Exception as e:
        logger.error(f"Erro ao realizar reset do bot: {e}")
        return False, f"Erro ao realizar reset: {str(e)}"

def calculate_advanced_metrics(df):
    """
    Calcula métricas quantitativas avançadas para cada estratégia:
    - Sharpe Ratio
    - Drawdown Máximo
    - Expectância
    - Payoff Ratio
    - Total PnL
    - Win Rate
    Retorna um dicionário com as métricas por estratégia.
    """
    import numpy as np
    metrics = {}
    if df.empty or 'strategy_name' not in df.columns:
        return metrics
    grouped = df[df['estado'] == 'fechado'].groupby('strategy_name')
    for strategy, group in grouped:
        pnls = group['pnl_realizado'].dropna().values
        returns = pnls / 100  # Considerando PnL em %
        total_pnl = np.sum(pnls)
        win_trades = group[group['pnl_realizado'] > 0]
        loss_trades = group[group['pnl_realizado'] <= 0]
        win_rate = len(win_trades) / len(group) * 100 if len(group) > 0 else 0
        avg_win = win_trades['pnl_realizado'].mean() if not win_trades.empty else 0
        avg_loss = loss_trades['pnl_realizado'].mean() if not loss_trades.empty else 0
        payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else np.nan
        expectancia = ((win_rate/100) * avg_win) + ((1 - win_rate/100) * avg_loss)
        # Sharpe Ratio (assumindo taxa livre de risco 0)
        sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else np.nan
        # Drawdown Máximo
        equity_curve = np.cumsum(returns)
        high_water_mark = np.maximum.accumulate(equity_curve)
        drawdowns = equity_curve - high_water_mark
        max_drawdown = drawdowns.min() if len(drawdowns) > 0 else 0
        metrics[strategy] = {
            'total_pnl': round(total_pnl, 2),
            'win_rate': round(win_rate, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'payoff_ratio': round(payoff_ratio, 2) if not np.isnan(payoff_ratio) else None,
            'expectancia': round(expectancia, 2),
            'sharpe': round(sharpe, 2) if not np.isnan(sharpe) else None,
            'max_drawdown': round(max_drawdown, 2)
        }
    return metrics