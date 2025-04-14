# dashboard_components.py
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from dashboard_utils import load_data, load_robot_status, generate_orders, check_alerts
from strategy_manager import load_strategies
from utils import logger

def render_status_robots():
    try:
        st.header("Status dos Robôs")
        active_strategies = st.session_state.get('active_strategies', load_robot_status())
        df = load_data()
        
        # Log para depuração: verificar o estado inicial de df['timestamp']
        logger.info(f"Antes da conversão - Primeiros 5 timestamps: {df['timestamp'].head().tolist()}")
        logger.info(f"Tipos de dados antes da conversão: {df['timestamp'].dtype}")
        
        # Converter a coluna timestamp para datetime com formato específico
        try:
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
        except Exception as e:
            logger.error(f"Erro ao converter timestamps com formato específico: {e}")
            # Fallback: tentar conversão sem formato específico
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        
        # Log para depuração: verificar o estado após conversão
        logger.info(f"Após a conversão - Primeiros 5 timestamps: {df['timestamp'].head().tolist()}")
        logger.info(f"Tipos de dados após conversão: {df['timestamp'].dtype}")
        
        # Verificar se há valores NaT (não convertidos)
        if df['timestamp'].isna().any():
            logger.warning(f"Alguns timestamps não foram convertidos corretamente e são NaT: {df[df['timestamp'].isna()]['timestamp'].tolist()}")
        
        df_closed = df[df['estado'] == 'fechado']
        strategies = load_strategies()
        status_data = []

        for strategy_name in list(strategies.keys()) + ["swing_trade_composite"]:
            # Calcular tempo online
            if strategy_name not in st.session_state:
                st.session_state[strategy_name] = {'activation_time': None, 'last_activity': None}
            if active_strategies.get(strategy_name, strategy_name == "swing_trade_composite") and st.session_state[strategy_name]['activation_time'] is None:
                st.session_state[strategy_name]['activation_time'] = datetime.now()
            if not active_strategies.get(strategy_name, strategy_name == "swing_trade_composite"):
                st.session_state[strategy_name]['activation_time'] = None

            time_online = "Desativado"
            if active_strategies.get(strategy_name, strategy_name == "swing_trade_composite") and st.session_state[strategy_name]['activation_time']:
                time_diff = datetime.now() - st.session_state[strategy_name]['activation_time']
                hours, remainder = divmod(time_diff.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                time_online = f"{int(hours)}h {int(minutes)}m"

            # Calcular última atividade
            robot_orders = df[df['strategy_name'] == strategy_name]
            last_activity = "Nenhuma atividade"
            if not robot_orders.empty:
                last_order = robot_orders.sort_values('timestamp', ascending=False).iloc[0]
                # Log para depuração: verificar o tipo de last_order['timestamp']
                logger.debug(f"last_order['timestamp'] para {strategy_name}: {last_order['timestamp']} (tipo: {type(last_order['timestamp'])})")
                
                # Verificar se timestamp é um objeto datetime válido
                if pd.notna(last_order['timestamp']):
                    last_activity = last_order['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # Fallback: usar a string original ou indicar erro
                    last_activity = last_order['timestamp'] if isinstance(last_order['timestamp'], str) else "Timestamp inválido"
                    logger.warning(f"Timestamp inválido para {strategy_name}: {last_order['timestamp']}")
                st.session_state[strategy_name]['last_activity'] = last_activity

            # Calcular PNL total e taxa de vitória
            robot_closed = df_closed[df_closed['strategy_name'] == strategy_name]
            total_orders = len(robot_closed)
            wins = len(robot_closed[robot_closed['pnl_realizado'] >= 0])
            win_rate = (wins / total_orders * 100) if total_orders > 0 else 0
            total_pnl = robot_closed['pnl_realizado'].sum() if total_orders > 0 else 0

            # Determinar alerta visual
            alert = ""
            if total_pnl < -5:
                alert = "⚠️"
            elif total_pnl > 5:
                alert = "📈"

            status_data.append({
                "Robô": strategy_name,
                "Status": "Ativado" if active_strategies.get(strategy_name, strategy_name == "swing_trade_composite") else "Desativado",
                "Tempo Online": time_online,
                "Última Atividade": st.session_state[strategy_name]['last_activity'] or "Nenhuma atividade",
                "PNL Total": f"{total_pnl:.2f}% {alert}",
                "Taxa de Vitória": f"{win_rate:.2f}%"
            })

        # Exibir tabela com opção de ordenação
        status_df = pd.DataFrame(status_data)
        sort_by = st.selectbox("Ordenar por", ["Robô", "Tempo Online", "PNL Total", "Taxa de Vitória"], key="sort_robots")
        if sort_by == "Robô":
            status_df = status_df.sort_values("Robô")
        elif sort_by == "Tempo Online":
            status_df['Tempo Online Sort'] = status_df['Tempo Online'].apply(lambda x: sum(int(part) * (60 if 'h' in part else 1) for part in x.split() if part.isdigit()) if x != "Desativado" else -1)
            status_df = status_df.sort_values("Tempo Online Sort", ascending=False).drop("Tempo Online Sort", axis=1)
        elif sort_by == "PNL Total":
            status_df['PNL Sort'] = status_df['PNL Total'].str.extract(r'([-+]?\d*\.?\d+)%')[0].astype(float)
            status_df = status_df.sort_values("PNL Sort", ascending=False).drop("PNL Sort", axis=1)
        elif sort_by == "Taxa de Vitória":
            status_df['Win Rate Sort'] = status_df['Taxa de Vitória'].str.replace('%', '').astype(float)
            status_df = status_df.sort_values("Win Rate Sort", ascending=False).drop("Win Rate Sort", axis=1)

        st.markdown(status_df.to_html(index=False, classes="status-table"), unsafe_allow_html=True)

        # Gráfico de evolução do PNL por robô
        st.subheader("Evolução do PNL por Robô")
        if not df_closed.empty:
            chart_data = pd.DataFrame()
            for robot_name in status_df['Robô']:
                robot_df = df_closed[df_closed['strategy_name'] == robot_name].sort_values('timestamp')
                if not robot_df.empty:
                    robot_df['timestamp'] = pd.to_datetime(robot_df['timestamp'])
                    robot_df['Cumulative PNL'] = robot_df['pnl_realizado'].cumsum()
                    chart_data[robot_name] = robot_df.set_index('timestamp')['Cumulative PNL']
            if not chart_data.empty:
                st.line_chart(chart_data)
            else:
                st.info("Nenhuma ordem fechada para exibir o gráfico.")
        else:
            st.info("Nenhuma ordem fechada para exibir o gráfico.")

        # Gráfico de distribuição de ordens por resultado
        st.subheader("Distribuição de Ordens por Resultado")
        if not df_closed.empty:
            result_counts = df_closed.groupby(['strategy_name', 'resultado']).size().unstack(fill_value=0)
            if not result_counts.empty:
                fig = px.bar(
                    result_counts,
                    barmode='stack',
                    title="Distribuição de Ordens por Resultado",
                    labels={'value': 'Número de Ordens', 'strategy_name': 'Robô', 'resultado': 'Resultado'},
                    height=400
                )
                st.plotly_chart(fig)
            else:
                st.info("Nenhuma ordem fechada para exibir o gráfico.")
        else:
            st.info("Nenhuma ordem fechada para exibir o gráfico.")
    except Exception as e:
        logger.error(f"Erro ao renderizar Status dos Robôs: {e}")
        st.error(f"Erro ao renderizar Status dos Robôs: {e}")

# ... (outras funções do dashboard_components.py permanecem inalteradas)