import fcntl
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from config import Config

logger = logging.getLogger(__name__)

# Lock file sits alongside the data file to serialise concurrent access.
_LOCK_FILE = Config.DATA_FILE + '.lock'


@contextmanager
def _file_lock():
    """Acquire an exclusive lock for the duration of the context.

    Uses ``fcntl.flock`` on a dedicated lockfile so that concurrent
    read-modify-write cycles on the JSON data file are serialised.
    """
    os.makedirs(os.path.dirname(_LOCK_FILE), exist_ok=True)
    fd = open(_LOCK_FILE, 'w')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        logger.debug('Acquired file lock: %s', _LOCK_FILE)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        logger.debug('Released file lock: %s', _LOCK_FILE)
        fd.close()


def _load_raw() -> list:
    """Read the client list from disk (no locking — callers must lock)."""
    if not os.path.exists(Config.DATA_FILE):
        return []
    with open(Config.DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, ValueError):
            logger.warning('Failed to decode %s — returning empty list',
                           Config.DATA_FILE)
            return []


def _save_raw(clients: list):
    """Atomically write the client list to disk.

    Writes to a temporary file in the same directory and then renames it
    over the target.  This avoids leaving a half-written file if the
    process is interrupted.
    """
    data_dir = os.path.dirname(Config.DATA_FILE)
    os.makedirs(data_dir, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=data_dir, suffix='.tmp',
                                    prefix='.clients_')
    try:
        with os.fdopen(fd, 'w') as tmp_f:
            json.dump(clients, tmp_f, indent=2)
        os.replace(tmp_path, Config.DATA_FILE)
    except BaseException:
        # Clean up the temp file on any failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_clients() -> list:
    """Return all clients (read-only, no lock required)."""
    return _load_raw()


def get_client(client_id: str) -> dict:
    """Return a single client by id, or an empty dict if not found."""
    return next((c for c in _load_raw() if c['id'] == client_id), {})


def save_client(client: dict):
    """Insert or update a client record with exclusive file locking."""
    client_id = client['id']
    with _file_lock():
        clients = _load_raw()
        existing_idx = next(
            (i for i, c in enumerate(clients) if c['id'] == client_id), None
        )
        if existing_idx is not None:
            clients[existing_idx] = client
            logger.info('Updated client %s', client_id)
        else:
            clients.append(client)
            logger.info('Created client %s', client_id)
        _save_raw(clients)


def delete_client(client_id: str):
    """Remove a client record with exclusive file locking."""
    with _file_lock():
        clients = _load_raw()
        before = len(clients)
        clients = [c for c in clients if c['id'] != client_id]
        if len(clients) < before:
            logger.info('Deleted client %s', client_id)
        else:
            logger.warning('Attempted to delete non-existent client %s',
                           client_id)
        _save_raw(clients)
