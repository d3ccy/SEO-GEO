import json
import os
from config import Config


def _load_raw() -> list:
    if not os.path.exists(Config.DATA_FILE):
        return []
    with open(Config.DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return []


def _save_raw(clients: list):
    os.makedirs(os.path.dirname(Config.DATA_FILE), exist_ok=True)
    with open(Config.DATA_FILE, 'w') as f:
        json.dump(clients, f, indent=2)


def load_clients() -> list:
    return _load_raw()


def get_client(client_id: str) -> dict:
    return next((c for c in _load_raw() if c['id'] == client_id), {})


def save_client(client: dict):
    clients = _load_raw()
    existing_idx = next((i for i, c in enumerate(clients) if c['id'] == client['id']), None)
    if existing_idx is not None:
        clients[existing_idx] = client
    else:
        clients.append(client)
    _save_raw(clients)


def delete_client(client_id: str):
    clients = [c for c in _load_raw() if c['id'] != client_id]
    _save_raw(clients)
