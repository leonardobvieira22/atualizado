import pickle
import pandas as pd
import numpy as np
import os
import json
from sklearn.linear_model import LogisticRegression
from utils import logger
from strategy_manager import load_strategies, save_strategies

class LearningEngine:
    def __init__(self, model_path="learning_model.pkl"):
        self.model_path = model_path
        self.model = None
        self.accuracy = 0.57  # Valor inicial conforme logs
        self.features = ['EMA9', 'EMA21', 'RSI', 'MACD', 'MACD_Signal']
        self.look_back = 10  # Valor padrão para look_back, ajuste conforme necessário
        logger.info("Inicializando LearningEngine...")
        self.load_model()

    def load_model(self):
        try:
            logger.info(f"Verificando se o arquivo do modelo existe: {self.model_path}")
            if os.path.exists(self.model_path):
                logger.info(f"Arquivo {self.model_path} encontrado. Carregando modelo...")
                with open(self.model_path, 'rb') as f:
                    self.model = pickle.load(f)
                logger.info("Modelo de aprendizado carregado com sucesso.")
            else:
                logger.warning(f"Arquivo {self.model_path} não encontrado. Modelo será inicializado como None.")
            logger.info("LearningEngine inicializado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao carregar o modelo: {e}")
            self.model = None

    def train(self):
        try:
            logger.info("Iniciando treinamento do modelo de aprendizado...")
            if not os.path.exists("sinais_detalhados.csv"):
                logger.warning("Arquivo sinais_detalhados.csv não existe. Não é possível treinar o modelo.")
                return

            df = pd.read_csv("sinais_detalhados.csv")
            if df.empty:
                logger.warning("Arquivo sinais_detalhados.csv está vazio. Não é possível treinar o modelo.")
                return

            # Extrair parâmetros
            df_params = df['parametros'].apply(lambda x: json.loads(x) if pd.notna(x) else {})
            df_features = pd.DataFrame()
            for feature in self.features:
                df_features[feature] = df[feature] if feature in df.columns else 0.0
            X = df_features.fillna(0)
            y = df['resultado'].apply(lambda x: 1 if x == 'TP' else 0)

            if len(X) < 2:
                logger.warning("Dados insuficientes para treinamento (menos de 2 amostras).")
                return

            self.model = LogisticRegression(max_iter=1000)
            self.model.fit(X, y)
            self.accuracy = self.model.score(X, y)
            logger.info(f"Modelo treinado com sucesso. Acurácia: {self.accuracy:.2f}")

            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
            logger.info(f"Modelo salvo em {self.model_path}")
        except Exception as e:
            logger.error(f"Erro ao treinar o modelo: {e}")

    def predict(self, historical_data):
        try:
            logger.debug("Gerando previsão com o modelo de aprendizado...")
            if self.model is None:
                logger.warning("Modelo não está treinado. Retornando confiança padrão.")
                return {"confidence": 0.0}

            if isinstance(historical_data, dict):
                data = {k: historical_data.get(k, 0.0) for k in self.features}
                X = pd.DataFrame([data])
            else:
                available_features = [f for f in self.features if f in historical_data.columns]
                if not available_features:
                    logger.warning("Nenhum indicador disponível para previsão.")
                    return {"confidence": 0.0}
                X = historical_data[available_features].fillna(0).iloc[-1:]
                for feature in self.features:
                    if feature not in X.columns:
                        X[feature] = 0.0
                X = X[self.features]

            if X.empty:
                logger.warning("Dados históricos vazios para previsão.")
                return {"confidence": 0.0}

            confidence = self.model.predict_proba(X)[0][1] if hasattr(self.model, 'predict_proba') else 0.5
            logger.debug(f"Previsão gerada: Confiança = {confidence:.2f}")
            return {"confidence": float(confidence)}
        except Exception as e:
            logger.error(f"Erro ao obter previsão do modelo ML: {e}")
            return {"confidence": 0.0}

    def adjust_strategy_parameters(self, strategy_name, performance_data):
        """
        Ajusta os parâmetros da estratégia com base no desempenho.
        Args:
            strategy_name (str): Nome da estratégia.
            performance_data (dict): Dados de desempenho (win_rate, avg_pnl, total_orders).
        """
        try:
            win_rate = performance_data.get('win_rate', 0)
            strategies = load_strategies()
            if strategy_name in strategies:
                strategy = strategies[strategy_name]
                if win_rate < 40:  # Se a taxa de acertos for baixa
                    strategy['score_tecnico_min'] = strategy.get('score_tecnico_min', 0.3) + 0.1
                    strategy['score_tecnico_min'] = min(strategy['score_tecnico_min'], 1.0)
                    logger.info(f"Aumentando score_tecnico_min para {strategy['score_tecnico_min']} na estratégia {strategy_name}")
                elif win_rate > 80:  # Se a taxa de acertos for alta
                    strategy['score_tecnico_min'] = max(strategy.get('score_tecnico_min', 0.3) - 0.05, 0.1)
                    logger.info(f"Reduzindo score_tecnico_min para {strategy['score_tecnico_min']} na estratégia {strategy_name}")
                strategies[strategy_name] = strategy
                save_strategies(strategies)
        except Exception as e:
            logger.error(f"Erro ao ajustar parâmetros da estratégia {strategy_name}: {e}")