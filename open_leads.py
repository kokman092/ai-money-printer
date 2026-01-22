#!/usr/bin/env python3
"""
open_all_leads.py - Opens all lead profiles in browser for manual outreach
Run this to open browser tabs for each lead.
"""

import webbrowser
import time
from tools.lead_hunter import get_hunter

def main():
    hunter = get_hunter()
    leads = hunter._load_leads()
    
    new_leads = [l for l in leads if l.status == "new"][:10]  # First 10 to avoid too many tabs
    
    print(f"\n🎯 Opening {len(new_leads)} lead profiles in browser...\n")
    
    for lead in new_leads:
        print(f"  Opening u/{lead.username}...")
        # Open their post first
        webbrowser.open(lead.post_url)
        time.sleep(0.5)
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                   ✅ BROWSER TABS OPENED!                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Now manually:                                               ║
║  1. Read each post                                           ║
║  2. Leave a helpful comment or DM                            ║
║  3. Include your link:                                       ║
║                                                              ║
║  https://web-production-d678.up.railway.app/                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

📝 Use this DM template:

Hey! I noticed your post about [their issue].

I actually built a tool that might help - it's an AI that 
automatically fixes database errors. It analyzes the error, 
tests the fix in a sandbox, and only applies if safe.

Check it out: https://web-production-d678.up.railway.app/

Happy to help if you have questions!
""")


if __name__ == "__main__":
    main()
