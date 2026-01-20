# AI Money Printer 💰

An autonomous AI-powered multi-agent service that makes money while you sleep.

## 🤖 Available Agents

| Agent | Endpoint | Price | Outcome |
|-------|----------|-------|---------|
| 🔧 **Database Fixer** | `/webhook/fix` | $5.00 | Per successful fix |
| 💬 **Customer Support** | `/webhook/support` | $0.99 | Per resolved ticket |
| 📈 **Sales Agent** | `/webhook/sales` | $2.50 | Per meeting booked |
| 📧 **Email Responder** | `/webhook/email` | $0.50 | Per email drafted |
| 📅 **Appointment Setter** | `/webhook/appointment` | $1.50 | Per confirmed booking |

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Edit `.env` with your API keys:

```env
# Required
OPENROUTER_API_KEY=your_openrouter_api_key
WEBHOOK_SECRET=your_admin_secret_key
ENCRYPTION_KEY=your_32_char_encryption_key

# Optional (for Telegram notifications)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Pricing (can override per agent)
FIX_PRICE_USD=5.00
```

### 3. Run the Server

```bash
python main.py
```

## 📡 API Endpoints

### List Available Agents
```bash
GET /agents
```

### Database Fixer
```bash
POST /webhook/fix
Header: X-API-Key: <client_api_key>
Body: {
  "error_message": "UNIQUE constraint failed: users.email",
  "database_type": "sqlite"
}
```

### Customer Support
```bash
POST /webhook/support
Header: X-API-Key: <client_api_key>
Body: {
  "customer_name": "John Smith",
  "customer_email": "john@example.com",
  "issue": "I can't access my account",
  "order_id": "ORD-12345"
}
```

### Sales Agent
```bash
POST /webhook/sales
Header: X-API-Key: <client_api_key>
Body: {
  "lead_name": "Jane Doe",
  "lead_email": "jane@company.com",
  "company": "Acme Corp",
  "inquiry": "Looking for automation solutions",
  "budget": "$5000-10000"
}
```

### Email Responder
```bash
POST /webhook/email
Header: X-API-Key: <client_api_key>
Body: {
  "from_email": "sender@example.com",
  "subject": "Partnership Inquiry",
  "body": "Hi, we're interested in partnering with you..."
}
```

### Appointment Setter
```bash
POST /webhook/appointment
Header: X-API-Key: <client_api_key>
Body: {
  "client_name": "Bob Wilson",
  "client_email": "bob@example.com",
  "preferred_times": ["2026-01-21 10:00", "2026-01-21 14:00"],
  "meeting_type": "video"
}
```

### Universal Endpoint (Any Agent)
```bash
POST /webhook/universal
Header: X-API-Key: <client_api_key>
Body: {
  "agent_type": "customer_support",
  "data": { ... },
  "context": "Optional additional context"
}
```

## 🔄 The Workflow

```
1. Client System → Webhook → Request received
2. Scout Check → Is this a paid client?
3. AI Brain → Process with DeepSeek
4. Safety Layer:
   - Database: Sandbox dry-run test
   - Support/Sales: Content quality check
5. Apply Action → Send response / Fix database
6. Billing → Log earnings + Telegram notification 💰
```

## 📁 Project Structure

```
ai_money_printer/
├── core/
│   ├── agents.py         # 🤖 Multi-agent configurations
│   ├── brain.py          # 🧠 AI via OpenRouter/DeepSeek
│   └── safety.py         # 🔒 Code + Content verification
├── tools/
│   ├── scout.py          # 👤 Client verification
│   ├── database_fixer.py # 🔧 SQL/Python execution
│   └── billing.py        # 💰 Logging & Telegram alerts
├── data/
│   ├── billing_log.csv   # 📊 Earnings record
│   └── client_vault.json # 🔐 Encrypted client data
├── main.py               # 🚀 FastAPI multi-agent listener
├── requirements.txt      # Dependencies
├── README.md             # This file
└── .env                  # API keys (keep secret!)
```

## 🔒 Security Features

- **API Key Authentication** - Each client has unique keys
- **Encrypted Connections** - Database strings are encrypted
- **Code Safety** - Dangerous SQL/Python patterns blocked
- **Content Safety** - Forbidden words & tone checking
- **Sandbox Testing** - Dry-run before live execution
- **Row Limits** - Maximum affected rows limit
- **Automatic Rollback** - On failure

## 💰 Billing Logic

Only charges when outcome is successful:

| Agent | Success Criteria |
|-------|------------------|
| Database Fixer | Fix applied successfully |
| Customer Support | `is_resolved: true` |
| Sales Agent | `meeting_booked: true` |
| Email Responder | `email_drafted: true` |
| Appointment Setter | `appointment_confirmed: true` |

## 📊 Monitoring

### Check Stats
```bash
curl "http://localhost:8000/stats" -H "X-API-Key: your_admin_secret"
```

### Recent Activity
```bash
curl "http://localhost:8000/stats/recent?limit=10" -H "X-API-Key: your_admin_secret"
```

## 🧪 Adding New Agents

1. Add configuration in `core/agents.py`:
```python
NEW_AGENT_CONFIG = AgentConfig(
    agent_type=AgentType.NEW_AGENT,
    name="New Agent",
    description="What it does",
    price_per_outcome=1.00,
    outcome_field="is_successful",
    success_value=True,
    system_prompt="You are...",
    ...
)
```

2. Register in `AGENT_CONFIGS` dict
3. Add endpoint in `main.py` (optional - can use `/webhook/universal`)

## 🌐 Integration Examples

### Zapier/Make Integration
Use webhooks to connect your existing tools:
1. Form submission → Support Agent
2. New email → Email Responder
3. Calendar request → Appointment Setter

### Direct API Integration
```python
import httpx

response = httpx.post(
    "http://your-server:8000/webhook/support",
    headers={"X-API-Key": "your_client_key"},
    json={
        "customer_name": "John",
        "issue": "Can't login"
    }
)
```

---

**Made with 🤖 by AI Money Printer - Your 24/7 Autonomous Revenue Machine**
