"""
lead_hunter.py - Autonomous Lead Generation Agent (PostgreSQL Version)
Finds potential customers on Reddit/Twitter and sends outreach emails
"""

import os
import json
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

# Import DB layer
from core import database
from core.database import LeadModel, init_db

load_dotenv()


@dataclass
class Lead:
    """Represents a potential customer lead."""
    lead_id: str
    platform: str
    username: str
    email: Optional[str]
    post_content: str
    post_url: str
    keywords_matched: List[str]
    status: str
    first_contact_date: Optional[str]
    last_contact_date: Optional[str]
    follow_up_count: int
    notes: str
    created_at: str


class LeadHunter:
    """
    Autonomous lead generation agent.
    Finds, qualifies, and reaches out to potential customers.
    """
    
    HUNTING_KEYWORDS = [
        # Database Issues
        "database error", "sql error", "sqlite error", "postgres error", "mysql error",
        "database crashed", "db not working", "production database down",
        
        # General Coding & APIs
        "api error 500", "python script error", "javascript undefined", "react rendering error",
        "api connection failed", "webhook not working", "stripe payment failed",
        
        # Automation & Scraping (High Value)
        "web scraping blocked", "selenium error", "beautifulsoup helps", "automate excel",
        "need python script", "automate data entry", "convert pdf to csv",
        
        # Distress Signals
        "stuck on this bug", "code help needed", "willing to pay for fix", 
        "urgent help needed coding", "developer needed asap"
    ]
    
    # Dynamic list that gets updated
    DYNAMIC_TRENDS = []
    
    TARGET_SUBREDDITS = [
        "webdev", "programming", "learnprogramming", "SaaS", "startups",
        "Entrepreneur", "smallbusiness", "techsupport", "database", "sql",
        "django", "flask", "laravel",
        # New Additions
        "learnpython", "webscraping", "automation", "freelance_forhire", 
        "aws", "reactjs", "node"
    ]
    
    def __init__(self):
        # Email config
        self.smtp_email = os.getenv("OUTREACH_EMAIL")
        self.smtp_password = os.getenv("OUTREACH_EMAIL_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        
        # Telegram
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        # AI
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        
        # Rate limiting
        self.max_outreach_per_day = int(os.getenv("MAX_OUTREACH_PER_DAY", "20"))
        
    async def _ensure_db_ready(self):
        """Ensure tables exist."""
        await init_db()
    
    def _generate_lead_id(self, platform: str, username: str, post_url: str) -> str:
        """Generate unique lead ID."""
        content = f"{platform}:{username}:{post_url}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    async def _is_duplicate_async(self, lead_id: str) -> bool:
        """Check if lead already exists."""
        async with database.async_session_maker() as session:
            stmt = select(LeadModel).where(LeadModel.lead_id == lead_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
            
    async def _save_lead_async(self, lead: Lead):
        """Save a new lead to DB."""
        new_lead = LeadModel(
            lead_id=lead.lead_id,
            platform=lead.platform,
            username=lead.username,
            email=lead.email,
            post_content=lead.post_content,
            post_url=lead.post_url,
            keywords_matched=json.dumps(lead.keywords_matched),
            status=lead.status,
            first_contact_date=lead.first_contact_date,
            last_contact_date=lead.last_contact_date,
            follow_up_count=lead.follow_up_count,
            notes=lead.notes,
            created_at=lead.created_at
        )
        
        async with database.async_session_maker() as session:
            session.add(new_lead)
            await session.commit()
    
    async def _update_lead_async(self, lead: Lead):
        """Update an existing lead in DB."""
        async with database.async_session_maker() as session:
            stmt = select(LeadModel).where(LeadModel.lead_id == lead.lead_id)
            result = await session.execute(stmt)
            lead_db = result.scalar_one_or_none()
            
            if lead_db:
                lead_db.status = lead.status
                lead_db.first_contact_date = lead.first_contact_date
                lead_db.last_contact_date = lead.last_contact_date
                lead_db.follow_up_count = lead.follow_up_count
                lead_db.notes = lead.notes
                await session.commit()

    async def get_stats_async(self) -> Dict:
        """Get lead hunting statistics."""
        await self._ensure_db_ready()
        
        async with async_session_maker() as session:
            stmt = select(LeadModel)
            result = await session.execute(stmt)
            leads = result.scalars().all()
            
            return {
                "total_leads": len(leads),
                "new": len([l for l in leads if l.status == "new"]),
                "contacted": len([l for l in leads if l.status == "contacted"]),
                "followed_up": len([l for l in leads if "followed_up" in l.status]),
                "replied": len([l for l in leads if l.status == "replied"]),
                "converted": len([l for l in leads if l.status == "converted"]),
                "dead": len([l for l in leads if l.status == "dead"]),
            }

    # ... keeping the core hunting logic ...
    
    async def hunt_reddit(self) -> List[Lead]:
        """Search Reddit for potential customers."""
        await self._ensure_db_ready()
        new_leads = []
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            # Combine static + dynamic keywords
            all_keywords = self.HUNTING_KEYWORDS + self.DYNAMIC_TRENDS
            
            for subreddit in self.TARGET_SUBREDDITS[:5]:
                for keyword in all_keywords[:10]: # Limit for rate limits
                    try:
                        url = f"https://www.reddit.com/r/{subreddit}/search.json"
                        params = {"q": keyword, "restrict_sr": "on", "sort": "new", "limit": 5, "t": "month"}
                        
                        response = await client.get(url, params=params, headers=headers)
                        
                        if response.status_code == 200:
                            data = response.json()
                            posts = data.get("data", {}).get("children", [])
                            
                            for post in posts:
                                post_data = post.get("data", {})
                                username = post_data.get("author", "")
                                
                                if username in ["[deleted]", "AutoModerator", ""]:
                                    continue
                                    
                                post_url = f"https://reddit.com{post_data.get('permalink', '')}"
                                lead_id = self._generate_lead_id("reddit", username, post_url)
                                
                                if await self._is_duplicate_async(lead_id):
                                    continue
                                    
                                content = f"{post_data.get('title', '')} {post_data.get('selftext', '')}"
                                matched = [keyword]
                                
                                lead = Lead(
                                    lead_id=lead_id,
                                    platform="reddit",
                                    username=username,
                                    email=None,
                                    post_content=content[:500],
                                    post_url=post_url,
                                    keywords_matched=matched,
                                    status="new",
                                    first_contact_date=None,
                                    last_contact_date=None,
                                    follow_up_count=0,
                                    notes="",
                                    created_at=datetime.now().isoformat()
                                )
                                new_leads.append(lead)
                                await self._save_lead_async(lead)
                                print(f"   ✅ Found lead: u/{username}")
                        
                        await asyncio.sleep(2)
                        
                    except Exception as e:
                        print(f"❌ Error hunting r/{subreddit}: {e}")
                        continue
        
        return new_leads

    # ... (skipping message generation for brevity, assumes same logic) ...
    async def generate_personalized_message(self, lead: Lead) -> str:
        """Use AI to generate a personalized outreach message."""
        if not self.openrouter_key:
            return "Hey, I saw your post about database issues. I have a tool that might help!"
            
        prompt = f"""You are a helpful sales rep.
A user posted: "{lead.post_content[:300]}"
Write a SHORT, helpful Reddit comment (under 100 words).
Offer genuine help for their database problem. Mention you have an AI tool.
Don't use greetings or subject lines."""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openrouter_key}"},
                    json={"model": "deepseek/deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
        except:
            pass
        return "Hey, looks like a DB issue. I built an AI tool that fixes these automatically. Let me know if you want to try it!"

    async def send_reddit_dm(self, lead: Lead, message: str) -> bool:
        """
        Send a Reddit DM (or prepare the link for manual sending).
        """
        subject = "Quick question about your post"
        body = message
        # Reddit compose link format: https://www.reddit.com/message/compose/?to=USERNAME&subject=SUBJECT&message=BODY
        import urllib.parse
        encoded_subject = urllib.parse.quote(subject)
        encoded_body = urllib.parse.quote(body)
        dm_url = f"https://www.reddit.com/message/compose/?to={lead.username}&subject={encoded_subject}&message={encoded_body}"
        
        print(f"\n📨 [ACTION REQUIRED] Click to Send DM to u/{lead.username}:")
        print(f"🔗 {dm_url}\n")
        
        lead.status = "contacted"
        lead.first_contact_date = datetime.now().isoformat()
        lead.last_contact_date = datetime.now().isoformat()
        await self._update_lead_async(lead)
        
        await self._send_telegram_alert(f"📤 **Outreach Generated**\n👤 u/{lead.username}\n🔗 [Send DM]({dm_url})")
        return True

    async def _send_telegram_alert(self, message: str):
        """Send Telegram notification."""
        if not self.telegram_token: return
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    json={"chat_id": self.telegram_chat_id, "text": message, "parse_mode": "Markdown"}
                )
        except: pass

    async def scan_for_trends(self):
        """
        AI Trend Surfer 🏄
        Scans broad tech subreddits for 'hot' topics and identifies profitable trends.
        """
        print("🏄 Scanning for trending problems...")
        trend_sources = ["technology", "artificial", "ChatGPT", "startups"]
        headers = {"User-Agent": "Mozilla/5.0"}
        
        combined_titles = ""
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for sub in trend_sources:
                    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=5"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        posts = resp.json().get("data", {}).get("children", [])
                        for p in posts:
                            combined_titles += p["data"].get("title", "") + "\n"
        except Exception as e:
            print(f"⚠️ Trend scan failed: {e}")
            return

        # Ask AI to identify profitable keywords
        if self.openrouter_key and combined_titles:
            prompt = f"""
            Analyze these recent tech post titles:\n{combined_titles}\n
            Identify 3 specific, technical problems or emerging tools people are struggling with RIGHT NOW.
            Return ONLY 3 short keyword phrases (e.g. "openai api error", "langchain bug", "vector db setup").
            Separated by commas. No other text.
            """
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.openrouter_key}"},
                        json={"model": "deepseek/deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
                    )
                    if response.status_code == 200:
                        content = response.json()["choices"][0]["message"]["content"]
                        new_trends = [k.strip() for k in content.split(",") if k.strip()]
                        
                        # Update dynamic list
                        self.DYNAMIC_TRENDS = new_trends[:3]
                        print(f"🔥 TRENDS DETECTED: {self.DYNAMIC_TRENDS}")
                        await self._send_telegram_alert(f"🏄 **Trend Alert**\nSurfing these new waves: {self.DYNAMIC_TRENDS}")
            except Exception as e:
                print(f"⚠️ Trend analysis failed: {e}")

    async def run_hunting_cycle(self):
        """Main hunting cycle."""
        print("🎯 Starting lead hunting cycle...")
        
        # 1. Update Trends
        await self.scan_for_trends()
        
        # 2. Hunt
        new_leads = await self.hunt_reddit()
        
        for lead in new_leads:
            msg = await self.generate_personalized_message(lead)
            await self.send_reddit_dm(lead, msg)
            await asyncio.sleep(60)
            
        print(f"✅ Hunting cycle complete. Found {len(new_leads)} leads.")


# Singleton instance
_hunter_instance: Optional[LeadHunter] = None

def get_hunter() -> LeadHunter:
    """Get or create the singleton hunter instance."""
    global _hunter_instance
    if _hunter_instance is None:
        _hunter_instance = LeadHunter()
    return _hunter_instance
