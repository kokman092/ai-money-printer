import requests

# 1. Your LIVE URL and the Client API Key from your vault
LIVE_URL = "https://your-public-url.com/webhook/support"
CLIENT_API_KEY = "client_a670e21be126bd22" 

test_data = {
    "customer_name": "Diagnostic Bot",
    "issue": "Checking if the printer is jammed."
}

try:
    print(f"📡 Pinging {LIVE_URL}...")
    response = requests.post(
        LIVE_URL, 
        headers={"x-api-key": CLIENT_API_KEY}, 
        json=test_data,
        timeout=10
    )
    
    print(f"⏱️ Status Code: {response.status_code}")
    print(f"📄 Server Response: {response.text}")

    if response.status_code == 401:
        print("❌ Error: Unauthorized. Your LIVE .env keys might not match your local ones.")
    elif response.status_code == 404:
        print("❌ Error: Not Found. Your server is running but the URL path is wrong.")
    elif response.status_code == 500:
        print("❌ Error: Server Crash. Check your cloud logs for a Python Traceback.")
    else:
        print("✅ Connection successful!")

except Exception as e:
    print(f"💥 Failed to connect: {e}")