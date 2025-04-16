from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT
from utils import logger
from binance.exceptions import BinanceAPIException
import pandas as pd
import json
from datetime import datetime
from trade_manager import check_timeframe_direction_limit, check_active_trades, check_global_and_robot_limit

SINALS_FILE = "sinais_detalhados.csv"

class OrderExecutor:
    """
    Módulo para execução de ordens reais na Binance.
    """
    def __init__(self, client, config):
        """
        Inicializa o OrderExecutor com cliente Binance e configurações.

        Args:
            client: Cliente Binance (binance.client.Client).
            config: Configurações do sistema (dicionário).
        """
        self.client = client
        self.config = config

    def configurar_alavancagem(self, par, leverage):
        """
        Configura a alavancagem para o par especificado.

        Args:
            par (str): Par de negociação (ex.: "DOGEUSDT").
            leverage (int): Nível de alavancagem (ex.: 20).
        """
        try:
            self.client.futures_change_leverage(symbol=par, leverage=leverage)
            logger.info(f"Alavancagem configurada para {par}: {leverage}x")
        except BinanceAPIException as e:
            logger.error(f"Erro ao configurar alavancagem para {par}: {e}")
            raise

    def executar_ordem(self, par, direcao, capital, stop_loss, take_profit, mercado='futures', dry_run=False):
        """
        Executa uma ordem de mercado ou simula em dry run.

        Args:
            par (str): Par de negociação (ex.: "DOGEUSDT").
            direcao (str): Direção da ordem ("LONG" ou "SHORT").
            capital (float): Capital para a ordem em USDT.
            stop_loss (float): Percentual de stop loss.
            take_profit (float): Percentual de take profit.
            mercado (str): Tipo de mercado (default: 'futures').
            dry_run (bool): Se True, simula a ordem sem executá-la.

        Returns:
            dict: Detalhes da ordem executada ou simulada.
        """
        # Checagem centralizada de limite de ordens por direção/par/timeframe/robô
        active_trades = check_active_trades()
        # Checagem de limite global e por robô
        if not check_global_and_robot_limit(self.config['strategy_name'], active_trades):
            logger.warning(f"Limite global (540) ou por robô (36) atingido para {self.config['strategy_name']}. Ordem não será criada.")
            with open("oportunidades_perdidas.csv", "a") as f:
                f.write(f"{pd.Timestamp.now()},{self.config['strategy_name']},{par},{self.config['timeframe']},{direcao},N/A,N/A,Limite global ou por robô atingido\n")
            return {"status": "ignored", "reason": "limite global ou por robô atingido"}
        can_open = check_timeframe_direction_limit(
            par,
            self.config['timeframe'],
            direcao,
            self.config['strategy_name'],
            active_trades,
            self.config
        )
        if not can_open:
            logger.warning(f"Limite de trades simultâneos atingido para {self.config['strategy_name']} em {par}/{self.config['timeframe']}/{direcao}. Ordem não será criada.")
            with open("oportunidades_perdidas.csv", "a") as f:
                f.write(f"{pd.Timestamp.now()},{self.config['strategy_name']},{par},{self.config['timeframe']},{direcao},N/A,N/A,Limite de trades simultâneos atingido\n")
            return {"status": "ignored", "reason": "limite de trades simultâneos atingido"}

        # Verificar se já existe uma ordem aberta para o robô na mesma direção e timeframe
        df = pd.read_csv("sinais_detalhados.csv")
        ordens_abertas = df[(df['estado'] == 'aberto') &
                            (df['strategy_name'] == self.config['strategy_name']) &
                            (df['direcao'] == direcao) &
                            (df['timeframe'] == self.config['timeframe'])]
        if not ordens_abertas.empty:
            logger.warning(f"Já existe uma ordem aberta para a estratégia {self.config['strategy_name']} na direção {direcao} e timeframe {self.config['timeframe']}. Ordem não será criada.")
            # Registrar no log de oportunidades perdidas
            with open("oportunidades_perdidas.csv", "a") as f:
                f.write(f"{pd.Timestamp.now()},{self.config['strategy_name']},{par},{self.config['timeframe']},{direcao},N/A,N/A,Limite de trades simultâneos atingido\n")
            return {"status": "ignored", "reason": "existing open order for direction and timeframe"}

        if dry_run:
            logger.info(f"[DRY RUN] Simulando ordem {direcao} em {par} com capital {capital} USDT, SL: {stop_loss}%, TP: {take_profit}%")
            return {"status": "simulated", "order_id": None}

        lado = SIDE_BUY if direcao == "LONG" else SIDE_SELL
        try:
            preco = float(self.client.futures_symbol_ticker(symbol=par)['price'])
            leverage = self.config.get('leverage', 20)
            quantidade = (capital * leverage) / preco

            # Configurar alavancagem
            self.configurar_alavancagem(par, leverage)

            # Criar ordem de mercado
            ordem = self.client.futures_create_order(
                symbol=par,
                side=lado,
                type=ORDER_TYPE_MARKET,
                quantity=quantidade
            )

            # Calcular preços de TP e SL
            sl_preco = preco * (1 - stop_loss / 100) if direcao == "LONG" else preco * (1 + stop_loss / 100)
            tp_preco = preco * (1 + take_profit / 100) if direcao == "LONG" else preco * (1 - take_profit / 100)

            # Criar ordens de TP e SL
            self.client.futures_create_order(
                symbol=par,
                side=SIDE_SELL if direcao == "LONG" else SIDE_BUY,
                type=ORDER_TYPE_LIMIT,
                quantity=quantidade,
                price=tp_preco,
                stopPrice=tp_preco,
                timeInForce='GTC'
            )
            self.client.futures_create_order(
                symbol=par,
                side=SIDE_SELL if direcao == "LONG" else SIDE_BUY,
                type=ORDER_TYPE_LIMIT,
                quantity=quantidade,
                price=sl_preco,
                stopPrice=sl_preco,
                timeInForce='GTC'
            )

            logger.info(f"Ordem {direcao} executada em {par}: {ordem}")
            return ordem
        except BinanceAPIException as e:
            logger.error(f"Erro ao executar ordem em {par}: {e}")
            raise
        except Exception as e:
            logger.error(f"Erro inesperado ao executar ordem em {par}: {e}")
            raise

def close_order(signal_id, mark_price, reason):
    """Fecha uma ordem com base no ID do sinal, preço de saída e motivo."""
    try:
        df = pd.read_csv(SINALS_FILE)
        order_idx = df.index[df['signal_id'] == signal_id].tolist()
        if not order_idx:
            logger.error(f"Ordem {signal_id} não encontrada ao tentar fechar.")
            return
        order_idx = order_idx[0]
        order = df.iloc[order_idx]
        direction = order['direcao']
        entry_price = float(order['preco_entrada'])

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
    except Exception as e:
        logger.error(f"Erro ao fechar ordem {signal_id}: {e}")