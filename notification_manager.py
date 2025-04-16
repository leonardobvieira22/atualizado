import os
import json
import pandas as pd
from datetime import datetime, timedelta
import logging
import uuid
import requests

# Configuração do logger
logger = logging.getLogger("notification_manager")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Arquivo para armazenar notificações
NOTIFICATIONS_FILE = "system_notifications.json"

# Tipos de notificações
NOTIFICATION_TYPES = {
    "ERROR": {"icon": "🚨", "color": "#dc3545", "priority": 1},
    "WARNING": {"icon": "⚠️", "color": "#ffc107", "priority": 2},
    "INFO": {"icon": "ℹ️", "color": "#0dcaf0", "priority": 3},
    "SUCCESS": {"icon": "✅", "color": "#28a745", "priority": 4}
}

def init_notifications():
    """Inicializa o arquivo de notificações se não existir"""
    if not os.path.exists(NOTIFICATIONS_FILE):
        with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        logger.info(f"Arquivo de notificações '{NOTIFICATIONS_FILE}' criado.")

def load_notifications():
    """
    Carrega as notificações do arquivo
    """
    if os.path.exists(NOTIFICATIONS_FILE):
        try:
            with open(NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    # Arquivo vazio, sobrescrever com lista vazia
                    with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as fw:
                        json.dump([], fw)
                    logger.warning(f"Arquivo de notificações '{NOTIFICATIONS_FILE}' estava vazio e foi resetado.")
                    return []
                return json.loads(content)
        except json.JSONDecodeError:
            # Caso o arquivo esteja corrompido, criar novo
            with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as fw:
                json.dump([], fw)
            logger.error(f"Arquivo de notificações '{NOTIFICATIONS_FILE}' corrompido. Resetado para lista vazia.")
            return []
        except Exception as e:
            logger.error(f"Erro inesperado ao carregar notificações: {e}")
            return []
    return []

def save_notifications(notifications):
    """
    Salva as notificações no arquivo
    """
    with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(notifications, f, indent=4)

def add_notification(message, notification_type="INFO", source="Sistema", details=None, expiry_days=7):
    """
    Adiciona uma nova notificação ao sistema
    Args:
        message: Mensagem principal da notificação
        notification_type: Tipo de notificação (ERROR, WARNING, INFO, SUCCESS)
        source: Origem da notificação (ex: nome do robô, sistema, etc.)
        details: Detalhes adicionais (opcional)
        expiry_days: Dias até a notificação expirar automaticamente
    """
    try:
        init_notifications()
        notifications = load_notifications()
        
        # Verificar se já existe notificação similar nas últimas 24h
        now = datetime.now()
        recent_similar = [n for n in notifications 
                          if n["message"] == message 
                          and n["source"] == source 
                          and n["type"] == notification_type
                          and datetime.fromisoformat(n["timestamp"]) > now - timedelta(hours=24)]
        
        # Se já existe notificação similar recente, apenas atualize a contagem
        if recent_similar:
            recent_similar[0]["count"] += 1
            recent_similar[0]["timestamp"] = now.isoformat()
            recent_similar[0]["expiry"] = (now + timedelta(days=expiry_days)).isoformat()
            recent_similar[0]["read"] = False
            
            if details:
                if "details_history" not in recent_similar[0]:
                    recent_similar[0]["details_history"] = [recent_similar[0]["details"]]
                recent_similar[0]["details_history"].append(details)
                recent_similar[0]["details"] = details
        else:
            # Criar nova notificação
            new_notification = {
                "id": len(notifications) + 1,
                "timestamp": now.isoformat(),
                "expiry": (now + timedelta(days=expiry_days)).isoformat(),
                "type": notification_type,
                "source": source,
                "message": message,
                "details": details,
                "read": False,
                "count": 1
            }
            notifications.append(new_notification)
        
        # Remover notificações expiradas
        notifications = [n for n in notifications
                         if datetime.fromisoformat(n["expiry"]) > now]
        
        with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(notifications, f, indent=4)
            
        # Log adicional para debugging
        logger.info(f"Notificação [{notification_type}] adicionada: {message} (origem: {source})")
        
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar notificação: {e}")
        return False

def get_notifications(max_age_days=None, only_unread=False, source=None, type=None):
    """
    Recupera notificações com opções de filtragem
    """
    try:
        init_notifications()
        
        with open(NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
            notifications = json.load(f)
        
        # Aplicar filtros
        now = datetime.now()
        
        if max_age_days is not None:
            notifications = [n for n in notifications 
                             if datetime.fromisoformat(n["timestamp"]) > now - timedelta(days=max_age_days)]
        
        if only_unread:
            notifications = [n for n in notifications if not n.get("read", False)]
            
        if source:
            notifications = [n for n in notifications if n["source"] == source]
            
        if type:
            notifications = [n for n in notifications if n["type"] == type]
        
        # Ordenar por prioridade e depois por timestamp (mais recente primeiro)
        notifications.sort(key=lambda n: (
            NOTIFICATION_TYPES.get(n["type"], {"priority": 999})["priority"], 
            -datetime.fromisoformat(n["timestamp"]).timestamp()
        ))
        
        return notifications
    except Exception as e:
        logger.error(f"Erro ao recuperar notificações: {e}")
        return []

def mark_as_read(notification_id=None, all_notifications=False):
    """
    Marca notificações como lidas
    Args:
        notification_id: ID da notificação específica
        all_notifications: Se True, marca todas as notificações como lidas
    """
    try:
        init_notifications()
        
        with open(NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
            notifications = json.load(f)
        
        if all_notifications:
            for notification in notifications:
                notification["read"] = True
            logger.info("Todas as notificações marcadas como lidas.")
        elif notification_id is not None:
            for notification in notifications:
                if notification["id"] == notification_id:
                    notification["read"] = True
                    logger.info(f"Notificação {notification_id} marcada como lida.")
                    break
        
        with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(notifications, f, indent=4)
            
        return True
    except Exception as e:
        logger.error(f"Erro ao marcar notificação como lida: {e}")
        return False

def clear_all_notifications():
    """
    Limpa todas as notificações (útil para reset completo)
    """
    try:
        with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        logger.info("Todas as notificações foram removidas.")
        return True
    except Exception as e:
        logger.error(f"Erro ao limpar notificações: {e}")
        return False

def log_inconsistency(strategy_name, issue_type, details=None):
    """
    Registra uma inconsistência específica de estratégia
    Args:
        strategy_name: Nome da estratégia
        issue_type: Tipo de problema (active_no_orders, inactive_has_orders)
        details: Detalhes adicionais
    """
    issue_messages = {
        "active_no_orders": f"Robô '{strategy_name}' está ativo, mas não possui ordens abertas.",
        "inactive_has_orders": f"Robô '{strategy_name}' está inativo, mas possui ordens abertas.",
        "unlisted_strategy": f"Robô '{strategy_name}' não está listado no status dos robôs."
    }
    
    message = issue_messages.get(issue_type, f"Inconsistência detectada: {issue_type}")
    
    add_notification(
        message=message,
        notification_type="WARNING",
        source=f"Validação: {strategy_name}",
        details=details
    )

def check_system_health(df, robot_status, indicadores_compostos):
    """
    Verifica a saúde do sistema e registra problemas encontrados
    Args:
        df: DataFrame com ordens
        robot_status: Status dos robôs
        indicadores_compostos: Lista de nomes de indicadores compostos 
    Returns:
        int: Número de inconsistências encontradas
    """
    inconsistency_count = 0
    
    # Verificar inconsistências no status dos robôs
    for strategy_name, is_active in robot_status.items():
        # Pular verificação para conjuntos de indicadores
        if strategy_name.lower() in [ind.lower() for ind in indicadores_compostos]:
            continue
            
        active_orders = df[(df['strategy_name'] == strategy_name) & (df['estado'] == 'aberto')]
        if is_active and active_orders.empty:
            log_inconsistency(strategy_name, "active_no_orders")
            inconsistency_count += 1
        elif not is_active and not active_orders.empty:
            log_inconsistency(strategy_name, "inactive_has_orders", 
                              f"Ordens abertas: {len(active_orders)}")
            inconsistency_count += 1

    # Verificar estratégias não listadas no status
    all_strategies = set(robot_status.keys())
    active_strategies_in_data = set(df['strategy_name'].unique())
    unlisted_strategies = active_strategies_in_data - all_strategies

    for strategy_name in unlisted_strategies:
        # Não reportar indicadores compostos
        if strategy_name.lower() in [ind.lower() for ind in indicadores_compostos]:
            continue
            
        log_inconsistency(strategy_name, "unlisted_strategy")
        inconsistency_count += 1
        
    # Verificar arquivos de dados
    if len(df) == 0:
        add_notification(
            message="O arquivo de sinais está vazio. Pode ser necessário verificar a geração de sinais.",
            notification_type="WARNING",
            source="Validação: Sistema"
        )
        inconsistency_count += 1
    
    return inconsistency_count

def get_recent_notifications(limit=10, include_read=False):
    """
    Obtém as notificações mais recentes
    
    Args:
        limit (int, optional): Número máximo de notificações para retornar
        include_read (bool, optional): Incluir notificações já lidas
    
    Returns:
        list: Lista de notificações
    """
    notifications = load_notifications()
    
    if not include_read:
        notifications = [n for n in notifications if not n.get('is_read', False)]
    
    # Ordenar por timestamp (mais recentes primeiro)
    notifications.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return notifications[:limit]

def mark_notification_as_read(notification_id):
    """
    Marca uma notificação como lida
    
    Args:
        notification_id (str): ID da notificação
    
    Returns:
        bool: True se a notificação foi encontrada e marcada, False caso contrário
    """
    notifications = load_notifications()
    
    for notification in notifications:
        if notification['id'] == notification_id:
            notification['is_read'] = True
            save_notifications(notifications)
            return True
    
    return False

def mark_all_as_read():
    """
    Marca todas as notificações como lidas
    """
    notifications = load_notifications()
    
    if not notifications:
        return False
    
    for notification in notifications:
        notification['is_read'] = True
    
    save_notifications(notifications)
    return True

def get_unread_count():
    """
    Obtém o número de notificações não lidas
    
    Returns:
        int: Número de notificações não lidas
    """
    notifications = load_notifications()
    return len([n for n in notifications if not n.get('is_read', False)])

def cleanup_old_notifications(max_age_days=30):
    """
    Remove notificações antigas do sistema
    
    Args:
        max_age_days (int): Idade máxima em dias das notificações a manter
    
    Returns:
        int: Número de notificações removidas
    """
    notifications = load_notifications()
    
    if not notifications:
        return 0
    
    now = datetime.now()
    cutoff_date = now - timedelta(days=max_age_days)
    
    old_notifications = []
    new_notifications = []
    
    for notification in notifications:
        try:
            notification_date = datetime.fromisoformat(notification['timestamp'])
            if notification_date < cutoff_date:
                old_notifications.append(notification)
            else:
                new_notifications.append(notification)
        except (ValueError, KeyError):
            # Se não for possível analisar a data, manter a notificação
            new_notifications.append(notification)
    
    if old_notifications:
        save_notifications(new_notifications)
        
    return len(old_notifications)

def send_telegram_alert(message: str):
    """
    Envia alerta para o Telegram usando o token e chat_id definidos no código.
    """
    chat_id = "6097421181"
    telegram_api_url = "https://api.telegram.org/bot8091827388:AAGUkSq6rxchs0OitnLQWzEjrer7AWWSgmY/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(telegram_api_url, data=payload, timeout=5)
        if resp.status_code == 200:
            logger.info(f"Alerta enviado ao Telegram: {message}")
            return True
        else:
            logger.error(f"Falha ao enviar alerta Telegram: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Erro ao enviar alerta Telegram: {e}")
        return False