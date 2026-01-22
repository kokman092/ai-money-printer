import asyncio
from tools.billing import get_billing
from tools.lead_hunter import get_hunter

async def run_dashboard():
    billing = get_billing()
    hunter = get_hunter()
    
    # Fetch Stats
    bill_stats = await billing.get_stats_async()
    try:
        lead_stats = await hunter.get_stats_async()
    except Exception:
        lead_stats = {"total_leads": 0, "contacted": 0, "new": 0}

    print("\n" + "="*60)
    print(" 💰 AI MONEY PRINTER - DIAGNOSTIC DASHBOARD 💰")
    print("="*60)
    
    # 1. HUNTER STATUS (Top of Funnel)
    print("\n🏹 LEAD HUNTER STATUS:")
    print(f"   • Total Leads Found:   {lead_stats.get('total_leads', 0)}")
    print(f"   • Waiting for Reply:   {lead_stats.get('contacted', 0)}")
    print(f"   • New (Uncontacted):   {lead_stats.get('new', 0)}")
    
    if lead_stats.get('total_leads', 0) == 0:
        print("   ⚠️  WARNING: No leads found yet. Check internet/Reddit connection.")
    else:
        print("   ✅ Hunter is active and finding potential customers.")

    print("-" * 60)

    # 2. FINANCIAL STATUS (Bottom of Funnel)
    daily = bill_stats['daily_earnings']
    print("\n💵 FINANCIAL PERFORMANCE:")
    print(f"   • Total Earnings:      ${bill_stats['total_earnings']:.2f}")
    print(f"   • Daily Earnings:      ${daily:.2f}")
    
    if daily == 0 and lead_stats.get('contacted', 0) > 0:
        print("   ℹ️  Status: Outreach active, waiting for first sale.")
    elif daily == 0:
        print("   ℹ️  Status: System starting up.")

    print("-" * 60)

    # 3. PROJECTIONS
    if daily > 0:
        print("📈 SCALE PROJECTIONS:")
        print(f"   • Monthly Estimate:    ${daily * 30:.2f}")
        print(f"   • Yearly Estimate:     ${daily * 365:.2f}")
    else:
        print("📈 PROJECTIONS: Waiting for first sale to calculate velocity.")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(run_dashboard())