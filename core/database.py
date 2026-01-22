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

async def create_engine_with_fallback():
    """Try to connect with DATABASE_URL, fallback to DATABASE_PUBLIC_URL if needed."""
    
    # helper to fix protocol for asyncpg
    def fix_url(url):
        if not url: return None
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # 1. Try Primary URL (Internal)
    primary_url = fix_url(os.getenv("DATABASE_URL"))
    
    # 2. Prepare Fallback (Public)
    fallback_url = fix_url(os.getenv("DATABASE_PUBLIC_URL"))
    
    if not primary_url:
        print("❌ CRITICAL: DATABASE_URL is NOT SET.")
        if fallback_url:
            print("⚠️ Using DATABASE_PUBLIC_URL as primary.")
            primary_url = fallback_url
        else:
            print("⚠️ Using default localhost URL. This will fail on production.")
            primary_url = "postgresql+asyncpg://user:pass@localhost/dbname"

    # Function to test connection
    async def try_connect(url, name):
        try:
            # Log the host we are trying to connect to (masking credentials)
            safe_host = url.split("@")[-1] if "@" in url else "unknown"
            print(f"🔌 [{name}] Attempting to connect to: {safe_host}")
            
            test_engine = create_async_engine(url, echo=False, pool_pre_ping=True)
            async with test_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            print(f"✅ [{name}] Connection SUCCESS!")
            return test_engine
        except Exception as e:
            print(f"❌ [{name}] Connection FAILED: {e}")
            return None

    # Attempt 1: Primary
    engine = await try_connect(primary_url, "PRIMARY")
    
    # Attempt 2: Fallback (if primary failed and we have a fallback)
    if not engine and fallback_url and primary_url != fallback_url:
        print("⚠️ Primary connection failed. Switching to FALLBACK (Public URL)...")
        engine = await try_connect(fallback_url, "FALLBACK")
        
    if not engine:
        print("🔥 ALL CONNECTION ATTEMPTS FAILED. App will likely crash.")
        # Return a broken engine anyway so we don't crash at module level, 
        # but usage will crash
        return create_async_engine(primary_url or "", echo=False)
        
    return engine

# Create Async Engine (Global)
# We need to run this synchronously at module level, but we can't await here.
# So we use a lazy loader or just standard creation for now, but we'll adding the smart logic to the init_db check.

# SIMPLIFIED ROBUST VERSION for module level:
# We just use the string processing here to be safe
_raw_url = os.getenv("DATABASE_URL")
if _raw_url and _raw_url.startswith("postgres://"):
    DATABASE_URL = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url and _raw_url.startswith("postgresql://"):
    DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_url or "postgresql+asyncpg://user:pass@localhost/dbname"

# Fallback check immediately if internal is likely to fail? 
# No, let's just create the engine. The 'lifespan' startup event will handle the actual check.
engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)

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
    """Initialize database tables."""
    global engine
    
    # Helper to check connection
    async def check_conn(eng):
        try:
            async with eng.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            print(f"❌ Connection check failed: {e}")
            return False

    print("🔄 Checking database connection...")
    
    # 1. Try existing engine
    if await check_conn(engine):
        print("✅ Primary Database Connection Successful!")
    else:
        # 2. Try Fallback URL
        fallback_raw = os.getenv("DATABASE_PUBLIC_URL")
        if fallback_raw:
            print("⚠️ Primary failed. Attempting Fallback to DATABASE_PUBLIC_URL...")
            
            # Fix URL
            if fallback_raw.startswith("postgres://"):
                fb_url = fallback_raw.replace("postgres://", "postgresql+asyncpg://", 1)
            elif fallback_raw.startswith("postgresql://"):
                fb_url = fallback_raw.replace("postgresql://", "postgresql+asyncpg://", 1)
            else:
                fb_url = fallback_raw
                
            try:
                # Create temporary engine to test
                fb_engine = create_async_engine(fb_url, echo=False, pool_pre_ping=True)
                if await check_conn(fb_engine):
                    print("✅ Fallback Connection Successful! Switching engine.")
                    # Dispose old engine
                    await engine.dispose()
                    # Switch global engine
                    engine = fb_engine
                    # Re-bind sessionmaker
                    global async_session_maker
                    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
                else:
                    print("❌ Fallback also failed.")
            except Exception as e:
                print(f"❌ Error creating fallback engine: {e}")
        else:
            print("❌ No DATABASE_PUBLIC_URL provided for fallback.")

    # Proceed with initialization (will raise if still broken)
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # WARNING: DELETES DATA
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ Tables initialized")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for generic DB access."""
    async with async_session_maker() as session:
        yield session
