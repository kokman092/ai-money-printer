"""
scout.py - Client Verification & Discovery (PostgreSQL Version)
Checks if incoming requests are from paid clients
"""

import os
import secrets
import hashlib
import asyncio
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# Import our new DB layer
from core.database import async_session_maker, ClientModel, init_db


@dataclass
class Client:
    """Represents a registered client."""
    client_id: str
    company_name: str
    api_key_hash: str
    webhook_secret: str
    database_type: str
    connection_string_encrypted: str
    is_active: bool
    created_at: str
    last_activity: Optional[str] = None
    total_fixes: int = 0
    total_billed: float = 0.0
    plan: str = "per-fix"


class ClientVault:
    """
    Secure storage for client credentials and verification.
    Uses PostgreSQL for persistence.
    """
    
    def __init__(self):
        # Initialize DB tables on startup (non-blocking)
        # In production, use migrations (Alembic)
        pass
    
    async def _ensure_db_ready(self):
        """Ensure tables exist (lazy init)."""
        # This is a bit hacky for creating tables on the fly
        # Ideally correct this in main.py startup event
        await init_db()
    
    def _hash_api_key(self, api_key: str) -> str:
        """Create a secure hash of an API key."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    async def register_client(
        self,
        company_name: str,
        database_type: str,
        connection_string: str,
        plan: str = "per-fix"
    ) -> tuple[str, str]:
        """
        Register a new client and generate their credentials.
        """
        await self._ensure_db_ready()
        
        # Generate credentials
        client_id = f"client_{secrets.token_hex(8)}"
        api_key = f"amp_{secrets.token_urlsafe(32)}"
        webhook_secret = secrets.token_urlsafe(16)
        
        # Encrypt connection string
        encryption_key = os.getenv("ENCRYPTION_KEY", "default_key_change_me!")
        encrypted_conn = self._simple_encrypt(connection_string, encryption_key)
        
        new_client = ClientModel(
            client_id=client_id,
            company_name=company_name,
            api_key_hash=self._hash_api_key(api_key),
            webhook_secret=webhook_secret,
            database_type=database_type,
            connection_string_encrypted=encrypted_conn,
            is_active=True,
            plan=plan,
            created_at=datetime.now().isoformat()
        )
        
        async with async_session_maker() as session:
            session.add(new_client)
            await session.commit()
            
        return client_id, api_key
    
    def verify_client(self, api_key: str) -> Optional[Client]:
        """
        Verify an API key and return the client if valid.
        NOTE: This method is synchronous in the interface, but we need to run async DB calls.
        We'll use a helper to run the async verify.
        """
        # This wrapper allows calling async code from sync context if needed,
        # but optimally we should update main.py to await this.
        # For now, let's assume the caller can await if we change the signature.
        # But to avoid breaking main.py immediately, we'll try to run it.
        # UPDATE: We should update main.py to async.
        # But wait - main.py endpoints ARE async. We can change this to async!
        raise NotImplementedError("Use verify_client_async instead")

    async def verify_client_async(self, api_key: str) -> Optional[Client]:
        """Async version of client verification."""
        hashed_key = self._hash_api_key(api_key)
        
        async with async_session_maker() as session:
            stmt = select(ClientModel).where(ClientModel.api_key_hash == hashed_key)
            result = await session.execute(stmt)
            client_model = result.scalar_one_or_none()
            
            if not client_model or not client_model.is_active:
                return None
            
            # Update activity
            client_model.last_activity = datetime.now().isoformat()
            await session.commit()
            
            return self._model_to_dataclass(client_model)
    
    async def update_client_stats(self, client_id: str, amount_billed: float):
        """Update client statistics."""
        async with async_session_maker() as session:
            stmt = select(ClientModel).where(ClientModel.client_id == client_id)
            result = await session.execute(stmt)
            client = result.scalar_one_or_none()
            
            if client:
                client.total_fixes += 1
                client.total_billed += amount_billed
                client.last_activity = datetime.now().isoformat()
                await session.commit()

    async def list_active_clients_async(self) -> List[Client]:
        """List all active clients."""
        async with async_session_maker() as session:
            stmt = select(ClientModel).where(ClientModel.is_active == True)
            result = await session.execute(stmt)
            clients = result.scalars().all()
            return [self._model_to_dataclass(c) for c in clients]
            
    async def get_decrypted_connection(self, client: Client) -> str:
        """Decrypt connection string."""
        encryption_key = os.getenv("ENCRYPTION_KEY", "default_key_change_me!")
        return self._simple_decrypt(client.connection_string_encrypted, encryption_key)
        
    def _model_to_dataclass(self, model: ClientModel) -> Client:
        """Convert DB model to dataclass."""
        return Client(
            client_id=model.client_id,
            company_name=model.company_name,
            api_key_hash=model.api_key_hash,
            webhook_secret=model.webhook_secret,
            database_type=model.database_type,
            connection_string_encrypted=model.connection_string_encrypted,
            is_active=model.is_active,
            created_at=model.created_at,
            last_activity=model.last_activity,
            total_fixes=model.total_fixes,
            total_billed=model.total_billed,
            plan=model.plan
        )
    
    @staticmethod
    def _simple_encrypt(data: str, key: str) -> str:
        """Simple XOR encryption."""
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
