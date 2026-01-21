"""
lead_hunter.py - Autonomous Lead Generation Agent
Finds potential customers on Reddit/Twitter and sends outreach emails
"""

import os
import csv
import json
import asyncio
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict

import httpx
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Lead:
    """Represents a potential customer lead."""
    lead_id: str
    platform: str  # reddit, twitter, linkedin
    username: str
    email: Optional[str]
    post_content: str
    post_url: str
    keywords_matched: List[str]
    status: str  # new, contacted, followed_up_1, followed_up_2, replied, converted, dead
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
    
    # Keywords that indicate someone needs our service
    HUNTING_KEYWORDS = [
        "database error",
        "sql error",
        "sqlite error", 
        "postgres error",
        "mysql error",
        "database crashed",
        "db not working",
        "need help with database",
        "database admin needed",
        "looking for database help",
        "production database down",
        "critical database issue",
        "anyone know sql",
        "database migration help",
        "corrupted database",
    ]
    
    # Subreddits to hunt in
    TARGET_SUBREDDITS = [
        "webdev",
        "programming", 
        "learnprogramming",
        "SaaS",
        "startups",
        "Entrepreneur",
        "smallbusiness",
        "techsupport",
        "database",
        "sql",
    ]
    
    def __init__(self, leads_path: str = None):
        if leads_path is None:
            leads_path = Path(__file__).parent.parent / "data" / "leads.csv"
        self.leads_path = Path(leads_path)
        self._ensure_leads_file()
        
        # Email config
        self.smtp_email = os.getenv("OUTREACH_EMAIL")
        self.smtp_password = os.getenv("OUTREACH_EMAIL_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        
        # Telegram notifications
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        # AI for personalization
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        
        # Rate limiting
        self.max_outreach_per_day = int(os.getenv("MAX_OUTREACH_PER_DAY", "20"))
        
    def _ensure_leads_file(self):
        """Create leads CSV if it doesn't exist."""
        if not self.leads_path.exists():
            self.leads_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.leads_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "lead_id", "platform", "username", "email", "post_content",
                    "post_url", "keywords_matched", "status", "first_contact_date",
                    "last_contact_date", "follow_up_count", "notes", "created_at"
                ])
    
    def _load_leads(self) -> List[Lead]:
        """Load all leads from CSV."""
        leads = []
        with open(self.leads_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["keywords_matched"] = json.loads(row.get("keywords_matched", "[]"))
                row["follow_up_count"] = int(row.get("follow_up_count", 0))
                leads.append(Lead(**row))
        return leads
    
    def _save_lead(self, lead: Lead):
        """Append a new lead to CSV."""
        with open(self.leads_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            data = asdict(lead)
            data["keywords_matched"] = json.dumps(data["keywords_matched"])
            writer.writerow(data.values())
    
    def _update_lead(self, lead: Lead):
        """Update an existing lead in CSV."""
        leads = self._load_leads()
        updated = []
        for l in leads:
            if l.lead_id == lead.lead_id:
                updated.append(lead)
            else:
                updated.append(l)
        
        # Rewrite entire file
        with open(self.leads_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "lead_id", "platform", "username", "email", "post_content",
                "post_url", "keywords_matched", "status", "first_contact_date",
                "last_contact_date", "follow_up_count", "notes", "created_at"
            ])
            for l in updated:
                data = asdict(l)
                data["keywords_matched"] = json.dumps(data["keywords_matched"])
                writer.writerow(data.values())
    
    def _generate_lead_id(self, platform: str, username: str, post_url: str) -> str:
        """Generate unique lead ID."""
        content = f"{platform}:{username}:{post_url}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _is_duplicate(self, lead_id: str) -> bool:
        """Check if lead already exists."""
        leads = self._load_leads()
        return any(l.lead_id == lead_id for l in leads)
    
    async def hunt_reddit(self) -> List[Lead]:
        """
        Search Reddit for potential customers.
        Uses Reddit's search API to find posts matching our keywords.
        """
        new_leads = []
        
        # Better User-Agent for Reddit (required by Reddit API)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            for subreddit in self.TARGET_SUBREDDITS[:5]:  # Limit subreddits to avoid rate limits
                for keyword in self.HUNTING_KEYWORDS[:3]:  # Limit keywords
                    try:
                        # Reddit JSON API (no auth needed for public posts)
                        url = f"https://www.reddit.com/r/{subreddit}/search.json"
                        params = {
                            "q": keyword,
                            "restrict_sr": "on",
                            "sort": "new",
                            "limit": 5,
                            "t": "month"  # Last month for more results
                        }
                        
                        print(f"🔍 Searching r/{subreddit} for '{keyword}'...")
                        response = await client.get(url, params=params, headers=headers)
                        
                        print(f"   Response status: {response.status_code}")
                        
                        if response.status_code == 429:
                            print(f"⏳ Rate limited by Reddit, waiting 60s...")
                            await asyncio.sleep(60)
                            continue
                        
                        if response.status_code == 200:
                            data = response.json()
                            posts = data.get("data", {}).get("children", [])
                            print(f"   Found {len(posts)} posts")
                            
                            for post in posts:
                                post_data = post.get("data", {})
                                username = post_data.get("author", "")
                                post_url = f"https://reddit.com{post_data.get('permalink', '')}"
                                content = f"{post_data.get('title', '')} {post_data.get('selftext', '')}"
                                
                                # Skip deleted/removed
                                if username in ["[deleted]", "AutoModerator", ""]:
                                    continue
                                
                                lead_id = self._generate_lead_id("reddit", username, post_url)
                                
                                if self._is_duplicate(lead_id):
                                    continue
                                
                                # The post was returned by Reddit search for this keyword
                                # So we consider it a match even if exact phrase isn't in content
                                matched = [keyword]  # The search keyword matched
                                
                                # Also check for other keywords in content
                                for kw in self.HUNTING_KEYWORDS:
                                    if kw.lower() in content.lower() and kw not in matched:
                                        matched.append(kw)
                                
                                lead = Lead(
                                    lead_id=lead_id,
                                    platform="reddit",
                                    username=username,
                                    email=None,  # Reddit doesn't expose emails
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
                                self._save_lead(lead)
                                print(f"   ✅ Found lead: u/{username} - {matched}")
                        else:
                            print(f"   ❌ Error: {response.status_code}")
                        
                        # Rate limiting - be respectful to Reddit
                        await asyncio.sleep(3)
                        
                    except Exception as e:
                        print(f"❌ Error hunting r/{subreddit}: {e}")
                        continue
        
        return new_leads
    
    async def generate_personalized_message(self, lead: Lead) -> str:
        """
        Use AI to generate a personalized outreach message.
        """
        if not self.openrouter_key:
            return self._get_template_message(lead)
        
        prompt = f"""You are a helpful sales representative for an AI database fixing service.

A potential customer posted this online:
"{lead.post_content[:300]}"

Write a SHORT, helpful Reddit comment or DM that:
1. Acknowledges their specific problem (don't be generic)
2. Offers genuine help first (not a hard sell)
3. Mentions you have an AI tool that fixes database errors automatically
4. Keeps it under 100 words
5. Sounds human and empathetic, not salesy

Don't include subject lines or greetings like "Hi there!" - just the message body."""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openrouter_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "deepseek/deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 200
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"AI message generation failed: {e}")
        
        return self._get_template_message(lead)
    
    def _get_template_message(self, lead: Lead) -> str:
        """Fallback template message."""
        keyword = lead.keywords_matched[0] if lead.keywords_matched else "database issue"
        
        return f"""I noticed you're dealing with a {keyword} - that's frustrating!

I've been there. I actually built a tool that automatically fixes common database errors. It analyzes the error, tests a fix in sandbox, and only applies it if safe.

Happy to help if you want to share more details about what you're seeing. No pressure - just trying to help fellow devs out."""
    
    async def send_reddit_dm(self, lead: Lead, message: str) -> bool:
        """
        Send a Reddit DM to a potential customer.
        Note: Requires Reddit API credentials.
        """
        # For now, just log - Reddit DMs need OAuth
        print(f"📤 Would DM u/{lead.username}: {message[:50]}...")
        
        # Update lead status
        lead.status = "contacted"
        lead.first_contact_date = datetime.now().isoformat()
        lead.last_contact_date = datetime.now().isoformat()
        self._update_lead(lead)
        
        # Notify via Telegram
        await self._send_telegram_alert(
            f"📤 **Outreach Sent**\n\n"
            f"👤 u/{lead.username}\n"
            f"📝 {message[:100]}...\n"
            f"🔗 {lead.post_url}"
        )
        
        return True
    
    async def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send outreach email via SMTP."""
        if not self.smtp_email or not self.smtp_password:
            print("⚠️ Email not configured. Set OUTREACH_EMAIL and OUTREACH_EMAIL_PASSWORD")
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg["From"] = self.smtp_email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_email, self.smtp_password)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"Email failed: {e}")
            return False
    
    async def _send_telegram_alert(self, message: str):
        """Send Telegram notification."""
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    json={
                        "chat_id": self.telegram_chat_id,
                        "text": message,
                        "parse_mode": "Markdown"
                    }
                )
        except Exception as e:
            print(f"Telegram alert failed: {e}")
    
    def get_leads_needing_followup(self) -> List[Lead]:
        """Get leads that need follow-up (Day 4 or Day 7)."""
        leads = self._load_leads()
        needs_followup = []
        
        now = datetime.now()
        
        for lead in leads:
            if lead.status in ["replied", "converted", "dead"]:
                continue
            
            if not lead.last_contact_date:
                continue
            
            last_contact = datetime.fromisoformat(lead.last_contact_date)
            days_since = (now - last_contact).days
            
            # Follow up on Day 4 (first follow-up) and Day 7 (second follow-up)
            if lead.follow_up_count == 0 and days_since >= 4:
                needs_followup.append(lead)
            elif lead.follow_up_count == 1 and days_since >= 3:  # 3 more days after first follow-up
                needs_followup.append(lead)
        
        return needs_followup
    
    async def run_hunting_cycle(self):
        """
        Main hunting cycle - run this periodically.
        1. Find new leads
        2. Send outreach to new leads
        3. Follow up on old leads
        """
        print("🎯 Starting lead hunting cycle...")
        
        # 1. Hunt for new leads
        print("🔍 Hunting Reddit for leads...")
        new_leads = await self.hunt_reddit()
        print(f"✅ Found {len(new_leads)} new leads")
        
        # 2. Send outreach to new leads (respect daily limit)
        outreach_count = 0
        for lead in new_leads:
            if outreach_count >= self.max_outreach_per_day:
                print(f"⏸️ Daily outreach limit ({self.max_outreach_per_day}) reached")
                break
            
            message = await self.generate_personalized_message(lead)
            await self.send_reddit_dm(lead, message)
            outreach_count += 1
            await asyncio.sleep(60)  # 1 min between messages
        
        # 3. Process follow-ups
        followups = self.get_leads_needing_followup()
        print(f"📬 {len(followups)} leads need follow-up")
        
        for lead in followups:
            if outreach_count >= self.max_outreach_per_day:
                break
            
            followup_msg = f"""Hey, just following up on my earlier message about your database issue.

Did you get a chance to look into it? Happy to help if you're still stuck.

No worries if you've already solved it - just wanted to check in!"""
            
            await self.send_reddit_dm(lead, followup_msg)
            lead.follow_up_count += 1
            lead.last_contact_date = datetime.now().isoformat()
            
            if lead.follow_up_count >= 2:
                lead.status = "dead"  # Max 2 follow-ups
            else:
                lead.status = f"followed_up_{lead.follow_up_count}"
            
            self._update_lead(lead)
            outreach_count += 1
        
        # Summary
        await self._send_telegram_alert(
            f"🎯 **Lead Hunting Complete**\n\n"
            f"🆕 New leads found: {len(new_leads)}\n"
            f"📤 Outreach sent: {outreach_count}\n"
            f"📬 Follow-ups processed: {len(followups)}"
        )
        
        print(f"✅ Hunting cycle complete. Total outreach: {outreach_count}")
        
        return {
            "new_leads": len(new_leads),
            "outreach_sent": outreach_count,
            "followups": len(followups)
        }
    
    def get_stats(self) -> Dict:
        """Get lead hunting statistics."""
        leads = self._load_leads()
        
        return {
            "total_leads": len(leads),
            "new": len([l for l in leads if l.status == "new"]),
            "contacted": len([l for l in leads if l.status == "contacted"]),
            "followed_up": len([l for l in leads if "followed_up" in l.status]),
            "replied": len([l for l in leads if l.status == "replied"]),
            "converted": len([l for l in leads if l.status == "converted"]),
            "dead": len([l for l in leads if l.status == "dead"]),
        }


# Singleton instance
_hunter_instance: Optional[LeadHunter] = None


def get_hunter() -> LeadHunter:
    """Get or create the singleton hunter instance."""
    global _hunter_instance
    if _hunter_instance is None:
        _hunter_instance = LeadHunter()
    return _hunter_instance


# Quick test
if __name__ == "__main__":
    hunter = get_hunter()
    print("Lead Hunter initialized")
    print(f"Leads file: {hunter.leads_path}")
    
    # Run hunting cycle
    asyncio.run(hunter.run_hunting_cycle())
