import pandas as pd
import numpy as np
from utils import logger

def generate_signal(historical_data, timeframe, strategy_config, config, learning_engine, binance_utils):
    """
    Gera um sinal de compra (LONG) ou venda (SHORT) com base nos indicadores da estratégia.
    """
    try:
        # Substituir 'unknown' por um valor mais informativo e adicionar validações
        strategy_name = strategy_config.get('name')
        if not strategy_name:
            logger.warning("Nome da estratégia não definido. Usando valor padrão.")
            strategy_name = "Estratégia Desconhecida"
        if not strategy_name or strategy_name == "Estratégia Desconhecida":
            logger.error("Estratégia inválida ou desconhecida detectada. Ignorando processamento.")
            return None, 0.0, {}, "", "Estratégia Inválida"
        indicators = strategy_config.get('indicators', strategy_config.get('indicadores_ativos', []))
        if isinstance(indicators, dict):
            indicators = [ind for ind, active in indicators.items() if active]
        if not indicators:
            logger.warning(f"Nenhum indicador definido para a estratégia {strategy_name}.")
            return None, 0.0, {}, "", strategy_name

        score_tecnico = 0.0
        reasons = []
        locators = {}
        contributing_indicators = []

        # Configurações específicas da estratégia
        score_tecnico_min = strategy_config.get('score_tecnico_min', config.get('score_tecnico_min', 0.05))
        ml_confidence_min = strategy_config.get('ml_confidence_min', config.get('ml_confidence_min', 0.2))

        # Verificar colunas disponíveis
        required_columns = ['EMA12', 'EMA50', 'RSI', 'MACD', 'MACD_Signal', 'close']  # Ajustado para EMA12 e EMA50
        available_columns = [col for col in required_columns if col in historical_data.columns]
        missing_columns = [col for col in required_columns if col not in historical_data.columns]
        if missing_columns:
            logger.error(f"Colunas ausentes para {strategy_name} ({timeframe}): {missing_columns}")
            logger.debug(f"Colunas disponíveis: {historical_data.columns.tolist()}")
        
        # Logar dados históricos
        logger.debug(f"Dados para {strategy_name} ({timeframe}): {historical_data.tail(1)[available_columns].to_dict()}")

        # EMA
        if 'EMA' in indicators and 'EMA12' in historical_data.columns and 'EMA50' in historical_data.columns:
            ema12 = historical_data['EMA12'].iloc[-1]
            ema50 = historical_data['EMA50'].iloc[-1]
            if pd.notna(ema12) and pd.notna(ema50):
                if ema12 > ema50:
                    score_tecnico += 0.3
                    reasons.append("EMA12 cruzou acima de EMA50")
                    locators['EMA12>EMA50'] = True
                    contributing_indicators.append('EMA')
                elif ema12 < ema50:
                    score_tecnico += 0.2
                    reasons.append("EMA12 abaixo de EMA50")
                    locators['EMA12<EMA50'] = True
                    contributing_indicators.append('EMA')
                logger.debug(f"EMA para {strategy_name}: EMA12={ema12:.4f}, EMA50={ema50:.4f}, Score={score_tecnico:.2f}")
            else:
                logger.warning(f"EMA inválido para {strategy_name}: EMA12={ema12}, EMA50={ema50}")

        # RSI
        if 'RSI' in indicators and 'RSI' in historical_data.columns:
            rsi = historical_data['RSI'].iloc[-1]
            if pd.notna(rsi):
                if rsi < 45:
                    score_tecnico += 0.3
                    reasons.append(f"RSI sobrevendido: {rsi:.2f}")
                    locators['RSI_Sobrevendido'] = True
                    contributing_indicators.append('RSI')
                elif rsi > 60:  # Ajustado para 60
                    score_tecnico += 0.2
                    reasons.append(f"RSI sobrecomprado: {rsi:.2f}")
                    locators['RSI_Sobrecomprado'] = True
                    contributing_indicators.append('RSI')
                logger.debug(f"RSI para {strategy_name}: RSI={rsi:.2f}, Score={score_tecnico:.2f}")
            else:
                logger.warning(f"RSI inválido para {strategy_name}: RSI={rsi}")

        # MACD
        if 'MACD' in indicators and 'MACD' in historical_data.columns and 'MACD_Signal' in historical_data.columns:
            macd = historical_data['MACD'].iloc[-1]
            macd_signal = historical_data['MACD_Signal'].iloc[-1]
            macd_prev = historical_data['MACD'].iloc[-2] if len(historical_data) > 1 else np.nan
            macd_signal_prev = historical_data['MACD_Signal'].iloc[-2] if len(historical_data) > 1 else np.nan
            if all(pd.notna([macd, macd_signal, macd_prev, macd_signal_prev])):
                if macd > macd_signal and macd_prev <= macd_signal_prev:
                    score_tecnico += 0.3
                    reasons.append("MACD cruzou acima da linha de sinal")
                    locators['MACD_Cruzamento_Alta'] = True
                    contributing_indicators.append('MACD')
                elif macd < macd_signal and macd_prev >= macd_signal_prev:
                    score_tecnico += 0.2
                    reasons.append("MACD cruzou abaixo da linha de sinal")
                    locators['MACD_Cruzamento_Baixa'] = True
                    contributing_indicators.append('MACD')
                logger.debug(f"MACD para {strategy_name}: MACD={macd:.4f}, Signal={macd_signal:.4f}, Score={score_tecnico:.2f}")
            else:
                logger.warning(f"MACD inválido para {strategy_name}: MACD={macd}, Signal={macd_signal}")

        # Swing Trade Composite
        if 'Swing Trade Composite' in indicators and 'close' in historical_data.columns:
            close = historical_data['close'].iloc[-1]
            ma20 = historical_data['close'].rolling(window=20).mean().iloc[-1]
            if pd.notna(close) and pd.notna(ma20):
                if close > ma20:
                    score_tecnico += 0.4
                    reasons.append("Preço acima da média de 20 períodos")
                    locators['Swing_Trade_Long'] = True
                    contributing_indicators.append('Swing Trade Composite')
                elif close < ma20:
                    score_tecnico += 0.3
                    reasons.append("Preço abaixo da média de 20 períodos")
                    locators['Swing_Trade_Short'] = True
                    contributing_indicators.append('Swing Trade Composite')
                logger.debug(f"Swing Trade para {strategy_name}: Close={close:.4f}, MA20={ma20:.4f}, Score={score_tecnico:.2f}")
            else:
                logger.warning(f"Swing Trade inválido para {strategy_name}: Close={close}, MA20={ma20}")

        # Machine Learning
        ml_confidence = 0.0
        if config.get('learning_enabled', False):
            try:
                prediction = learning_engine.predict(historical_data)
                ml_confidence = prediction.get('confidence', 0.0)
                if ml_confidence >= ml_confidence_min:
                    score_tecnico += ml_confidence * 0.3
                    reasons.append(f"Modelo ML confiante: {ml_confidence:.2f}")
                    locators['ML_Confidence'] = ml_confidence
                logger.debug(f"ML para {strategy_name}: Confidence={ml_confidence:.2f}, Score={score_tecnico:.2f}")
            except Exception as e:
                logger.warning(f"Erro ao obter previsão do modelo ML: {e}")

        # Determinar direção
        direction = None
        if score_tecnico >= score_tecnico_min:
            if any(key in locators for key in ['EMA12>EMA50', 'RSI_Sobrevendido', 'MACD_Cruzamento_Alta', 'Swing_Trade_Long']):
                direction = "LONG"
            elif any(key in locators for key in ['EMA12<EMA50', 'RSI_Sobrecomprado', 'MACD_Cruzamento_Baixa', 'Swing_Trade_Short']):
                direction = "SHORT"

        details = {
            "reasons": reasons,
            "locators": locators,
            "historical_win_rate": 0.0,
            "avg_pnl": 0.0
        }

        logger.info(f"Resultado para {strategy_name} ({timeframe}): Direction={direction}, Score={score_tecnico:.2f}, Reasons={reasons}, Indicators={contributing_indicators}")

        return direction, score_tecnico, details, ";".join(contributing_indicators), strategy_name

    except Exception as e:
        logger.error(f"Erro ao gerar sinal para {strategy_config.get('name', 'unknown')}: {e}")
        return None, 0.0, {}, "", strategy_config.get('name', 'unknown')

