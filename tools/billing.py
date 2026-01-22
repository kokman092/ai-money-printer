"""
billing.py - Outcome Tracker & Billing
Turns successful fixes into cash - only runs after safety.py green light
"""

import os
import csv
import httpx
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


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
    status: str  # "completed", "pending", "failed"
    execution_time_ms: float
    rows_affected: int


class BillingSystem:
    """
    The outcome tracker that:
    1. Logs every successful fix
    2. Sends Telegram notifications
    3. Tracks earnings
    """
    
    def __init__(self, log_path: str = None):
        if log_path is None:
            log_path = Path(__file__).parent.parent / "data" / "billing_log.csv"
        
        self.log_path = Path(log_path)
        self.fix_price = float(os.getenv("FIX_PRICE_USD", "5.00"))
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        self._ensure_log_exists()
    
    def _ensure_log_exists(self):
        """Create the billing log file with headers if it doesn't exist."""
        if not self.log_path.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.log_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "client_id",
                    "company_name", 
                    "fix_id",
                    "fix_type",
                    "error_summary",
                    "amount_usd",
                    "status",
                    "execution_time_ms",
                    "rows_affected"
                ])
    
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
        """
        Log a successful fix and trigger billing.
        
        Args:
            client_id: The client's unique ID
            company_name: Human-readable company name
            fix_id: Unique identifier for this fix
            fix_type: "sql" or "python"
            error_summary: Brief description of what was fixed
            execution_time_ms: How long the fix took
            rows_affected: Number of database rows affected
            custom_amount: Override the default fix price
        
        Returns:
            BillingRecord of the logged transaction
        """
        amount = custom_amount if custom_amount is not None else self.fix_price
        
        record = BillingRecord(
            timestamp=datetime.now().isoformat(),
            client_id=client_id,
            company_name=company_name,
            fix_id=fix_id,
            fix_type=fix_type,
            error_summary=error_summary[:100],  # Truncate for CSV
            amount_usd=amount,
            status="completed",
            execution_time_ms=execution_time_ms,
            rows_affected=rows_affected
        )
        
        # Write to CSV
        with open(self.log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                record.timestamp,
                record.client_id,
                record.company_name,
                record.fix_id,
                record.fix_type,
                record.error_summary,
                record.amount_usd,
                record.status,
                record.execution_time_ms,
                record.rows_affected
            ])
        
        # Send Telegram notification
        await self._send_telegram_notification(record)
        
        return record
    
    async def _send_telegram_notification(self, record: BillingRecord):
        """Send a notification to Telegram about the successful fix."""
        if not self.telegram_token or not self.telegram_chat_id:
            return  # Telegram not configured
        
        # Get daily total
        daily_total = self.get_daily_total()
        monthly_total = self.get_monthly_total()
        
        message = f"""💰 **NEW FIX COMPLETED**

🏢 **Client:** {record.company_name}
🔧 **Fix Type:** {record.fix_type.upper()}
📝 **Issue:** {record.error_summary}
⚡ **Time:** {record.execution_time_ms:.0f}ms
📊 **Rows:** {record.rows_affected}

💵 **Earned:** ${record.amount_usd:.2f}
📈 **Today:** ${daily_total:.2f}
📅 **This Month:** ${monthly_total:.2f}
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
            # Don't fail the billing if Telegram fails
            print(f"Warning: Telegram notification failed: {e}")
    
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
        # payout_wallet = os.getenv("MY_PAYOUT_WALLET") # Removed, using dashboard wallet
        pay_currency = os.getenv("PAY_CURRENCY", "usdttrc20")
        
        if not api_key or api_key == "your_nowpayments_api_key_here":
            print("⚠️ NOWPayments API key not configured in .env")
            return None
            
        # 1. Check Minimum Amount Logic
        min_amount = await self.get_min_payment_amount("usd", pay_currency)
        
        # Buffer: Add 10% safety margin for price fluctuations
        safe_min = min_amount * 1.10
        
        if amount < safe_min:
            print(f"⚠️ Billing Skipped: Amount ${amount:.2f} is below network minimum (${safe_min:.2f} for {pay_currency})")
            return None
        
        url = "https://api.nowpayments.io/v1/invoice"
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }
        
        # Note: payout_address removed - uses dashboard wallet setting instead
        # (API override requires enterprise whitelisting)
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
                    invoice_id = data.get("id")
                    print(f"💳 Invoice created: ID={invoice_id}, URL={invoice_url}")
                    return invoice_url
                else:
                    print(f"⚠️ NOWPayments error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"💰 Payment Error: {e}")
            return None
    
    async def check_payment_status(self, invoice_id: str) -> dict:
        """
        Check the payment status of an invoice.
        
        Returns:
            Payment status dict with 'payment_status' field
        """
        api_key = os.getenv("NOWPAYMENTS_API_KEY")
        
        if not api_key:
            return {"payment_status": "unknown", "error": "API key not configured"}
        
        url = f"https://api.nowpayments.io/v1/payment/{invoice_id}"
        headers = {"x-api-key": api_key}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                return response.json()
        except Exception as e:
            return {"payment_status": "error", "error": str(e)}
    
    def get_daily_total(self, date: datetime = None) -> float:
        """Get total earnings for a specific day."""
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime("%Y-%m-%d")
        total = 0.0
        
        with open(self.log_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["timestamp"].startswith(date_str) and row["status"] == "completed":
                    total += float(row["amount_usd"])
        
        return total
    
    def get_monthly_total(self, year: int = None, month: int = None) -> float:
        """Get total earnings for a specific month."""
        if year is None or month is None:
            now = datetime.now()
            year = now.year
            month = now.month
        
        month_str = f"{year}-{month:02d}"
        total = 0.0
        
        with open(self.log_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["timestamp"].startswith(month_str) and row["status"] == "completed":
                    total += float(row["amount_usd"])
        
        return total
    
    def get_all_time_total(self) -> float:
        """Get total earnings all time."""
        total = 0.0
        
        with open(self.log_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["status"] == "completed":
                    total += float(row["amount_usd"])
        
        return total
    
    def get_client_total(self, client_id: str) -> float:
        """Get total earnings from a specific client."""
        total = 0.0
        
        with open(self.log_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["client_id"] == client_id and row["status"] == "completed":
                    total += float(row["amount_usd"])
        
        return total
    
    def get_recent_fixes(self, limit: int = 10) -> list[BillingRecord]:
        """Get the most recent fixes."""
        records = []
        
        with open(self.log_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(BillingRecord(
                    timestamp=row["timestamp"],
                    client_id=row["client_id"],
                    company_name=row["company_name"],
                    fix_id=row["fix_id"],
                    fix_type=row["fix_type"],
                    error_summary=row["error_summary"],
                    amount_usd=float(row["amount_usd"]),
                    status=row["status"],
                    execution_time_ms=float(row["execution_time_ms"]),
                    rows_affected=int(row["rows_affected"])
                ))
        
        return records[-limit:]
    
    def get_stats(self) -> dict:
        """Get comprehensive billing statistics."""
        records = []
        
        with open(self.log_path, "r") as f:
            reader = csv.DictReader(f)
            records = list(reader)
        
        completed = [r for r in records if r["status"] == "completed"]
        
        if not completed:
            return {
                "total_fixes": 0,
                "total_earnings": 0.0,
                "daily_earnings": 0.0,
                "monthly_earnings": 0.0,
                "avg_fix_time_ms": 0.0,
                "total_rows_fixed": 0,
                "unique_clients": 0
            }
        
        return {
            "total_fixes": len(completed),
            "total_earnings": sum(float(r["amount_usd"]) for r in completed),
            "daily_earnings": self.get_daily_total(),
            "monthly_earnings": self.get_monthly_total(),
            "avg_fix_time_ms": sum(float(r["execution_time_ms"]) for r in completed) / len(completed),
            "total_rows_fixed": sum(int(r["rows_affected"]) for r in completed),
            "unique_clients": len(set(r["client_id"] for r in completed))
        }


# Singleton instance
_billing_instance: Optional[BillingSystem] = None


def get_billing() -> BillingSystem:
    """Get or create the singleton billing instance."""
    global _billing_instance
    if _billing_instance is None:
        _billing_instance = BillingSystem()
    return _billing_instance
