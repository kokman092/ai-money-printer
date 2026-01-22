"""
billing.py - Outcome Tracker & Billing (PostgreSQL Version)
Turns successful fixes into cash - only runs after safety.py green light
"""

import os
import httpx
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# Import DB layer
from core.database import async_session_maker, BillingModel


@dataclass
class BillingRecord:
    """A record of a billable fix."""
    timestamp: str
    client_id: str
    company_name: str
    fix_id: str
    fix_type: str
    error_summary: str
    amount_usd: float
    status: str
    execution_time_ms: float
    rows_affected: int


class BillingSystem:
    """
    The outcome tracker that:
    1. Logs every successful fix
    2. Sends Telegram notifications
    3. Tracks earnings
    """
    
    def __init__(self):
        self.fix_price = float(os.getenv("FIX_PRICE_USD", "5.00"))
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    async def log_success(
        self,
        client_id: str,
        company_name: str,
        fix_id: str,
        fix_type: str,
        error_summary: str,
        execution_time_ms: float,
        rows_affected: int,
        custom_amount: Optional[float] = None
    ) -> BillingRecord:
        """Log a successful fix and trigger billing."""
        amount = custom_amount if custom_amount is not None else self.fix_price
        
        timestamp = datetime.now().isoformat()
        
        # Create DB record
        record = BillingModel(
            timestamp=timestamp,
            client_id=client_id,
            company_name=company_name,
            fix_id=fix_id,
            fix_type=fix_type,
            error_summary=error_summary[:1000],  # Postgres TEXT can hold more
            amount_usd=amount,
            status="completed",
            execution_time_ms=execution_time_ms,
            rows_affected=rows_affected
        )
        
        async with async_session_maker() as session:
            session.add(record)
            await session.commit()
            
        # Create dataclass for return
        billing_record = BillingRecord(
            timestamp=timestamp,
            client_id=client_id,
            company_name=company_name,
            fix_id=fix_id,
            fix_type=fix_type,
            error_summary=error_summary,
            amount_usd=amount,
            status="completed",
            execution_time_ms=execution_time_ms,
            rows_affected=rows_affected
        )
        
        # Send Telegram notification
        await self._send_telegram_notification(billing_record)
        
        return billing_record

    async def get_min_payment_amount(self, currency_from: str = "usd", currency_to: str = "usdttrc20") -> float:
        """
        Get the minimum payment amount for a specific currency pair.
        """
        api_key = os.getenv("NOWPAYMENTS_API_KEY")
        if not api_key:
            return 0.0
            
        url = f"https://api.nowpayments.io/v1/min-amount?currency_from={currency_from}&currency_to={currency_to}"
        headers = {"x-api-key": api_key}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return float(data.get("min_amount", 0))
                return 0.0
        except Exception as e:
            print(f"⚠️ Failed to check min amount: {e}")
            return 0.0

    async def create_now_invoice(
        self,
        amount: float,
        fix_id: str,
        description: str = None
    ) -> Optional[str]:
        """
        Generates a real crypto payment link via NOWPayments.
        """
        api_key = os.getenv("NOWPAYMENTS_API_KEY")
        pay_currency = os.getenv("PAY_CURRENCY", "usdttrc20")
        
        if not api_key:
            return None
            
        # 1. Check Minimum Amount Logic
        min_amount = await self.get_min_payment_amount("usd", pay_currency)
        safe_min = min_amount * 1.10
        
        if amount < safe_min:
            print(f"⚠️ Billing Skipped: Amount ${amount:.2f} is below network minimum (${safe_min:.2f} for {pay_currency})")
            return None
        
        url = "https://api.nowpayments.io/v1/invoice"
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "price_amount": amount,
            "price_currency": "usd",
            "pay_currency": pay_currency,
            "order_id": fix_id,
            "order_description": description or f"AI Outcome Resolution: {fix_id}",
            "is_fixed_rate": True,
            "is_fee_paid_by_user": True
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    invoice_url = data.get("invoice_url")
                    print(f"💳 Invoice created: {invoice_url}")
                    return invoice_url
                else:
                    return None
                    
        except Exception as e:
            print(f"💰 Payment Error: {e}")
            return None
    
    async def _send_telegram_notification(self, record: BillingRecord):
        """Send a notification to Telegram about the successful fix."""
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        # We need async total calculation
        daily_total = await self.get_daily_total_async()
        
        message = f"""💰 **NEW FIX COMPLETED**

🏢 **Client:** {record.company_name}
🔧 **Fix Type:** {record.fix_type.upper()}
📝 **Issue:** {record.error_summary[:50]}...
⚡ **Time:** {record.execution_time_ms:.0f}ms

💵 **Earned:** ${record.amount_usd:.2f}
📈 **Today:** ${daily_total:.2f}
"""
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                })
        except Exception as e:
            print(f"Warning: Telegram notification failed: {e}")
    
    async def get_daily_total_async(self) -> float:
        """Get total earnings for today (Async)."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        async with async_session_maker() as session:
            stmt = select(func.sum(BillingModel.amount_usd)).where(
                BillingModel.timestamp.like(f"{today_str}%"),
                BillingModel.status == "completed"
            )
            result = await session.execute(stmt)
            total = result.scalar() or 0.0
            return float(total)

    async def get_stats_async(self) -> dict:
        """Get comprehensive billing statistics (Async)."""
        async with async_session_maker() as session:
            # Total earnings
            total_stmt = select(func.sum(BillingModel.amount_usd)).where(BillingModel.status == "completed")
            total_earnings = (await session.execute(total_stmt)).scalar() or 0.0
            
            # Count
            count_stmt = select(func.count(BillingModel.id)).where(BillingModel.status == "completed")
            total_fixes = (await session.execute(count_stmt)).scalar() or 0
            
            # Today
            today_earnings = await self.get_daily_total_async()
            
            return {
                "total_fixes": total_fixes,
                "total_earnings": float(total_earnings),
                "daily_earnings": today_earnings,
                # Simplify for now
                "monthly_earnings": 0.0,
                "avg_fix_time_ms": 0.0,
                "total_rows_fixed": 0,
                "unique_clients": 0
            }


# Singleton instance
_billing_instance: Optional[BillingSystem] = None


def get_billing() -> BillingSystem:
    """Get or create the singleton billing instance."""
    global _billing_instance
    if _billing_instance is None:
        _billing_instance = BillingSystem()
    return _billing_instance
