import asyncio
import json
import os
import pandas as pd
import aiohttp
from datetime import datetime
import schedule
import time
import logging
from dotenv import load_dotenv
from notification_manager import send_telegram_alert

logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")

class GrokPeriodicCheck:
    def __init__(self, data_dir="data", api_key=XAI_API_KEY):
        self.data_dir = data_dir
        self.api_key = api_key
        self.base_url = "https://api.x.ai/v1/chat/completions"
        self.last_check = {}
        self.cache_file = os.path.join(self.data_dir, "grok_insights_cache.json")
        self.ma_history = {pair: [] for pair in ["TRXUSDT", "DOGEUSDT", "XRPUSDT"]}
        self.pattern_history = {pair: [] for pair in ["TRXUSDT", "DOGEUSDT", "XRPUSDT"]}
        self.ma_study_file = os.path.join(self.data_dir, "ma_study.json")
        self.pattern_study_file = os.path.join(self.data_dir, "pattern_study.json")
        self.prediction_history = {pair: [] for pair in ["TRXUSDT", "DOGEUSDT", "XRPUSDT"]}
        self.prediction_study_file = os.path.join(self.data_dir, "prediction_study.json")
        os.makedirs(self.data_dir, exist_ok=True)

    async def fetch_data(self):
        try:
            ordens_df = pd.read_csv(os.path.join(self.data_dir, "sinais_detalhados.csv"))
            precos_df = pd.read_csv(os.path.join(self.data_dir, "precos_log.csv"))
            return ordens_df, precos_df
        except Exception as e:
            logger.error(f"Erro ao carregar dados: {e}")
            return None, None

    async def call_grok_api(self, prompt, pair):
        cache_key = f"{pair}_{datetime.now().strftime('%Y%m%d%H%M')}"
        cache = {}
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    cache = json.load(f)
            except Exception:
                cache = {}
        if cache_key in cache:
            logger.info(f"Usando cache para {pair}")
            return cache[cache_key]
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "grok-3-latest",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1200,
                "stream": False
            }
            try:
                async with session.post(self.base_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data["choices"][0]["message"]["content"]
                        cache[cache_key] = result
                        with open(self.cache_file, "w") as f:
                            json.dump(cache, f)
                        return result
                    else:
                        logger.error(f"Erro na API para {pair}: {response.status}")
                        return None
            except Exception as e:
                logger.error(f"Exceção na API para {pair}: {e}")
                return None

    def study_moving_averages(self, pair, close, volume, ema12, ema50, sma20, ema12_prev, ema50_prev, sma20_prev, crossover_ema, crossover_sma, volume_increase):
        study_data = {
            "timestamp": datetime.now().isoformat(),
            "pair": pair,
            "ema12": ema12,
            "ema50": ema50,
            "sma20": sma20,
            "crossover_ema": crossover_ema,
            "crossover_sma": crossover_sma,
            "volume_increase": volume_increase,
            "price_change": (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] if len(close) >= 2 else 0,
            "success": None
        }
        if crossover_ema != "none" or crossover_sma != "none":
            strength = "strong" if volume_increase > 0.2 else "weak"
            study_data["strength"] = strength
            study_data["context"] = (
                f"Cruzamento {crossover_ema} em EMA12/EMA50 e {crossover_sma} em SMA20/EMA50 "
                f"com aumento de volume de {volume_increase:.2%} (força: {strength})"
            )
        self.ma_history[pair].append(study_data)
        if len(self.ma_history[pair]) > 100:
            self.ma_history[pair] = self.ma_history[pair][-100:]
        try:
            with open(self.ma_study_file, "w") as f:
                json.dump(self.ma_history, f, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar estudo de médias móveis: {e}")
        return study_data.get("context", "Nenhum cruzamento significativo detectado")

    def study_market_patterns(self, pair, close, high, low, volume, ema12, ema50, rsi, macd, signal, adx, atr):
        pattern_data = {
            "timestamp": datetime.now().isoformat(),
            "pair": pair,
            "price": close.iloc[-1],
            "trend": "none",
            "channel": "none",
            "support": None,
            "resistance": None,
            "bottom": None,
            "top": None,
            "divergence": "none",
            "volume_increase": (volume.iloc[-1] - volume.iloc[-2]) / volume.iloc[-2] if volume.iloc[-2] > 0 else 0,
            "success": None
        }
        if ema12 > ema50 and close.iloc[-1] > ema50:
            pattern_data["trend"] = "bullish"
        elif ema12 < ema50 and close.iloc[-1] < ema50:
            pattern_data["trend"] = "bearish"
        highs = high[-10:]
        lows = low[-10:]
        if highs.is_monotonic_increasing and lows.is_monotonic_increasing:
            pattern_data["channel"] = "ascending"
        elif highs.is_monotonic_decreasing and lows.is_monotonic_decreasing:
            pattern_data["channel"] = "descending"
        else:
            pattern_data["channel"] = "horizontal"
        pattern_data["support"] = min(low[-20:]) if len(low) >= 20 else None
        pattern_data["resistance"] = max(high[-20:]) if len(high) >= 20 else None
        if close.iloc[-1] <= pattern_data["support"] * 1.01:
            pattern_data["bottom"] = "potential"
        if close.iloc[-1] >= pattern_data["resistance"] * 0.99:
            pattern_data["top"] = "potential"
        if len(close) >= 3:
            price_diff = close.iloc[-1] - close.iloc[-2]
            rsi_diff = rsi.iloc[-1] - rsi.iloc[-2]
            if price_diff < 0 and rsi_diff > 0:
                pattern_data["divergence"] = "bullish"
            elif price_diff > 0 and rsi_diff < 0:
                pattern_data["divergence"] = "bearish"
        strength = "strong" if pattern_data["volume_increase"] > 0.2 and adx > 25 else "weak"
        pattern_data["strength"] = strength
        pattern_data["context"] = (
            f"Tendência: {pattern_data['trend']}, Canal: {pattern_data['channel']}, "
            f"Suporte: {pattern_data['support']:.4f}, Resistência: {pattern_data['resistance']:.4f}, "
            f"Fundo: {pattern_data['bottom']}, Topo: {pattern_data['top']}, "
            f"Divergência: {pattern_data['divergence']}, Força: {strength}"
        )
        self.pattern_history[pair].append(pattern_data)
        if len(self.pattern_history[pair]) > 100:
            self.pattern_history[pair] = self.pattern_history[pair][-100:]
        try:
            with open(self.pattern_study_file, "w") as f:
                json.dump(self.pattern_history, f, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar estudo de padrões: {e}")
        return pattern_data["context"]

    def predict_movement(self, pair, close, high, low, volume, ema12, ema50, rsi, macd, signal, adx, atr):
        """Tenta prever o movimento com base em indicadores e padrões precoces."""
        prediction_data = {
            "timestamp": datetime.now().isoformat(),
            "pair": pair,
            "price": close.iloc[-1],
            "predicted_direction": "none",
            "confidence": 0.0,
            "reason": "Nenhum padrão preditivo detectado",
            "time_horizon": "5-10 minutes"
        }
        
        # Sinais precoces de movimento
        if ema12 > ema50 and rsi.iloc[-1] > rsi.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]:
            prediction_data["predicted_direction"] = "up"
            prediction_data["confidence"] = 0.7 if volume.iloc[-1] > volume.iloc[-2] else 0.5
            prediction_data["reason"] = (
                f"EMA12 acima de EMA50 com RSI subindo e MACD positivo sugere movimento ascendente. "
                f"Confiança ajustada por volume ({volume.iloc[-1]/volume.iloc[-2]:.2%} de aumento)."
            )
        elif ema12 < ema50 and rsi.iloc[-1] < rsi.iloc[-2] and macd.iloc[-1] < signal.iloc[-1]:
            prediction_data["predicted_direction"] = "down"
            prediction_data["confidence"] = 0.7 if volume.iloc[-1] > volume.iloc[-2] else 0.5
            prediction_data["reason"] = (
                f"EMA12 abaixo de EMA50 com RSI caindo e MACD negativo sugere movimento descendente. "
                f"Confiança ajustada por volume ({volume.iloc[-1]/volume.iloc[-2]:.2%} de aumento)."
            )
        elif atr.iloc[-1] > atr.iloc[-2] * 1.2 and adx.iloc[-1] > 20:  # Aumento de volatilidade
            if close.iloc[-1] < ema50:
                prediction_data["predicted_direction"] = "down"
                prediction_data["confidence"] = 0.6
                prediction_data["reason"] = (
                    f"Aumento de volatilidade (ATR) com preço abaixo de EMA50 e ADX (20) sugere movimento descendente."
                )
            elif close.iloc[-1] > ema50:
                prediction_data["predicted_direction"] = "up"
                prediction_data["confidence"] = 0.6
                prediction_data["reason"] = (
                    f"Aumento de volatilidade (ATR) com preço acima de EMA50 e ADX (20) sugere movimento ascendente."
                )
        
        self.prediction_history[pair].append(prediction_data)
        if len(self.prediction_history[pair]) > 100:
            self.prediction_history[pair] = self.prediction_history[pair][-100:]
        try:
            with open(self.prediction_study_file, "w") as f:
                json.dump(self.prediction_history, f, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar estudo preditivo: {e}")
        return prediction_data

    def calculate_atr(self, high, low, close, period=14):
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr

    async def analyze_market(self):
        ordens_df, precos_df = await self.fetch_data()
        if ordens_df is None or precos_df is None:
            return
        for pair in ["TRXUSDT", "DOGEUSDT", "XRPUSDT"]:
            if pair in self.last_check and (datetime.now() - self.last_check[pair]).total_seconds() < 600:
                continue
            open_orders = ordens_df[(ordens_df["par"] == pair) & (ordens_df["estado"] == "aberto")]
            recent_precos = precos_df[(precos_df["par"] == pair) & (pd.to_datetime(precos_df["timestamp"]) > pd.Timestamp.now() - pd.Timedelta(minutes=60))]
            if recent_precos.empty:
                logger.info(f"Sem preços recentes para {pair}")
                continue
            close = recent_precos["close"]
            high = recent_precos["high"] if "high" in recent_precos else close
            low = recent_precos["low"] if "low" in recent_precos else close
            volume = recent_precos["volume"] if "volume" in recent_precos else pd.Series([0] * len(close))
            rsi = self.calculate_rsi(close, 14)
            ema12 = self.calculate_ema(close, 12).iloc[-1]
            ema50 = self.calculate_ema(close, 50).iloc[-1]
            sma20 = self.calculate_sma(close, 20).iloc[-1]
            macd, signal = self.calculate_macd(close)
            macd_val, signal_val = macd.iloc[-1], signal.iloc[-1]
            adx = self.calculate_adx(high, low, close, 14).iloc[-1]
            atr = self.calculate_atr(high, low, close, 14)
            previous_close = close.shift(1)
            ema12_prev = self.calculate_ema(previous_close, 12).iloc[-1]
            ema50_prev = self.calculate_ema(previous_close, 50).iloc[-1]
            sma20_prev = self.calculate_sma(previous_close, 20).iloc[-1]
            crossover_ema = "bullish" if ema12_prev < ema50_prev and ema12 > ema50 else "bearish" if ema12_prev > ema50_prev and ema12 < ema50 else "none"
            crossover_sma = "bullish" if sma20_prev < ema50_prev and sma20 > ema50 else "bearish" if sma20_prev > ema50_prev and sma20 < ema50 else "none"
            volume_increase = (volume.iloc[-1] - volume.iloc[-2]) / volume.iloc[-2] if volume.iloc[-2] > 0 else 0
            ma_study_context = self.study_moving_averages(
                pair, close, volume, ema12, ema50, sma20, ema12_prev, ema50_prev, sma20_prev,
                crossover_ema, crossover_sma, volume_increase
            )
            pattern_study_context = self.study_market_patterns(
                pair, close, high, low, volume, ema12, ema50, rsi, macd, signal, adx, atr
            )
            prediction_data = self.predict_movement(
                pair, close, high, low, volume, ema12, ema50, rsi, macd, signal, adx, atr
            )
            prompt = (
                f"UltraBot: Análise técnica para {pair} (10min).\n"
                f"Indicadores atuais:\n"
                f"- RSI: {rsi.iloc[-1]:.2f}\n"
                f"- EMA12: {ema12:.4f}, EMA50: {ema50:.4f}, Cruzamento EMA: {crossover_ema}\n"
                f"- SMA20: {sma20:.4f}, Cruzamento SMA: {crossover_sma}\n"
                f"- MACD: {macd_val:.4f}, Signal: {signal_val:.4f}\n"
                f"- ADX: {adx:.2f}\n"
                f"- Volume Aumento: {volume_increase:.2%}\n"
                f"- ATR (Volatilidade): {atr.iloc[-1]:.4f}\n"
                f"Preço atual: {close.iloc[-1]:.4f}\n"
                f"Previsão de Movimento: {prediction_data['predicted_direction']} com confiança {prediction_data['confidence']:.2%} ({prediction_data['reason']})\n"
                f"Ordens abertas: {len(open_orders)} (exemplo: {open_orders[['signal_id', 'direcao', 'preco_entrada']].to_dict('records')[:2] if not open_orders.empty else []})\n"
                f"Parâmetros: TP=0.75%, SL=0.75%, Leverage=10x\n"
                f"Estudo de Médias Móveis: {ma_study_context}\n"
                f"Estudo de Padrões de Mercado: {pattern_study_context}\n"
                f"Objetivo: Validar funcionamento, maximizar PNL, reduzir SLs e prever movimentos minutos antes.\n"
                f"Tarefas:\n"
                f"1. Detectar tendência (bullish/bearish/neutral) com base em cruzamentos, ADX, padrões e previsão.\n"
                f"2. Validar sinal (buy/sell/hold) considerando cruzamentos, RSI, MACD, volume, ATR, fundos, topos, canais, divergências e previsão.\n"
                f"3. Sugerir ajustes em TP/SL e leverage para robôs (ex.: robo do um porcento, Momentum Fast, Swing Alpha) com base em previsão e volatilidade.\n"
                f"4. Fornecer confiança (0-1) e motivo detalhado, destacando a importância da previsão de movimento.\n"
                f"Retorne JSON com: trend, signal, confidence, tp, sl, leverage, reason, robot_adjustments."
            )
            response = await self.call_grok_api(prompt, pair)
            if response:
                try:
                    insight = json.loads(response)
                    required_keys = ["trend", "signal", "confidence", "tp", "sl", "leverage", "reason", "robot_adjustments"]
                    if all(key in insight for key in required_keys):
                        out_path = os.path.join(self.data_dir, "grok_insights.csv")
                        pd.DataFrame({
                            "pair": [pair],
                            "timeframe": ["10m"],
                            "insights": [json.dumps(insight)],
                            "timestamp": [datetime.now().isoformat()]
                        }).to_csv(
                            out_path,
                            mode="a",
                            index=False,
                            header=not os.path.exists(out_path)
                        )
                        logger.info(f"Insight gerado para {pair}: {insight}")
                        self.last_check[pair] = datetime.now()
                        msg = (
                            f"\n[GROK - {pair}]\n"
                            f"Tendência: <b>{insight['trend'].capitalize()}</b>\n"
                            f"Sinal: <b>{insight['signal'].capitalize()}</b>\n"
                            f"Confiança: <b>{insight['confidence']:.2%}</b>\n"
                            f"Take-Profit: <b>{insight['tp']:.4f}</b>\n"
                            f"Stop-Loss: <b>{insight['sl']:.4f}</b>\n"
                            f"Leverage: <b>{insight['leverage']}x</b>\n"
                            f"Motivo: <pre>{insight['reason']}</pre>\n"
                            f"Ajustes por Robô: <pre>{json.dumps(insight['robot_adjustments'], indent=2, ensure_ascii=False)}</pre>\n"
                            f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
                        )
                        send_telegram_alert(msg)
                    else:
                        logger.error(f"Insight incompleto para {pair}: {insight}")
                except json.JSONDecodeError:
                    logger.error(f"Resposta inválida para {pair}: {response}")

    def calculate_rsi(self, prices, period=14):
        deltas = prices.diff()
        gains = deltas.where(deltas > 0, 0)
        losses = -deltas.where(deltas < 0, 0)
        avg_gain = gains.rolling(window=period, min_periods=1).mean()
        avg_loss = losses.rolling(window=period, min_periods=1).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs.replace([float('inf'), float('-inf')], float('nan')).fillna(0)))

    def calculate_ema(self, prices, period):
        return prices.ewm(span=period, adjust=False).mean()

    def calculate_sma(self, prices, period):
        return prices.rolling(window=period, min_periods=1).mean()

    def calculate_macd(self, prices, slow=26, fast=12, signal=9):
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        return macd, signal_line

    def calculate_adx(self, high, low, close, period=14):
        plus_dm = high.diff()
        minus_dm = -low.diff()
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        plus_di = 100 * (plus_dm.rolling(window=period, min_periods=1).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period, min_periods=1).mean() / atr)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float('nan')))
        adx = dx.rolling(window=period, min_periods=1).mean()
        return adx.fillna(0)

    async def run(self):
        schedule.every(10).minutes.do(lambda: asyncio.create_task(self.analyze_market()))
        logger.info("Iniciando verificações periódicas com Grok a cada 10 minutos...")
        while True:
            schedule.run_pending()
            await asyncio.sleep(60)

if __name__ == "__main__":
    checker = GrokPeriodicCheck(data_dir="data")
    asyncio.run(checker.run())