import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8000"
ADMIN_KEY = os.getenv("WEBHOOK_SECRET", "admin_secret_key")

async def run_test_suite():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("🛠️  STARTING MULTI-AGENT TEST SUITE\n")

        # 1. Register a Mock Client
        print("📝 Step 1: Registering Test Client...")
        reg_resp = await client.post(
            f"{BASE_URL}/clients/register",
            params={
                "company_name": "TestCorp",
                "database_type": "sqlite",
                "connection_string": "data/test.db"
            },
            headers={"x-api-key": ADMIN_KEY}
        )
        
        if reg_resp.status_code != 200:
            print(f"❌ Failed to register: {reg_resp.text}")
            return
            
        client_data = reg_resp.json()
        api_key = client_data["api_key"]
        print(f"✅ Registered! API Key: {api_key}\n")

        # 2. Test Customer Support ($0.99)
        print("💬 Step 2: Testing Customer Support ($0.99)...")
        support_payload = {
            "customer_name": "John Doe",
            "issue": "I haven't received my refund for order #12345.",
            "priority": "high"
        }
        await client.post(
            f"{BASE_URL}/webhook/support",
            json=support_payload,
            headers={"x-api-key": api_key}
        )
        print("✅ Support ticket queued.\n")

        # 3. Test Sales Agent ($2.50)
        print("📈 Step 3: Testing Sales Agent ($2.50)...")
        sales_payload = {
            "lead_name": "Jane Smith",
            "lead_email": "jane@startup.com",
            "inquiry": "We are looking for an AI solution for our 50-person team."
        }
        await client.post(
            f"{BASE_URL}/webhook/sales",
            json=sales_payload,
            headers={"x-api-key": api_key}
        )
        print("✅ Sales lead queued.\n")

        # 4. Wait for Background Processing
        print("⏳ Waiting 5 seconds for AI processing...")
        await asyncio.sleep(5)

        # 5. Check the "Money Printer" Stats
        print("\n💰 FINAL EARNINGS CHECK:")
        stats_resp = await client.get(
            f"{BASE_URL}/stats",
            headers={"x-api-key": ADMIN_KEY}
        )
        stats = stats_resp.json()
        
        print(f"---------------------------------")
        print(f"Total Successful Fixes: {stats['total_fixes']}")
        print(f"Total Earnings:         ${stats['total_earnings']:.2f}")
        print(f"Avg Processing Time:    {stats['avg_fix_time_ms']:.0f}ms")
        print(f"---------------------------------")

if __name__ == "__main__":
    asyncio.run(run_test_suite())