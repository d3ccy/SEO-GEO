"""
Client data access layer.

Replaces the legacy clients.json flat-file store with SQLAlchemy-backed
persistence.  The public interface (load_clients, get_client, save_client,
delete_client) is identical to the old file-based version so that no route
code needs to change.
"""
import logging
import uuid
from datetime import datetime, timezone

from extensions import db
from models import Client

logger = logging.getLogger(__name__)


def load_clients() -> list:
    """Return all clients as a list of dicts, ordered by creation date."""
    return [c.to_dict() for c in Client.query.order_by(Client.created.asc()).all()]


def get_client(client_id: str) -> dict:
    """Return a single client as a dict, or an empty dict if not found."""
    c = db.session.get(Client, client_id)
    return c.to_dict() if c else {}


def save_client(client: dict) -> None:
    """Insert or update a client record.

    ``client`` must be a dict with at least 'id' and 'name' keys.
    """
    client_id = client.get('id') or uuid.uuid4().hex
    existing = db.session.get(Client, client_id)

    if existing:
        existing.name = client.get('name', existing.name)
        existing.domain = client.get('domain', existing.domain) or ''
        existing.project_name = client.get('project_name', existing.project_name) or ''
        existing.cms = client.get('cms', existing.cms) or ''
        existing.location_code = int(client.get('location_code', existing.location_code) or 2826)
        existing.notes = client.get('notes', existing.notes) or ''
        logger.info('Updated client %s', client_id)
    else:
        # Parse 'created' if provided as an ISO string, otherwise use now
        created_raw = client.get('created')
        if isinstance(created_raw, str):
            try:
                created_dt = datetime.fromisoformat(created_raw)
            except ValueError:
                created_dt = datetime.now(timezone.utc)
        elif isinstance(created_raw, datetime):
            created_dt = created_raw
        else:
            created_dt = datetime.now(timezone.utc)

        new_client = Client(
            id=client_id,
            name=client.get('name', ''),
            domain=client.get('domain', '') or '',
            project_name=client.get('project_name', '') or '',
            cms=client.get('cms', '') or '',
            location_code=int(client.get('location_code', 2826) or 2826),
            notes=client.get('notes', '') or '',
            created=created_dt,
        )
        db.session.add(new_client)
        logger.info('Created client %s', client_id)

    db.session.commit()


def delete_client(client_id: str) -> None:
    """Remove a client record. No-op if the client does not exist."""
    c = db.session.get(Client, client_id)
    if c:
        db.session.delete(c)
        db.session.commit()
        logger.info('Deleted client %s', client_id)
    else:
        logger.warning('Attempted to delete non-existent client %s', client_id)
