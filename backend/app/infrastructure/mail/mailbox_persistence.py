# File: backend/app/infrastructure/mail/mailbox_persistence.py
import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional
from app.domain.value_objects.mailbox_verification import MailboxMapping

logger = logging.getLogger(__name__)


class MailboxPersistence:
    """Safely stores serialized MSAL token cache and connection mapping on local disk."""

    def __init__(self, filepath: str):
        self.filepath = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.isfile(self.filepath):
            return {}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                data = json.loads(content)
                if isinstance(data, dict) and "connections" in data:
                    return data["connections"]
                return data if isinstance(data, dict) else {}
        except Exception as error:
            logger.warning("Failed to read mailbox cache file %s: %s", self.filepath, error)
            return {}

    def _write_all(self, connections: Dict[str, Dict[str, Any]]) -> None:
        payload = {"version": 1, "updated_at": time.time(), "connections": connections}
        dir_name = os.path.dirname(self.filepath)
        os.makedirs(dir_name, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="mailbox_cache_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.filepath)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    def save_connection(
        self, connection_id: str, account_id: str, primary_email: str,
        account: dict, serialized_cache: str, mapping: Optional[MailboxMapping] = None,
        revision: int = 0,
    ) -> None:
        connections = self.load_all()
        mapping_dict = None
        if mapping is not None:
            mapping_dict = {
                "meta_email": mapping.meta_email,
                "primary_email": mapping.primary_email,
                "confirmed_aliases": list(mapping.confirmed_aliases),
                "folders": list(mapping.folders),
                "template_version": mapping.template_version,
            }
        connections[connection_id] = {
            "connection_id": connection_id,
            "account_id": account_id,
            "primary_email": primary_email,
            "account": account,
            "token_cache": serialized_cache,
            "mapping": mapping_dict,
            "revision": revision,
            "saved_at": time.time(),
        }
        self._write_all(connections)

    def update_cache(self, connection_id: str, serialized_cache: str) -> None:
        connections = self.load_all()
        if connection_id in connections:
            connections[connection_id]["token_cache"] = serialized_cache
            connections[connection_id]["saved_at"] = time.time()
            self._write_all(connections)

    def update_mapping(self, connection_id: str, mapping: MailboxMapping, revision: int = 1) -> None:
        connections = self.load_all()
        if connection_id in connections:
            connections[connection_id]["mapping"] = {
                "meta_email": mapping.meta_email,
                "primary_email": mapping.primary_email,
                "confirmed_aliases": list(mapping.confirmed_aliases),
                "folders": list(mapping.folders),
                "template_version": mapping.template_version,
            }
            connections[connection_id]["revision"] = revision
            connections[connection_id]["saved_at"] = time.time()
            self._write_all(connections)

    def remove_connection(self, connection_id: str) -> None:
        connections = self.load_all()
        if connection_id in connections:
            connections.pop(connection_id, None)
            self._write_all(connections)
