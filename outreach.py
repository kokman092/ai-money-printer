#!/usr/bin/env python3
"""
outreach.py - Manual Lead Outreach Script
Run this to generate personalized messages for all new leads
and open their Reddit profiles for manual DM.
"""

import asyncio
import webbrowser
from tools.lead_hunter import get_hunter

LANDING_URL = "https://web-production-d678.up.railway.app/"

async def main():
    hunter = get_hunter()
    leads = hunter._load_leads()
    
    new_leads = [l for l in leads if l.status == "new"]
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           🎯 AI MONEY PRINTER - OUTREACH MODE 🎯            ║
╠══════════════════════════════════════════════════════════════╣
║  Found {len(new_leads):3d} new leads to contact                           ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    for i, lead in enumerate(new_leads, 1):
        print(f"\n{'='*60}")
        print(f"LEAD {i}/{len(new_leads)}: u/{lead.username}")
        print(f"{'='*60}")
        print(f"Platform: {lead.platform}")
        print(f"Keywords: {', '.join(lead.keywords_matched)}")
        print(f"Post: {lead.post_url}")
        
        # Generate personalized message
        message = await hunter.generate_personalized_message(lead)
        
        print(f"\n📝 PERSONALIZED MESSAGE:")
        print("-" * 40)
        print(message)
        print("-" * 40)
        
        # Ask user what to do
        print(f"\nOptions:")
        print(f"  [o] Open Reddit post in browser")
        print(f"  [d] Open DM link (if possible)")
        print(f"  [s] Skip this lead")
        print(f"  [m] Mark as contacted")
        print(f"  [q] Quit")
        
        choice = input("\nYour choice: ").strip().lower()
        
        if choice == 'o':
            webbrowser.open(lead.post_url)
            print("✅ Opened in browser")
        elif choice == 'd':
            dm_url = f"https://www.reddit.com/message/compose/?to={lead.username}"
            webbrowser.open(dm_url)
            print(f"✅ Opened DM page for u/{lead.username}")
        elif choice == 'm':
            lead.status = "contacted"
            hunter._update_lead(lead)
            print(f"✅ Marked as contacted")
        elif choice == 'q':
            print("👋 Exiting...")
            break
        else:
            print("⏭️ Skipped")
    
    print(f"\n✅ Outreach session complete!")
    stats = hunter.get_stats()
    print(f"   Total leads: {stats['total_leads']}")
    print(f"   Contacted: {stats['contacted']}")
    print(f"   New: {stats['new']}")


if __name__ == "__main__":
    asyncio.run(main())