def generate_multi_timeframe_signal(signals_by_tf, learning_engine, contributing_indicators):
    """
    Combina sinais de diferentes timeframes para gerar um sinal final.
    """
    try:
        if not signals_by_tf:
            logger.debug("Nenhum sinal por timeframe disponível para análise multi-timeframe.")
            return None, 0.0, {}

        direction_counts = {"LONG": 0, "SHORT": 0}
        total_score = 0.0
        reasons = []
        timeframes_analisados = list(signals_by_tf.keys())

        for tf, signal_data in signals_by_tf.items():
            direction = signal_data['direction']
            score = signal_data['score']
            tf_weight = 1.0 / (timeframes_analisados.index(tf) + 1)
            direction_counts[direction] += tf_weight
            total_score += score * tf_weight
            reasons.extend(signal_data['details'].get('reasons', []))

        long_score = direction_counts["LONG"]
        short_score = direction_counts["SHORT"]
        final_direction = None
        if long_score > short_score and long_score > 0:
            final_direction = "LONG"
        elif short_score > long_score and short_score > 0:
            final_direction = "SHORT"

        multi_tf_confidence = max(long_score, short_score) / sum(direction_counts.values()) if sum(direction_counts.values()) > 0 else 0.0
        multi_tf_details = {
            "multi_tf_confidence": multi_tf_confidence,
            "timeframes_analisados": timeframes_analisados,
            "reasons": reasons
        }

        logger.debug(f"Sinal multi-timeframe: Direction={final_direction}, Score={total_score:.2f}, Confidence={multi_tf_confidence:.2f}")

        return final_direction, total_score, multi_tf_details

    except Exception as e:
        logger.error(f"Erro ao gerar sinal multi-timeframe: {e}")
        return None, 0.0, {}

