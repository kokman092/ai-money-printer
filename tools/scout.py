"""
scout.py - Client Verification & Discovery
Checks if incoming requests are from paid clients
"""

import os
import json
import hashlib
import secrets
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Client:
    """Represents a registered client."""
    client_id: str
    company_name: str
    api_key_hash: str
    webhook_secret: str
    database_type: str  # "sqlite", "postgres", "mysql"
    connection_string_encrypted: str
    is_active: bool
    created_at: str
    last_activity: Optional[str] = None
    total_fixes: int = 0
    total_billed: float = 0.0
    plan: str = "per-fix"  # "per-fix", "monthly", "enterprise"


class ClientVault:
    """
    Secure storage for client credentials and verification.
    """
    
    def __init__(self, vault_path: str = None):
        if vault_path is None:
            vault_path = Path(__file__).parent.parent / "data" / "client_vault.json"
        self.vault_path = Path(vault_path)
        self._ensure_vault_exists()
    
    def _ensure_vault_exists(self):
        """Create vault file if it doesn't exist."""
        if not self.vault_path.exists():
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_vault({"clients": {}, "api_keys": {}})
    
    def _load_vault(self) -> dict:
        """Load the vault from disk."""
        with open(self.vault_path, "r") as f:
            return json.load(f)
    
    def _save_vault(self, data: dict):
        """Save the vault to disk."""
        with open(self.vault_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _hash_api_key(self, api_key: str) -> str:
        """Create a secure hash of an API key."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def register_client(
        self,
        company_name: str,
        database_type: str,
        connection_string: str,
        plan: str = "per-fix"
    ) -> tuple[str, str]:
        """
        Register a new client and generate their credentials.
        
        Returns:
            (client_id, api_key) - API key is only shown once!
        """
        vault = self._load_vault()
        
        # Generate unique identifiers
        client_id = f"client_{secrets.token_hex(8)}"
        api_key = f"amp_{secrets.token_urlsafe(32)}"
        webhook_secret = secrets.token_urlsafe(16)
        
        # Encrypt connection string (simple XOR for demo, use proper encryption in production)
        encryption_key = os.getenv("ENCRYPTION_KEY", "default_key_change_me!")
        encrypted_conn = self._simple_encrypt(connection_string, encryption_key)
        
        client = Client(
            client_id=client_id,
            company_name=company_name,
            api_key_hash=self._hash_api_key(api_key),
            webhook_secret=webhook_secret,
            database_type=database_type,
            connection_string_encrypted=encrypted_conn,
            is_active=True,
            created_at=datetime.now().isoformat(),
            plan=plan
        )
        
        vault["clients"][client_id] = asdict(client)
        vault["api_keys"][self._hash_api_key(api_key)] = client_id
        
        self._save_vault(vault)
        
        return client_id, api_key
    
    def verify_client(self, api_key: str) -> Optional[Client]:
        """
        Verify an API key and return the client if valid.
        
        Returns:
            Client object if valid, None if invalid
        """
        vault = self._load_vault()
        api_key_hash = self._hash_api_key(api_key)
        
        client_id = vault["api_keys"].get(api_key_hash)
        if not client_id:
            return None
        
        client_data = vault["clients"].get(client_id)
        if not client_data:
            return None
        
        if not client_data.get("is_active", False):
            return None
        
        # Update last activity
        client_data["last_activity"] = datetime.now().isoformat()
        self._save_vault(vault)
        
        return Client(**client_data)
    
    def is_paid_client(self, api_key: str) -> bool:
        """Quick check if this is a valid, paid client."""
        client = self.verify_client(api_key)
        return client is not None and client.is_active
    
    def get_client_by_id(self, client_id: str) -> Optional[Client]:
        """Get a client by their ID."""
        vault = self._load_vault()
        client_data = vault["clients"].get(client_id)
        if client_data:
            return Client(**client_data)
        return None
    
    def update_client_stats(self, client_id: str, amount_billed: float):
        """Update client statistics after a successful fix."""
        vault = self._load_vault()
        
        if client_id in vault["clients"]:
            vault["clients"][client_id]["total_fixes"] += 1
            vault["clients"][client_id]["total_billed"] += amount_billed
            vault["clients"][client_id]["last_activity"] = datetime.now().isoformat()
            self._save_vault(vault)
    
    def deactivate_client(self, client_id: str) -> bool:
        """Deactivate a client (e.g., for non-payment)."""
        vault = self._load_vault()
        
        if client_id in vault["clients"]:
            vault["clients"][client_id]["is_active"] = False
            self._save_vault(vault)
            return True
        return False
    
    def list_active_clients(self) -> list[Client]:
        """List all active clients."""
        vault = self._load_vault()
        return [
            Client(**data) 
            for data in vault["clients"].values() 
            if data.get("is_active", False)
        ]
    
    def get_decrypted_connection(self, client: Client) -> str:
        """Decrypt and return the client's database connection string."""
        encryption_key = os.getenv("ENCRYPTION_KEY", "default_key_change_me!")
        return self._simple_decrypt(client.connection_string_encrypted, encryption_key)
    
    @staticmethod
    def _simple_encrypt(data: str, key: str) -> str:
        """Simple XOR encryption (use proper encryption in production!)."""
        import base64
        key_bytes = key.encode() * (len(data) // len(key) + 1)
        encrypted = bytes([a ^ b for a, b in zip(data.encode(), key_bytes[:len(data)])])
        return base64.b64encode(encrypted).decode()
    
    @staticmethod
    def _simple_decrypt(data: str, key: str) -> str:
        """Simple XOR decryption."""
        import base64
        encrypted = base64.b64decode(data.encode())
        key_bytes = key.encode() * (len(encrypted) // len(key) + 1)
        decrypted = bytes([a ^ b for a, b in zip(encrypted, key_bytes[:len(encrypted)])])
        return decrypted.decode()


# Singleton instance
_vault_instance: Optional[ClientVault] = None


def get_vault() -> ClientVault:
    """Get or create the singleton vault instance."""
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = ClientVault()
    return _vault_instance
