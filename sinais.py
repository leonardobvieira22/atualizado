import pandas as pd
import numpy as np
import ta
import logging
import json

logger = logging.getLogger(__name__)

class SignalGenerator:
    def __init__(self, config):
        self.config = config
        self.indicators_config = config["backtest_config"]["indicators"]

    def calculate_indicators(self, df):
        if self.indicators_config["sma"]["enabled"]:
            df['sma_short'] = ta.trend.sma_indicator(df['close'], window=self.indicators_config["sma"]["short_window"])
            df['sma_long'] = ta.trend.sma_indicator(df['close'], window=self.indicators_config["sma"]["long_window"])
        if self.indicators_config["ema"]["enabled"]:
            df['ema_short'] = ta.trend.ema_indicator(df['close'], window=self.indicators_config["ema"]["short_window"])
            df['ema_long'] = ta.trend.ema_indicator(df['close'], window=self.indicators_config["ema"]["long_window"])
        if self.indicators_config["rsi"]["enabled"]:
            df['rsi'] = ta.momentum.rsi(df['close'], window=self.indicators_config["rsi"]["window"])
        if self.indicators_config["macd"]["enabled"]:
            macd = ta.trend.MACD(df['close'], window_slow=self.indicators_config["macd"]["slow"],
                                 window_fast=self.indicators_config["macd"]["fast"],
                                 window_sign=self.indicators_config["macd"]["signal"])
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
        if self.indicators_config["adx"]["enabled"]:
            df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=self.indicators_config["adx"]["window"])
        if self.indicators_config["volume"]["enabled"]:
            df['volume_sma'] = ta.trend.sma_indicator(df['volume'], window=14)
        return df

    def generate_signal(self, df, pair, timeframe, strategy_name, confidence_data=None):
        # Checagem de pausa de sinais
        try:
            with open("config.json", "r") as f:
                config_json = json.load(f)
            if config_json.get("pausar_sinais", False):
                logger.info("Geração de sinais pausada por configuração (pausar_sinais=true). Nenhum sinal será gerado.")
                return None
        except Exception as e:
            logger.error(f"Erro ao ler config.json para pausar_sinais: {e}")

        indicators = next(s["indicators"] for s in self.config["backtest_config"]["signal_strategies"] if s["name"] == strategy_name)
        score = 0
        reasons = []
        direction = None

        close = df['close'].iloc[-1]
        confidence = confidence_data.get("confidence", 0) if confidence_data else 0
        score += confidence * 10

        if "sma" in indicators and self.indicators_config["sma"]["enabled"]:
            sma_short = df['sma_short'].iloc[-1]
            sma_long = df['sma_long'].iloc[-1]
            if sma_short > sma_long:
                score += self.indicators_config["sma"]["score"]
                direction = "LONG"
                reasons.append(f"SMA10 > SMA50 (Diff: {((sma_short - sma_long) / sma_long * 100):.2f}%)")
            elif sma_short < sma_long:
                score += self.indicators_config["sma"]["score"]
                direction = "SHORT"
                reasons.append(f"SMA10 < SMA50 (Diff: {((sma_long - sma_short) / sma_long * 100):.2f}%)")

        if "ema" in indicators and self.indicators_config["ema"]["enabled"]:
            ema_short = df['ema_short'].iloc[-1]
            ema_long = df['ema_long'].iloc[-1]
            if ema_short > ema_long:
                score += self.indicators_config["ema"]["score"]
                direction = "LONG" if direction is None or direction == "LONG" else None
                reasons.append(f"EMA9 > EMA21 (Diff: {((ema_short - ema_long) / ema_long * 100):.2f}%)")
            elif ema_short < ema_long:
                score += self.indicators_config["ema"]["score"]
                direction = "SHORT" if direction is None or direction == "SHORT" else None
                reasons.append(f"EMA9 < EMA21 (Diff: {((ema_long - ema_short) / ema_long * 100):.2f}%)")

        if "rsi" in indicators and self.indicators_config["rsi"]["enabled"]:
            rsi = df['rsi'].iloc[-1]
            if rsi < self.indicators_config["rsi"]["oversold_threshold"]:
                score += self.indicators_config["rsi"]["score"]
                direction = "LONG" if direction is None or direction == "LONG" else None
                reasons.append(f"RSI Oversold: {rsi:.2f}")
            elif rsi > self.indicators_config["rsi"]["overbought_threshold"]:
                score += self.indicators_config["rsi"]["score"]
                direction = "SHORT" if direction is None or direction == "SHORT" else None
                reasons.append(f"RSI Overbought: {rsi:.2f}")

        if "macd" in indicators and self.indicators_config["macd"]["enabled"]:
            macd = df['macd'].iloc[-1]
            macd_signal = df['macd_signal'].iloc[-1]
            if macd > macd_signal:
                score += self.indicators_config["macd"]["score"]
                direction = "LONG" if direction is None or direction == "LONG" else None
                reasons.append("MACD Bullish Cross")
            elif macd < macd_signal:
                score += self.indicators_config["macd"]["score"]
                direction = "SHORT" if direction is None or direction == "SHORT" else None
                reasons.append("MACD Bearish Cross")

        if "adx" in indicators and self.indicators_config["adx"]["enabled"]:
            adx = df['adx'].iloc[-1]
            if adx > self.indicators_config["adx"]["threshold"]:
                score += self.indicators_config["adx"]["score"]
                reasons.append(f"ADX Trend Strength: {adx:.2f}")

        if "volume" in indicators and self.indicators_config["volume"]["enabled"]:
            volume = df['volume'].iloc[-1]
            volume_sma = df['volume_sma'].iloc[-1]
            if volume > volume_sma:
                score += self.indicators_config["volume"]["score"]
                reasons.append("Volume Above Average")

        if direction and score >= 50:
            indicator_scores = {ind: self.indicators_config[ind]["score"] for ind in indicators if self.indicators_config[ind]["enabled"]}
            max_score = sum(indicator_scores.values()) + 10
            normalized_score = min((score / max_score) * 100, 100)

            return {
                "direction": direction,
                "score": normalized_score,
                "reasons": reasons,
                "entry_price": close,
                "strategy": strategy_name,
                "tp_percent": max(self.indicators_config[ind]["tp_percent"] for ind in indicators),
                "sl_percent": max(self.indicators_config[ind]["sl_percent"] for ind in indicators)
            }
        logger.debug(f"Nenhum sinal gerado para {pair} ({timeframe}): score={score}")
        return None

    def format_signal_card(self, signal, quantity):
        confidence_data = {"win_rate": 0.615, "avg_pnl": 1.14, "signals": 39}  # Placeholder
        card = [
            "┌──────────────────────────────────────────────────────────────┐",
            f"│ [ULTRABOT] SINAL GERADO - {signal['par']} ({signal['timeframe']}) - {'COMPRA' if signal['direction'] == 'LONG' else 'VENDA'} ({signal['direction']})      │",
            "├──────────────────────────────────────────────────────────────┤",
            f"│ 🎯 Preço de Entrada: {signal['entry_price']:.4f} | Quantidade: {quantity:.2f}                │",
            f"│ 🎯 TP: +{signal['tp_percent']:.2f}% | SL: -{signal['sl_percent']:.2f}%                                   │",
            f"│ 🧠 Estratégia: {signal['strategy']}             │",
            "│                                                              │",
            "│ 📊 Indicadores:                                              │"
        ]
        for reason in signal["reasons"]:
            card.append(f"│    - 📊 {reason}      │")
        card.extend([
            "│                                                              │",
            "│ 📌 Motivos:                                                  │"
        ])
        for reason in signal["reasons"]:
            card.append(f"│    ✔ {reason}                                │")
        card.extend([
            "│                                                              │",
            f"│ 📈 Confiabilidade Histórica: {confidence_data['win_rate']*100:.1f}% de acerto em {confidence_data['signals']} sinais     │",
            f"│    PnL médio por sinal: +{confidence_data['avg_pnl']:.2f}%                               │",
            "│                                                              │",
            "│ ✅ SINAL ACEITO - Simulado (Dry-Run Interno)                 │",
            "└──────────────────────────────────────────────────────────────┘"
        ])
        return "\n".join(card)

