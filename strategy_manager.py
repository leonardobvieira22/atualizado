import json
import os

STRATEGIES_FILE = "strategies.json"
ROBOT_STATUS_FILE = "robot_status.json"

def load_strategies():
    """
    Carrega as estratégias salvas do arquivo JSON, excluindo swing_trade_composite.
    Returns:
        dict: Dicionário com as estratégias salvas.
    """
    if os.path.exists(STRATEGIES_FILE):
        with open(STRATEGIES_FILE, 'r') as f:
            strategies = json.load(f)
            # Remove swing_trade_composite, se existir
            strategies.pop("swing_trade_composite", None)
            return strategies
    return {}

def save_strategies(strategies):
    """
    Salva as estratégias no arquivo JSON, excluindo swing_trade_composite.
    Args:
        strategies (dict): Dicionário com as estratégias a serem salvas.
    """
    # Cria uma cópia do dicionário e remove swing_trade_composite
    strategies_to_save = strategies.copy()
    strategies_to_save.pop("swing_trade_composite", None)
    with open(STRATEGIES_FILE, 'w') as f:
        json.dump(strategies_to_save, f, indent=4)

def load_robot_status():
    """
    Carrega o status dos robôs (ativo/desativado) do arquivo JSON.
    Returns:
        dict: Dicionário com o status dos robôs.
    """
    if os.path.exists(ROBOT_STATUS_FILE):
        with open(ROBOT_STATUS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_robot_status(status):
    """
    Salva o status dos robôs no arquivo JSON.
    Args:
        status (dict): Dicionário com o status dos robôs.
    """
    with open(ROBOT_STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=4)