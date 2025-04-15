import logging
import pandas as pd
import os
import time
import requests
import unicodedata

# Configuração do logger
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - UltraBot - %(levelname)s - %(message)s"
)
logger = logging.getLogger("UltraBot")

# Classe para escrita em arquivos CSV
class CsvWriter:
    def __init__(self, filename, columns):
        """
        Inicializa o escritor de CSV.
        Args:
            filename (str): Nome do arquivo CSV.
            columns (list): Lista de colunas do CSV.
        """
        self.filename = filename
        self.columns = columns
        self.initialize_csv()

    def initialize_csv(self):
        """
        Inicializa o arquivo CSV com as colunas especificadas, se ele não existir.
        """
        if not os.path.exists(self.filename):
            df = pd.DataFrame(columns=self.columns)
            df.to_csv(self.filename, index=False)
            logger.info(f"Arquivo CSV {self.filename} inicializado com colunas: {self.columns}")

    def write_row(self, data):
        """
        Escreve uma linha no arquivo CSV.
        Args:
            data (dict): Dicionário com os dados a serem escritos (deve corresponder às colunas).
        """
        try:
            # Carregar o DataFrame existente
            if os.path.exists(self.filename) and os.path.getsize(self.filename) > 0:
                df = pd.read_csv(self.filename)
            else:
                df = pd.DataFrame(columns=self.columns)

            # Criar a nova linha como DataFrame
            new_row = pd.DataFrame([data], columns=self.columns)

            # Garantir que os tipos de dados sejam consistentes
            for col in self.columns:
                if col in df and col in new_row:
                    # Converter para o mesmo tipo de dado que o DataFrame existente
                    if pd.api.types.is_numeric_dtype(df[col].dtype):
                        new_row[col] = pd.to_numeric(new_row[col], errors='coerce')
                    elif pd.api.types.is_datetime64_any_dtype(df[col].dtype):
                        new_row[col] = pd.to_datetime(new_row[col], errors='coerce')
                    else:
                        new_row[col] = new_row[col].astype(str)

            # Concatenar os DataFrames
            df = pd.concat([df, new_row], ignore_index=True)

            # Salvar no arquivo CSV
            df.to_csv(self.filename, index=False)
            logger.info(f"Linha escrita no arquivo {self.filename}: {data}")
        except Exception as e:
            logger.error(f"Erro ao escrever no arquivo {self.filename}: {e}")

# Função para inicializar arquivos CSV
def initialize_csv_files():
    """
    Inicializa os arquivos CSV necessários para o sistema.
    """
    sinais_columns = [
        'signal_id', 'par', 'direcao', 'preco_entrada', 'preco_saida', 'quantity',
        'lucro_percentual', 'pnl_realizado', 'resultado', 'timestamp', 'timestamp_saida',
        'estado', 'strategy_name', 'contributing_indicators', 'localizadores',
        'motivos', 'timeframe', 'aceito', 'parametros'
    ]
    missed_columns = [
        'timestamp', 'robot_name', 'par', 'timeframe', 'direcao', 'score_tecnico',
        'contributing_indicators', 'reason'
    ]
    CsvWriter("sinais_detalhados.csv", sinais_columns)
    CsvWriter("oportunidades_perdidas.csv", missed_columns)
    logger.info("Arquivos CSV inicializados com sucesso.")

# Função para chamadas à API com retry
def api_call_with_retry(func, max_retries=3, delay=5, *args, **kwargs):
    """
    Executa uma chamada à API com tentativas de retry em caso de falha.
    Args:
        func: Função da API a ser chamada.
        max_retries (int): Número máximo de tentativas.
        delay (int): Tempo de espera entre tentativas (em segundos).
        *args, **kwargs: Argumentos para a função da API.
    Returns:
        Resultado da chamada à API ou None em caso de falha.
    """
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"Erro na chamada à API (tentativa {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"Aguardando {delay} segundos antes da próxima tentativa...")
                time.sleep(delay)
            else:
                logger.error("Número máximo de tentativas atingido. Falha na chamada à API.")
                return None

# Função para gerar o resumo do motivo do sinal
def gerar_resumo(indicadores, valores):
    """
    Gera um resumo textual com base nos indicadores e seus valores.
    Args:
        indicadores (list): Lista de indicadores utilizados (ex.: ["EMA", "MACD"]).
        valores (dict): Dicionário com os valores dos indicadores.
    Returns:
        str: Resumo textual dos motivos do sinal.
    """
    resumo = []
    if "EMA" in indicadores:
        if valores.get("EMA9>EMA21", False):
            resumo.append("Tendência de alta pelo cruzamento de EMAs")
        elif valores.get("EMA9<EMA21", False):
            resumo.append("Tendência de baixa pelo cruzamento de EMAs")
    if "MACD" in indicadores:
        if valores.get("MACD Cruzamento Alta", False):
            resumo.append("MACD indicando alta")
        elif valores.get("MACD Cruzamento Baixa", False):
            resumo.append("MACD indicando baixa")
    if "RSI" in indicadores:
        if valores.get("RSI Sobrevendido", False):
            resumo.append("RSI em sobrevenda")
        elif valores.get("RSI Sobrecomprado", False):
            resumo.append("RSI em sobrecompra")
    if "Swing Trade Composite" in indicadores:
        if valores.get("Swing_Trade_Composite_LONG", False):
            resumo.append("Swing Trade Composite indicando alta")
        elif valores.get("Swing_Trade_Composite_SHORT", False):
            resumo.append("Swing Trade Composite indicando baixa")
    if "ML_Confidence" in valores:
        resumo.append(f"Confiança ML: {valores['ML_Confidence']}")
    return ", ".join(resumo) if resumo else "Motivo não especificado"

# Função para calcular confiabilidade histórica
def calcular_confiabilidade_historica(strategy, direction, df_closed):
    """
    Calcula a confiabilidade histórica e o PnL médio de uma estratégia.
    Args:
        strategy (str): Nome da estratégia.
        direction (str): Direção da ordem (ex.: "LONG", "SHORT").
        df_closed (pd.DataFrame): DataFrame com ordens fechadas.
    Returns:
        tuple: (win_rate, avg_pnl, total_signals).
    """
    ordens_passadas = df_closed[
        (df_closed["strategy_name"] == strategy) & (df_closed["direcao"] == direction)
    ]
    if len(ordens_passadas) == 0:
        return 0, 0, 0
    acertos = len(ordens_passadas[ordens_passadas["pnl_realizado"] > 0])
    win_rate = (acertos / len(ordens_passadas)) * 100 if len(ordens_passadas) > 0 else 0
    avg_pnl = ordens_passadas["pnl_realizado"].mean() if len(ordens_passadas) > 0 else 0
    total_signals = len(ordens_passadas)
    return round(win_rate, 2), round(avg_pnl, 2), total_signals

def normalize_strategy_name(name: str) -> str:
    """
    Normaliza o nome da estratégia para padronização em todo o sistema.
    Remove acentos, converte para minúsculas, remove espaços extras e caracteres especiais.
    Args:
        name (str): Nome original da estratégia.
    Returns:
        str: Nome normalizado.
    """
    if not isinstance(name, str):
        return ""
    # Remove acentos
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    # Converte para minúsculas
    name = name.lower()
    # Remove espaços extras e caracteres especiais comuns
    name = name.strip().replace(' ', '_')
    name = ''.join(c for c in name if c.isalnum() or c == '_')
    return name