class ExtendedTargetSignalGenerator(SignalGenerator):
    def __init__(self, config):
        super().__init__(config)
        # Buscar a estratégia "extended_target" pelo nome
        extended_strategy = next((s for s in config["backtest_config"]["signal_strategies"] if s["name"] == "extended_target"), None)
        if extended_strategy and "min_target_percent" in extended_strategy:
            self.min_target_percent = extended_strategy["min_target_percent"]
            self.stop_loss_percent = extended_strategy["stop_loss_percent"]
        else:
            # Valores padrão caso a estratégia não esteja presente ou incompleta
            logger.warning("Estratégia 'extended_target' não encontrada ou incompleta no config.json. Usando valores padrão.")
            self.min_target_percent = 3.0
            self.stop_loss_percent = 1.0

    def generate_extended_signal(self, df_primary, df_confirmation, df_timing, pair, timeframe, strategy_name, confidence_data=None):
        """Gera sinais para movimentos > 3%."""
        score = 0
        reasons = []
        direction = None

        ema_short = df_primary['ema_short'].iloc[-1]
        ema_long = df_primary['ema_long'].iloc[-1]
        adx = df_primary['adx'].iloc[-1]
        macd = df_primary['macd'].iloc[-1]
        macd_signal = df_primary['macd_signal'].iloc[-1]
        rsi = df_primary['rsi'].iloc[-1]

        if ema_short > ema_long and adx > 25 and macd > macd_signal and rsi > 50:
            direction = "LONG"
            score += 60
            reasons.append(f"EMA9 > EMA21 (Diff: {((ema_short - ema_long) / ema_long * 100):.2f}%), ADX={adx:.2f}, MACD positivo, RSI={rsi:.2f}")
        elif ema_short < ema_long and adx > 25 and macd < macd_signal and rsi < 50:
            direction = "SHORT"
            score += 60
            reasons.append(f"EMA9 < EMA21 (Diff: {((ema_long - ema_short) / ema_long * 100):.2f}%), ADX={adx:.2f}, MACD negativo, RSI={rsi:.2f}")
        else:
            logger.debug(f"Tendência não confirmada para {pair} ({timeframe}): EMA9={ema_short}, EMA21={ema_long}, ADX={adx}, RSI={rsi}")
            return None

        ema_short_1d = df_confirmation['ema_short'].iloc[-1]
        ema_long_1d = df_confirmation['ema_long'].iloc[-1]
        if (direction == "LONG" and ema_short_1d <= ema_long_1d) or (direction == "SHORT" and ema_short_1d >= ema_long_1d):
            logger.debug(f"Tendência 1D não alinhada para {pair}: EMA9_1D={ema_short_1d}, EMA21_1D={ema_long_1d}")
            return None
        score += 20
        reasons.append("Tendência confirmada no 1D")

        volume_current = df_primary['volume'].iloc[-1]
        volume_prev = df_primary['volume'].iloc[-2]
        if volume_current > volume_prev:
            score += 10
            reasons.append("Volume crescente")
        else:
            logger.debug(f"Volume não crescente para {pair} ({timeframe}): {volume_current} <= {volume_prev}")
            return None

        high_prev = df_primary['high'].iloc[-2]
        low_prev = df_primary['low'].iloc[-2]
        close = df_primary['close'].iloc[-1]
        if direction == "LONG" and close > high_prev:
            score += 10
            reasons.append("Rompimento de máxima anterior")
        elif direction == "SHORT" and close < low_prev:
            score += 10
            reasons.append("Rompimento de mínima anterior")
        else:
            logger.debug(f"Sem rompimento para {pair} ({timeframe}): close={close}, high_prev={high_prev}, low_prev={low_prev}")
            return None

        if adx < 20 or (45 <= rsi <= 55) or (macd_signal - macd) > 0.01:
            logger.debug(f"Filtro de não entrada ativado para {pair} ({timeframe}): ADX={adx}, RSI={rsi}, MACD indeciso")
            return None

        if score >= 40:
            return {
                "direction": direction,
                "score": score,
                "reasons": reasons,
                "entry_price": close,
                "strategy": strategy_name,
                "tp_percent": self.min_target_percent,
                "sl_percent": self.stop_loss_percent,
                "type": "movimento_longo"
            }
        return None