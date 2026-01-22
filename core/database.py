"""
database.py - PostgreSQL Connection Layer
"""

import os
from typing import AsyncGenerator
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, Boolean, Text, BigInteger
from dotenv import load_dotenv

load_dotenv()

# Get DB URL from env (Railway provides DATABASE_URL)
raw_url = os.getenv("DATABASE_URL")

if not raw_url:
    print("❌ CRITICAL: DATABASE_URL environment variable is NOT SET.")
    print("⚠️ Using default localhost URL (this will fail on Railway unless you have a local DB).")
    raw_url = "postgresql+asyncpg://user:pass@localhost/dbname"
else:
    print("✅ Found DATABASE_URL environment variable.")

# Ensure async driver
if raw_url.startswith("postgres://"):
    DATABASE_URL = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif raw_url.startswith("postgresql://"):
    DATABASE_URL = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = raw_url

try:
    # Log the host we are trying to connect to (masking credentials)
    safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "unknown"
    print(f"🔌 Attempting to connect to database host: {safe_url}")
except Exception:
    pass

# Create Async Engine
try:
    engine = create_async_engine(
        DATABASE_URL, 
        echo=False,
        pool_pre_ping=True,  # Check connection health
        pool_recycle=3600,
    )
except Exception as e:
    print(f"❌ Failed to create database engine: {e}")
    raise

# Session Factory
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


# Base Model
class Base(DeclarativeBase):
    pass


# =============================================================================
# MODELS
# =============================================================================

class ClientModel(Base):
    __tablename__ = "clients"
    
    client_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[str] = mapped_column(String)
    api_key_hash: Mapped[str] = mapped_column(String, index=True)
    webhook_secret: Mapped[str] = mapped_column(String)
    database_type: Mapped[str] = mapped_column(String)
    connection_string_encrypted: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    plan: Mapped[str] = mapped_column(String, default="per-fix")
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now().isoformat())
    last_activity: Mapped[str | None] = mapped_column(String, nullable=True)
    total_fixes: Mapped[int] = mapped_column(Integer, default=0)
    total_billed: Mapped[float] = mapped_column(Float, default=0.0)


class BillingModel(Base):
    __tablename__ = "billing_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String, index=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    company_name: Mapped[str] = mapped_column(String)
    fix_id: Mapped[str] = mapped_column(String)
    fix_type: Mapped[str] = mapped_column(String)
    error_summary: Mapped[str] = mapped_column(Text)
    amount_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String)
    execution_time_ms: Mapped[float] = mapped_column(Float)
    rows_affected: Mapped[int] = mapped_column(Integer)


class LeadModel(Base):
    __tablename__ = "leads"
    
    lead_id: Mapped[str] = mapped_column(String, primary_key=True)
    platform: Mapped[str] = mapped_column(String)
    username: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    post_content: Mapped[str] = mapped_column(Text)
    post_url: Mapped[str] = mapped_column(String)
    keywords_matched: Mapped[str] = mapped_column(Text)  # JSON string
    status: Mapped[str] = mapped_column(String, index=True)
    first_contact_date: Mapped[str | None] = mapped_column(String, nullable=True)
    last_contact_date: Mapped[str | None] = mapped_column(String, nullable=True)
    follow_up_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String)


# =============================================================================
# DEPENDENCIES
# =============================================================================

async def init_db():
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for generic DB access."""
    async with async_session_maker() as session:
        yield session
