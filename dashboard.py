# ai_money_printer/dashboard.py
import pandas as pd
from tools.billing import get_billing

def run_dashboard():
    billing = get_billing()
    stats = billing.get_stats()
    
    print("\n" + "="*50)
    print(" 💰 AI MONEY PRINTER - LIVE PERFORMANCE 💰")
    print("="*50)
    
    # Financial Stats
    daily = stats['daily_earnings']
    print(f"💵 Total Earnings:      ${stats['total_earnings']:.2f}")
    print(f"☀️ Daily Earnings:      ${daily:.2f}")
    print("-"*50)

    # NEW: PROFIT PROJECTIONS
    print("📈 SCALE PROJECTIONS (If this continues):")
    print(f"🗓️ Monthly Estimate:   ${daily * 30:.2f}")
    print(f"🚀 Yearly Estimate:    ${daily * 365:.2f}")
    print("-"*50)
    
    # Operational Stats
    print(f"✅ Successful Tasks:    {stats['total_fixes']}")
    print(f"⚡ Avg. Response Time:  {stats['avg_fix_time_ms']:.0f}ms")
    print("="*50)

    # Recent Transactions
    print("\n📝 RECENT TRANSACTIONS:")
    try:
        df = pd.read_csv('data/billing_log.csv')
        print(df.tail(5)[['timestamp', 'fix_type', 'amount_usd']].to_string(index=False))
    except Exception:
        print("No transactions found.")
    
    print("\n" + "="*50)

if __name__ == "__main__":
    run_dashboard()