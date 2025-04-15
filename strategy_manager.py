import json
import os

STRATEGIES_FILE = "strategies.json"
ROBOT_STATUS_FILE = "robot_status.json"

def load_strategies():
    """
    Carrega as estratégias salvas do arquivo JSON, excluindo swing_trade_composite.
    Garante que cada estratégia tenha o campo 'name' preenchido corretamente.
    Returns:
        dict: Dicionário com as estratégias salvas.
    """
    if os.path.exists(STRATEGIES_FILE):
        with open(STRATEGIES_FILE, 'r') as f:
            strategies = json.load(f)
            # Remove swing_trade_composite, se existir
            strategies.pop("swing_trade_composite", None)
            # Garante que cada estratégia tenha o campo 'name' igual à chave
            for key in strategies:
                if isinstance(strategies[key], dict):
                    strategies[key]['name'] = key
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

def sync_strategies_and_status():
    """
    Sincroniza strategies.json e robot_status.json:
    - Adiciona ao status robôs presentes em strategies.json e ausentes em robot_status.json (como desativados)
    - Remove do status robôs que não existem mais em strategies.json
    - Salva o status atualizado se houver mudanças
    """
    strategies = load_strategies()
    status = load_robot_status()
    changed = False
    # Adicionar robôs ausentes
    for name in strategies.keys():
        if name not in status:
            status[name] = False
            changed = True
    # Remover robôs que não existem mais
    to_remove = [name for name in status.keys() if name not in strategies]
    for name in to_remove:
        del status[name]
        changed = True
    if changed:
        save_robot_status(status)
        print("[SYNC] robot_status.json sincronizado com strategies.json.")
    return status