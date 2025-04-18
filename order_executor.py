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

    def executar_ordem(self, par, direcao, capital, stop_loss, take_profit, mercado='futures', dry_run=False, dry_run_id=None):
        logger.info(f"[DEBUG-ORDER_EXECUTOR] Parâmetros: par={par}, direcao={direcao}, capital={capital}, stop_loss={stop_loss}, take_profit={take_profit}, dry_run={dry_run}, config={self.config}")
        """
        Executa uma ordem de mercado ou simula em dry run.
        Agora faz log detalhado e vincula o signal_id local ao id da Binance e ao id da ordem dry run.

        Args:
            par (str): Par de negociação (ex.: "DOGEUSDT").
            direcao (str): Direção da ordem ("LONG" ou "SHORT").
            capital (float): Capital para a ordem em USDT.
            stop_loss (float): Percentual de stop loss.
            take_profit (float): Percentual de take profit.
            mercado (str): Tipo de mercado (default: 'futures').
            dry_run (bool): Se True, simula a ordem sem executá-la.
            dry_run_id (str): ID da ordem dry run para vinculação cruzada.

        Returns:
            dict: Detalhes da ordem executada ou simulada.
        """
        # Checagem centralizada de limite de ordens por direção/par/timeframe/robô
        active_trades = check_active_trades()
        # Checagem de limite global e por robô
        if not check_global_and_robot_limit(self.config['strategy_name'], active_trades):
            logger.info(f"[DEBUG-ORDER_EXECUTOR] Motivo do bloqueio: Limite global (540) ou por robô (36) atingido para {self.config['strategy_name']}")
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
            logger.info(f"[DEBUG-ORDER_EXECUTOR] Motivo do bloqueio: Limite de trades simultâneos atingido para {self.config['strategy_name']} em {par}/{self.config['timeframe']}/{direcao}")
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
            logger.info(f"[DEBUG-ORDER_EXECUTOR] Motivo do bloqueio: Já existe uma ordem aberta para a estratégia {self.config['strategy_name']} na direção {direcao} e timeframe {self.config['timeframe']}")
            logger.warning(f"Já existe uma ordem aberta para a estratégia {self.config['strategy_name']} na direção {direcao} e timeframe {self.config['timeframe']}. Ordem não será criada.")
            # Registrar no log de oportunidades perdidas
            with open("oportunidades_perdidas.csv", "a") as f:
                f.write(f"{pd.Timestamp.now()},{self.config['strategy_name']},{par},{self.config['timeframe']},{direcao},N/A,N/A,Limite de trades simultâneos atingido\n")
            return {"status": "ignored", "reason": "existing open order for direction and timeframe"}

        if dry_run:
            logger.info(f"[DRY RUN] Simulando ordem {direcao} em {par} com capital {capital} USDT, SL: {stop_loss}%, TP: {take_profit}%, signal_id={dry_run_id}")
            return {"status": "simulated", "order_id": dry_run_id}

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
            binance_order_id = ordem.get('orderId')
            logger.info(f"[REAL ORDER] Ordem REAL executada: par={par}, direcao={direcao}, capital={capital}, quantidade={quantidade}, preco_entrada={preco}, binance_order_id={binance_order_id}, strategy={self.config.get('strategy_name')}, timeframe={self.config.get('timeframe')}")

            # Calcular preços de TP e SL
            sl_preco = preco * (1 - stop_loss / 100) if direcao == "LONG" else preco * (1 + stop_loss / 100)
            tp_preco = preco * (1 + take_profit / 100) if direcao == "LONG" else preco * (1 - take_profit / 100)

            # Criar ordens de TP e SL
            tp_order = self.client.futures_create_order(
                symbol=par,
                side=SIDE_SELL if direcao == "LONG" else SIDE_BUY,
                type=ORDER_TYPE_LIMIT,
                quantity=quantidade,
                price=tp_preco,
                stopPrice=tp_preco,
                timeInForce='GTC'
            )
            sl_order = self.client.futures_create_order(
                symbol=par,
                side=SIDE_SELL if direcao == "LONG" else SIDE_BUY,
                type=ORDER_TYPE_LIMIT,
                quantity=quantidade,
                price=sl_preco,
                stopPrice=sl_preco,
                timeInForce='GTC'
            )
            logger.info(f"[REAL ORDER] TP/SL criados: tp_order_id={tp_order.get('orderId')}, sl_order_id={sl_order.get('orderId')}, binance_order_id={binance_order_id}, signal_id={ordem.get('clientOrderId')}")

            # Vinculação de IDs: salva no CSV local
            df = pd.read_csv(SINALS_FILE)
            # Busca ordem aberta mais recente para este robô/par/timeframe/direcao
            idx = df[(df['estado'] == 'aberto') & (df['strategy_name'] == self.config['strategy_name']) & (df['par'] == par) & (df['direcao'] == direcao) & (df['timeframe'] == self.config['timeframe'])].index
            if len(idx) > 0:
                df.at[idx[-1], 'binance_order_id'] = binance_order_id
                df.at[idx[-1], 'tp_order_id'] = tp_order.get('orderId')
                df.at[idx[-1], 'sl_order_id'] = sl_order.get('orderId')
                if dry_run_id:
                    df.at[idx[-1], 'dry_run_id'] = dry_run_id
                df.to_csv(SINALS_FILE, index=False)
                logger.info(f"[VINCULO] Ordem local vinculada: signal_id={df.at[idx[-1], 'signal_id']}, binance_order_id={binance_order_id}, dry_run_id={dry_run_id}")
            else:
                logger.warning(f"[VINCULO] Não foi possível vincular binance_order_id ao signal_id local (ordem não encontrada no CSV)")

            return {
                "status": "executed",
                "binance_order_id": binance_order_id,
                "tp_order_id": tp_order.get('orderId'),
                "sl_order_id": sl_order.get('orderId'),
                "signal_id": ordem.get('clientOrderId'),
                "dry_run_id": dry_run_id
            }
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