def calculate_signal_quality(historical_data, signal_data, binance_utils):
    """
    Calcula uma pontuação de qualidade para o sinal.
    Args:
        historical_data (pd.DataFrame): Dados históricos do par/timeframe.
        signal_data (dict): Dados do sinal gerado.
        binance_utils (BinanceUtils): Instância de BinanceUtils para cálculos.
    Returns:
        float: Pontuação de qualidade (0 a 1).
    """
    try:
        # Score técnico (já calculado)
        score_tecnico = signal_data['score_tecnico']

        # Volatilidade (usando ATR)
        atr = historical_data['close'].pct_change().rolling(window=14).std().iloc[-1] * (252 ** 0.5)  # Volatilidade anualizada
        atr_normalized = min(atr * 100, 1.0) if pd.notna(atr) else 0.0  # Normaliza para 0-1

        # Volume
        volume_avg = historical_data['volume'].rolling(window=20).mean().iloc[-1]
        volume_max = historical_data['volume'].rolling(window=100).max().iloc[-1]
        volume_score = volume_avg / volume_max if volume_max > 0 else 0.0

        # Desempenho histórico
        historical_win_rate = signal_data['historical_win_rate']
        avg_pnl = signal_data['avg_pnl']
        historical_score = (historical_win_rate / 100) * (1 + avg_pnl / 100)

        # Pontuação final (ponderada)
        quality_score = (
            0.4 * score_tecnico +
            0.2 * atr_normalized +
            0.2 * volume_score +
            0.2 * historical_score
        )
        return min(max(quality_score, 0.0), 1.0)
    except Exception as e:
        logger.error(f"Erro ao calcular qualidade do sinal: {e}")
        return 0.0