
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

# IMPORT MAIN MODULE to patch it
import main 

# MOCK EVERYTHING
mock_vault = MagicMock()
mock_vault._ensure_db_ready = AsyncMock(return_value=None)
mock_vault.register_client = AsyncMock(return_value=("client_123", "key_abc"))
mock_vault.list_active_clients_async = AsyncMock(return_value=[])

mock_billing = MagicMock()
mock_billing.create_now_invoice = AsyncMock(return_value="https://nowpayments.io/payment/?iid=mock_123")
mock_billing.log_success = AsyncMock()
mock_billing.telegram_token = "mock"
mock_billing.telegram_chat_id = "mock"

# Monkeypatch MAIN module directly
main.get_vault = lambda: mock_vault
main.get_billing = lambda: mock_billing
main.get_brain = lambda: MagicMock() # Mock brain too if needed
main.get_fixer = lambda: MagicMock()
main.get_safety = lambda: MagicMock()

# Also override dependency injection for endpoints
main.app.dependency_overrides[main.get_vault] = lambda: mock_vault
main.app.dependency_overrides[main.get_billing] = lambda: mock_billing

def test_checkout_flow():
    print("🧪 Verifying Revenue Optimization Flow (Mocked DB)...")
    
    # We use TestClient which triggers lifespan
    # Our mocks should prevent DB connection attempts
    
    with TestClient(main.app) as client:
        # 1. Test /buy-access
        print("\n1. Testing /buy-access endpoint...")
        payload = {
            "company_name": "Test Corp",
            "email": "cio@testcorp.com",
            "plan": "per-fix"
        }
        
        response = client.post("/buy-access", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print("   ✅ Success! Endpoint returned 200")
            print(f"   Payment URL: {data['payment_url']}")
            print(f"   Order ID: {data['order_id']}")
            print(f"   Temp API Key: {data['temp_api_key']}")
            
            assert data["client_id"] == "client_123"
            assert data["temp_api_key"] == "key_abc"
        else:
            print(f"   ❌ Failed: {response.status_code} - {response.text}")

        # 2. Test Partial Payment Webhook
        print("\n2. Testing /webhook/nowpayments (Finished)...")
        webhook_payload = {
            "payment_status": "finished",
            "order_id": "access_test_123",
            "pay_amount": 50,
            "pay_currency": "usdt",
            "actually_paid": 50
        }
        
        resp = client.post("/webhook/nowpayments", json=webhook_payload)
        if resp.status_code == 200:
             print("   ✅ Webhook processed successfully")
        else:
             print(f"   ❌ Webhook failed: {resp.status_code}")

if __name__ == "__main__":
    test_checkout_flow()
