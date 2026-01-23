
import asyncio
from core.database import init_db
from tools.lead_hunter import get_hunter

async def test_hunter():
    print("🔬 Debug Hunter: Initializing DB...")
    await init_db()
    
    hunter = get_hunter()
    print("🔬 Debug Hunter: Starting Scan...")
    
    # Run scan manually
    leads = await hunter.hunt_reddit()
    
    print(f"🔬 Result: Found {len(leads)} leads.")
    for lead in leads:
        print(f"   - u/{lead.username}: {lead.post_content[:50]}...")

if __name__ == "__main__":
    asyncio.run(test_hunter())
