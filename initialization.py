import os
import json
import subprocess
import socket
import psutil
import requests
import time
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from binance.client import Client
from binance.exceptions import BinanceAPIException
from utils import logger, api_call_with_retry

CONFIG_FILE = "config.json"

@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(5),
    retry=retry_if_exception_type(Exception)
)
def inicializar_client(api_key, api_secret, testnet=False):
    logger.info(f"Inicializando cliente da Binance: testnet={testnet}...")
    if not api_key or not api_secret:
        logger.warning(f"Chaves API não definidas: api_key={api_key}, api_secret={api_secret}, testnet={testnet}.")
        return None
    try:
        client = Client(api_key, api_secret, testnet=testnet, requests_params={"timeout": 30})
        logger.info(f"Cliente inicializado com sucesso: testnet={testnet}")
        return client
    except Exception as e:
        logger.warning(f"Falha ao inicializar cliente (testnet={testnet}): {e}.")
        raise

def is_port_in_use(port):
    logger.info(f"Verificando se a porta {port} está em uso...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", port))
            logger.info(f"Porta {port} está livre.")
            return False
        except socket.error:
            logger.info(f"Porta {port} está em uso.")
            return True

def kill_process_on_port(port):
    logger.info(f"Tentando liberar a porta {port}...")
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.net_connections(kind='inet'):
                if conn.laddr.port == port:
                    logger.warning(f"Porta {port} em uso pelo processo {proc.name()} (PID: {proc.pid}). Encerrando processo...")
                    proc.kill()
                    logger.info(f"Processo com PID {proc.pid} na porta {port} foi finalizado.")
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    logger.warning(f"Nenhum processo encontrado usando a porta {port}.")
    return False

def check_dashboard_availability(url, timeout=30):
    logger.info(f"Verificando disponibilidade do dashboard em {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                logger.info(f"Dashboard está disponível em {url}.")
                return True
        except requests.exceptions.RequestException:
            logger.debug(f"Dashboard ainda não está disponível em {url}. Aguardando...")
        time.sleep(1)
    logger.warning(f"Timeout atingido. Dashboard não está disponível em {url} após {timeout} segundos.")
    return False

def check_api_status(real_api_key, real_api_secret):
    logger.info("Executando check_api_status()...")
    real_status = {"connected": False, "permissions": {}, "client": None}
    if real_api_key and real_api_secret:
        real_client = inicializar_client(real_api_key, real_api_secret, testnet=False)
        if real_client:
            try:
                permissions = api_call_with_retry(real_client.get_account_api_permissions)
                real_status["connected"] = True
                real_status["permissions"] = {
                    "read": permissions.get("enableReading", False),
                    "spot": permissions.get("enableSpotTrading", False),
                    "futures": permissions.get("enableFutures", False)
                }
                real_status["client"] = real_client
                logger.info("Chave Real conectada com sucesso.")
            except BinanceAPIException as e:
                real_status["connected"] = False
                real_status["error"] = str(e)
                logger.error(f"Erro ao verificar chave Real: {e}")
            except Exception as e:
                real_status["connected"] = False
                real_status["error"] = str(e)
                logger.error(f"Erro inesperado ao verificar chave Real: {e}")
        else:
            logger.error("Falha ao inicializar cliente para verificar chave Real.")
    else:
        logger.error("Chave API Real não definida corretamente no config.py. O bot precisa da chave real para obter preços.")
        raise SystemExit(1)

    logger.info(f"Status da API verificado: {real_status}")
    return real_status

def load_config(pairs):
    logger.info("Carregando configurações com load_config()...")
    default_quantities = {"DOGEUSDT": 1.0, "XRPUSDT": 0.1, "TRXUSDT": 1.0}
    default_config = {
        "tp_percent": 2.0,
        "sl_percent": 1.0,
        "leverage": 20,
        "quantities": default_quantities,
        "quantities_usdt": {pair: 10.0 for pair in pairs},
        "quantity_in_usdt": False,
        "modes": {
            "real": False,
            "dry_run": True,
            "backtest": False
        },
        "backtest_start_date": "2025-03-01",
        "backtest_end_date": "2025-04-01",
        "price_cache_duration": 5,
        "backtest_funding_rate": 0.0001,
        "backtest_config": {
            "signal_strategies": [
                {"name": "all", "indicators": ["sma", "ema", "rsi", "macd"], "enabled": True},
                {"name": "sma_rsi", "indicators": ["sma", "rsi"], "enabled": True},
                {"name": "ema_macd", "indicators": ["ema", "macd"], "enabled": True},
                {"name": "extended_target", "indicators": ["ema"], "enabled": True}
            ],
            "slippage_percent": 0.1,
            "fee_percent": 0.04
        },
        "indicators": {
            "sma": {"score": 15, "enabled": True},
            "ema": {"score": 20, "enabled": True},
            "rsi": {"score": 30, "sobrevendido": 30, "sobrecomprado": 70, "enabled": True},
            "macd": {"score": 25, "enabled": True},
            "adx": {"score": 15, "threshold": 25, "enabled": True},
            "volume": {"score": 15, "enabled": True},
            "bollinger": {"score": 25, "enabled": True},
            "estocastico": {"score": 25, "enabled": True},
            "vwap": {"score": 20, "enabled": True},
            "obv": {"score": 20, "enabled": True},
            "fibonacci": {"score": 25, "enabled": True},
            "sentimento": {"score": 20, "enabled": True}
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]
            if "quantities" not in config:
                config["quantities"] = default_quantities
            if "quantities_usdt" not in config:
                config["quantities_usdt"] = default_config["quantities_usdt"]
            if "quantity_in_usdt" not in config:
                config["quantity_in_usdt"] = default_config["quantity_in_usdt"]
            if "modes" not in config:
                config["modes"] = default_config["modes"]
            if "backtest_start_date" not in config:
                config["backtest_start_date"] = default_config["backtest_start_date"]
            if "backtest_end_date" not in config:
                config["backtest_end_date"] = default_config["backtest_end_date"]
            if "price_cache_duration" not in config:
                config["price_cache_duration"] = default_config["price_cache_duration"]
            if "backtest_funding_rate" not in config:
                config["backtest_funding_rate"] = default_config["backtest_funding_rate"]
            if "backtest_config" not in config or not config["backtest_config"].get("signal_strategies"):
                config["backtest_config"] = default_config["backtest_config"]
            if "indicators" not in config:
                config["indicators"] = default_config["indicators"]
            logger.info("Configuração carregada com sucesso.")
            return config
        except Exception as e:
            logger.error(f"Erro ao carregar config.json: {e}. Recriando com configurações padrão.")
            config = default_config
            save_config(config)
            return config
    else:
        logger.info("Arquivo config.json não encontrado. Criando com configurações padrão.")
        config = default_config
        save_config(config)
        return config

def save_config(config):
    logger.info("Salvando configurações em config.json...")
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info("Configuração salva com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao salvar config.json: {e}")