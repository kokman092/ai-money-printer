"""
main.py - The 24/7 AI Money Printer Listener
FastAPI webhook server that processes client database errors automatically
"""

import os
import uuid
import time
import asyncio
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our modules
from core.brain import get_brain, AIBrain
from core.safety import get_safety, get_content_safety, SafetyLayer, RiskLevel
from core.agents import AgentType, get_agent_config, list_available_agents
from tools.scout import get_vault, ClientVault
from tools.database_fixer import get_fixer, DatabaseFixer
from tools.billing import get_billing, BillingSystem


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ErrorReport(BaseModel):
    """Incoming error report from a client's system."""
    error_message: str = Field(..., description="The database error message")
    error_code: Optional[str] = Field(None, description="Optional error code")
    database_type: Optional[str] = Field(None, description="sqlite, postgres, mysql")
    table_name: Optional[str] = Field(None, description="Affected table if known")
    additional_context: Optional[str] = Field(None, description="Any extra context")
    priority: str = Field("normal", description="low, normal, high")


class FixResponse(BaseModel):
    """Response after processing a fix."""
    fix_id: str
    status: str  # "queued", "processing", "completed", "failed"
    message: str
    execution_time_ms: Optional[float] = None
    rows_affected: Optional[int] = None
    amount_charged: Optional[float] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str
    stats: dict


# Multi-Agent Request Models
class SupportTicket(BaseModel):
    """Incoming customer support request."""
    customer_name: str = Field(..., description="Customer's name")
    customer_email: Optional[str] = Field(None, description="Customer's email")
    issue: str = Field(..., description="The customer's issue/question")
    order_id: Optional[str] = Field(None, description="Related order ID if applicable")
    priority: str = Field("normal", description="low, normal, high")
    previous_context: Optional[str] = Field(None, description="Previous conversation")


class SalesLead(BaseModel):
    """Incoming sales inquiry."""
    lead_name: str = Field(..., description="Lead's name")
    lead_email: str = Field(..., description="Lead's email")
    company: Optional[str] = Field(None, description="Company name")
    inquiry: str = Field(..., description="What they're interested in")
    budget: Optional[str] = Field(None, description="Budget range if mentioned")
    timeline: Optional[str] = Field(None, description="When they need it")


class EmailRequest(BaseModel):
    """Incoming email to respond to."""
    from_email: str = Field(..., description="Sender's email")
    from_name: Optional[str] = Field(None, description="Sender's name")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email body content")
    reply_type: str = Field("reply", description="reply, forward, new")


class AppointmentRequest(BaseModel):
    """Appointment booking request."""
    client_name: str = Field(..., description="Client's name")
    client_email: str = Field(..., description="Client's email")
    preferred_times: Optional[list] = Field(None, description="Preferred time slots")
    meeting_type: str = Field("call", description="call, video, in-person")
    notes: Optional[str] = Field(None, description="Additional notes")


class UniversalRequest(BaseModel):
    """Universal request that works with any agent type."""
    agent_type: str = Field(..., description="database_fixer, customer_support, sales_agent, etc.")
    data: dict = Field(..., description="The request data specific to the agent type")
    context: Optional[str] = Field(None, description="Additional context")


# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("🚀 AI Money Printer starting up...")
    print(f"📡 Listening on {os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '8000')}")
    
    # Initialize singletons
    get_vault()
    get_billing()
    get_fixer()
    get_safety()
    
    try:
        get_brain()
        print("🧠 AI Brain connected to OpenRouter")
    except ValueError as e:
        print(f"⚠️ Warning: {e}")
    
    yield
    
    # Shutdown
    print("👋 AI Money Printer shutting down...")


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="AI Money Printer",
    description="Autonomous Database Fix Service - Making money while you sleep",
    version="1.0.0",
    lifespan=lifespan
)


# =============================================================================
# CORE WORKFLOW - THE MONEY MACHINE
# =============================================================================

async def process_fix(
    error_report: ErrorReport,
    client_id: str,
    company_name: str,
    db_type: str,
    connection_string: str,
    fix_id: str
):
    """
    The complete fix workflow:
    1. Brain generates fix
    2. Safety validates in sandbox
    3. Database fixer applies fix
    4. Billing logs the success
    """
    brain = get_brain()
    safety = get_safety()
    fixer = get_fixer()
    billing = get_billing()
    vault = get_vault()
    
    start_time = time.time()
    
    try:
        # Step 1: Analyze the error
        print(f"🔍 [{fix_id}] Analyzing error...")
        analysis = await brain.analyze_error(error_report.error_message)
        
        if not analysis.get("is_fixable", False):
            print(f"❌ [{fix_id}] Error not automatically fixable: {analysis.get('reason')}")
            return
        
        if analysis.get("requires_human", False):
            print(f"⚠️ [{fix_id}] Requires human review, skipping automatic fix")
            return
        
        # Step 2: Get schema context if possible
        schema = await fixer.get_schema(db_type, connection_string)
        
        # Step 3: Generate the fix
        print(f"🧠 [{fix_id}] Generating fix...")
        fix_data = await brain.generate_fix(
            error_message=error_report.error_message,
            database_schema=schema,
            context=error_report.additional_context
        )
        
        # Step 4: Validate in sandbox (DRY RUN)
        print(f"🧪 [{fix_id}] Testing fix in sandbox...")
        dry_run_result = await safety.dry_run(
            code=fix_data["code"],
            fix_type=fix_data["fix_type"],
            schema_sql=schema if db_type == "sqlite" else None
        )
        
        # Step 5: Check for green light
        if not safety.get_green_light(dry_run_result):
            print(f"🔴 [{fix_id}] Safety check FAILED: {dry_run_result.message}")
            return
        
        print(f"🟢 [{fix_id}] Safety check PASSED - applying fix...")
        
        # Step 6: Apply the fix to live database
        fix_result = await fixer.apply_fix(
            code=fix_data["code"],
            fix_type=fix_data["fix_type"],
            db_type=db_type,
            connection_string=connection_string
        )
        
        if not fix_result.success:
            print(f"❌ [{fix_id}] Fix failed to apply: {fix_result.error}")
            return
        
        # Step 7: Log the success and BILL IT!
        execution_time = (time.time() - start_time) * 1000
        
        print(f"💰 [{fix_id}] Logging billing...")
        billing_record = await billing.log_success(
            client_id=client_id,
            company_name=company_name,
            fix_id=fix_id,
            fix_type=fix_data["fix_type"],
            error_summary=error_report.error_message[:100],
            execution_time_ms=execution_time,
            rows_affected=fix_result.rows_affected
        )
        
        # Update client stats
        vault.update_client_stats(client_id, billing_record.amount_usd)
        
        print(f"✅ [{fix_id}] Complete! Earned ${billing_record.amount_usd:.2f}")
    
    except Exception as e:
        print(f"💥 [{fix_id}] Error in fix workflow: {str(e)}")
        raise


# =============================================================================
# API ENDPOINTS
# =============================================================================

# Mount static files for landing page assets
import pathlib
static_dir = pathlib.Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """Serve the landing page."""
    landing_page = pathlib.Path(__file__).parent / "static" / "landing.html"
    if landing_page.exists():
        # Read content directly to avoid Content-Length mismatch issues
        content = landing_page.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    
    # Fallback to JSON stats if landing page doesn't exist
    billing = get_billing()
    stats = billing.get_stats()
    return HealthResponse(
        status="running",
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
        stats=stats
    )


@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/favicon.ico")
async def favicon():
    """Return empty response for favicon requests to prevent 404 logs."""
    return JSONResponse(content={}, status_code=204)


@app.post("/webhook/fix", response_model=FixResponse)
async def receive_error(
    error_report: ErrorReport,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(..., description="Client API key")
):
    """
    Main webhook endpoint - receives errors from client systems.
    
    This is where the money comes in! 💰
    """
    # Step 1: Verify the client
    vault = get_vault()
    client = vault.verify_client(x_api_key)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    if not client.is_active:
        raise HTTPException(status_code=403, detail="Client account is inactive")
    
    # Step 2: Generate fix ID
    fix_id = f"fix_{uuid.uuid4().hex[:12]}"
    
    # Step 3: Get client's database connection
    connection_string = vault.get_decrypted_connection(client)
    db_type = error_report.database_type or client.database_type
    
    # Step 4: Queue the fix for background processing
    background_tasks.add_task(
        process_fix,
        error_report=error_report,
        client_id=client.client_id,
        company_name=client.company_name,
        db_type=db_type,
        connection_string=connection_string,
        fix_id=fix_id
    )
    
    return FixResponse(
        fix_id=fix_id,
        status="queued",
        message="Fix queued for processing. You will be billed upon successful completion."
    )


@app.get("/stats")
async def get_stats(x_api_key: str = Header(...)):
    """Get billing statistics (admin only)."""
    # Simple admin check - in production, use proper auth
    if x_api_key != os.getenv("WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Admin access required")
    
    billing = get_billing()
    return billing.get_stats()


@app.get("/stats/recent")
async def get_recent(
    limit: int = 10,
    x_api_key: str = Header(...)
):
    """Get recent fixes (admin only)."""
    if x_api_key != os.getenv("WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Admin access required")
    
    billing = get_billing()
    recent = billing.get_recent_fixes(limit)
    
    return [
        {
            "timestamp": r.timestamp,
            "client": r.company_name,
            "fix_type": r.fix_type,
            "amount": r.amount_usd,
            "time_ms": r.execution_time_ms
        }
        for r in recent
    ]


# =============================================================================
# CLIENT MANAGEMENT ENDPOINTS
# =============================================================================

@app.post("/clients/register")
async def register_client(
    company_name: str,
    database_type: str,
    connection_string: str,
    plan: str = "per-fix",
    x_api_key: str = Header(...)
):
    """Register a new client (admin only)."""
    if x_api_key != os.getenv("WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Admin access required")
    
    vault = get_vault()
    client_id, api_key = vault.register_client(
        company_name=company_name,
        database_type=database_type,
        connection_string=connection_string,
        plan=plan
    )
    
    return {
        "client_id": client_id,
        "api_key": api_key,  # Only shown once!
        "message": "Client registered successfully. Save the API key - it won't be shown again!"
    }


@app.get("/clients")
async def list_clients(x_api_key: str = Header(...)):
    """List all active clients (admin only)."""
    if x_api_key != os.getenv("WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Admin access required")
    
    vault = get_vault()
    clients = vault.list_active_clients()
    
    return [
        {
            "client_id": c.client_id,
            "company_name": c.company_name,
            "database_type": c.database_type,
            "plan": c.plan,
            "total_fixes": c.total_fixes,
            "total_billed": c.total_billed,
            "last_activity": c.last_activity
        }
        for c in clients
    ]


# =============================================================================
# MULTI-AGENT ENDPOINTS - Support, Sales, Email, Appointments
# =============================================================================

@app.get("/agents")
async def list_agents():
    """List all available agent types and their pricing."""
    return {
        "agents": list_available_agents(),
        "message": "Use the /webhook/{agent_type} endpoint with the appropriate request body"
    }


async def process_multi_agent_request(
    agent_type: str,
    request_data: dict,
    client_id: str,
    company_name: str,
    request_id: str,
    context: str = None
):
    """
    Universal processor for all agent types (non-database).
    Handles Support, Sales, Email, Appointments, etc.
    """
    brain = get_brain()
    content_safety = get_content_safety()
    billing = get_billing()
    vault = get_vault()
    
    start_time = time.time()
    
    try:
        # Get agent configuration
        config = get_agent_config(agent_type)
        
        print(f"🤖 [{request_id}] Processing {config.name} request...")
        
        # Step 1: Process with AI brain
        response = await brain.process_request(
            agent_type=agent_type,
            input_data=request_data,
            context=context
        )
        
        # Step 2: Check content safety (for non-database agents)
        if agent_type != "database_fixer":
            # Get the main response field to check
            response_field = None
            for field in ["response_to_customer", "response_to_lead", "email_body", "response_to_client"]:
                if field in response:
                    response_field = response[field]
                    break
            
            if response_field:
                safety_result = content_safety.check_content(
                    content=response_field,
                    forbidden_words=config.forbidden_words,
                    required_tone=config.required_tone,
                    max_length=config.max_response_length
                )
                
                if not content_safety.get_content_green_light(safety_result):
                    print(f"🔴 [{request_id}] Content safety check FAILED: {safety_result.issues_found}")
                    return
        
        # Step 3: Check if outcome was successful
        is_success = brain.check_outcome_success(response, agent_type)
        
        if not is_success:
            print(f"⚪ [{request_id}] Outcome not successful - no billing")
            return response  # Return but don't bill
        
        # Step 4: Log billing for successful outcome
        execution_time = (time.time() - start_time) * 1000
        
        print(f"💰 [{request_id}] Success! Logging billing and generating invoice...")
        
        # 1. Log the success in your local CSV ledger
        billing_record = await billing.log_success(
            client_id=client_id,
            company_name=company_name,
            fix_id=request_id,
            fix_type=agent_type,
            error_summary=str(request_data)[:100],
            execution_time_ms=execution_time,
            rows_affected=0,
            custom_amount=config.price_per_outcome
        )
        
        # 2. Generate the Real Crypto Invoice via NOWPayments
        payment_link = await billing.create_now_invoice(
            amount=config.price_per_outcome,
            fix_id=request_id,
            description=f"{config.name}: {str(request_data)[:50]}"
        )
        
        # 3. Add the payment link to the response so the client can pay
        if payment_link:
            response["payment_url"] = payment_link
            print(f"💸 [{request_id}] Invoice Created: {payment_link}")
        
        # Update client stats
        vault.update_client_stats(client_id, billing_record.amount_usd)
        
        print(f"✅ [{request_id}] Complete! Earned ${billing_record.amount_usd:.2f}")
        
        return response
    
    except Exception as e:
        print(f"💥 [{request_id}] Error: {str(e)}")
        raise


@app.post("/webhook/support")
async def handle_support_ticket(
    ticket: SupportTicket,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(...)
):
    """
    Customer Support Agent endpoint.
    Resolves customer issues automatically. Bills $0.99 per resolved ticket.
    """
    vault = get_vault()
    client = vault.verify_client(x_api_key)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    request_id = f"support_{uuid.uuid4().hex[:12]}"
    
    background_tasks.add_task(
        process_multi_agent_request,
        agent_type="customer_support",
        request_data=ticket.model_dump(),
        client_id=client.client_id,
        company_name=client.company_name,
        request_id=request_id,
        context=ticket.previous_context
    )
    
    return {
        "request_id": request_id,
        "status": "processing",
        "agent": "Customer Support",
        "message": "Support ticket is being processed. You will be billed $0.99 upon successful resolution."
    }


@app.post("/webhook/sales")
async def handle_sales_lead(
    lead: SalesLead,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(...)
):
    """
    Sales Agent endpoint.
    Qualifies leads and books meetings. Bills $2.50 per booked meeting.
    """
    vault = get_vault()
    client = vault.verify_client(x_api_key)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    request_id = f"sales_{uuid.uuid4().hex[:12]}"
    
    background_tasks.add_task(
        process_multi_agent_request,
        agent_type="sales_agent",
        request_data=lead.model_dump(),
        client_id=client.client_id,
        company_name=client.company_name,
        request_id=request_id
    )
    
    return {
        "request_id": request_id,
        "status": "processing",
        "agent": "Sales Agent",
        "message": "Lead is being qualified. You will be billed $2.50 if a meeting is booked."
    }


@app.post("/webhook/email")
async def handle_email(
    email: EmailRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(...)
):
    """
    Email Auto-Responder endpoint.
    Drafts professional email responses. Bills $0.50 per drafted email.
    """
    vault = get_vault()
    client = vault.verify_client(x_api_key)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    request_id = f"email_{uuid.uuid4().hex[:12]}"
    
    background_tasks.add_task(
        process_multi_agent_request,
        agent_type="email_responder",
        request_data=email.model_dump(),
        client_id=client.client_id,
        company_name=client.company_name,
        request_id=request_id
    )
    
    return {
        "request_id": request_id,
        "status": "processing",
        "agent": "Email Responder",
        "message": "Email response is being drafted. You will be billed $0.50 upon completion."
    }


@app.post("/webhook/appointment")
async def handle_appointment(
    appointment: AppointmentRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(...)
):
    """
    Appointment Setter endpoint.
    Books and confirms appointments. Bills $1.50 per confirmed appointment.
    """
    vault = get_vault()
    client = vault.verify_client(x_api_key)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    request_id = f"appt_{uuid.uuid4().hex[:12]}"
    
    background_tasks.add_task(
        process_multi_agent_request,
        agent_type="appointment_setter",
        request_data=appointment.model_dump(),
        client_id=client.client_id,
        company_name=client.company_name,
        request_id=request_id
    )
    
    return {
        "request_id": request_id,
        "status": "processing",
        "agent": "Appointment Setter",
        "message": "Appointment request is being processed. You will be billed $1.50 if confirmed."
    }


@app.post("/webhook/universal")
async def handle_universal_request(
    request: UniversalRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(...)
):
    """
    Universal endpoint that works with ANY agent type.
    Pass agent_type and data in the request body.
    """
    vault = get_vault()
    client = vault.verify_client(x_api_key)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Validate agent type
    try:
        config = get_agent_config(request.agent_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent type: {request.agent_type}. Use /agents to see available types."
        )
    
    request_id = f"uni_{uuid.uuid4().hex[:12]}"
    
    background_tasks.add_task(
        process_multi_agent_request,
        agent_type=request.agent_type,
        request_data=request.data,
        client_id=client.client_id,
        company_name=client.company_name,
        request_id=request_id,
        context=request.context
    )
    
    return {
        "request_id": request_id,
        "status": "processing",
        "agent": config.name,
        "price": config.price_per_outcome,
        "message": f"Request is being processed by {config.name}. You will be billed ${config.price_per_outcome:.2f} upon successful outcome."
    }


# =============================================================================
# NOWPAYMENTS IPN LISTENER - Real-time Payment Confirmations
# =============================================================================

@app.post("/webhook/nowpayments")
async def nowpayments_ipn(request: Request):
    """
    Real-time listener for crypto payments.
    NOWPayments pings this endpoint when a payment status changes.
    Configure this URL in your NOWPayments dashboard under IPN settings.
    """
    payload = await request.json()
    
    payment_status = payload.get("payment_status")
    order_id = payload.get("order_id")
    pay_amount = payload.get("pay_amount", 0)
    pay_currency = payload.get("pay_currency", "unknown")
    actually_paid = payload.get("actually_paid", 0)
    
    print(f"📥 NOWPayments IPN: Order {order_id} - Status: {payment_status}")
    
    if payment_status == "finished":
        print(f"💰💰💰 REAL MONEY RECEIVED! Order {order_id} is fully paid.")
        
        # Send Telegram notification for confirmed payment
        billing = get_billing()
        if billing.telegram_token and billing.telegram_chat_id:
            message = f"""🎉 **PAYMENT CONFIRMED!**

💳 **Order:** {order_id}
💰 **Amount:** {actually_paid} {pay_currency.upper()}
✅ **Status:** PAID

The money is now in your wallet! 🚀
"""
            try:
                import httpx
                url = f"https://api.telegram.org/bot{billing.telegram_token}/sendMessage"
                async with httpx.AsyncClient() as client:
                    await client.post(url, json={
                        "chat_id": billing.telegram_chat_id,
                        "text": message,
                        "parse_mode": "Markdown"
                    })
            except Exception as e:
                print(f"⚠️ Telegram notification failed: {e}")
    
    elif payment_status == "waiting":
        print(f"⏳ Waiting for payment: Order {order_id}")
    
    elif payment_status == "confirming":
        print(f"🔄 Payment confirming: Order {order_id}")
    
    elif payment_status in ["failed", "expired"]:
        print(f"❌ Payment {payment_status}: Order {order_id}")
    
    return {"status": "received"}


# =============================================================================
# RUN THE SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║     💰 AI MONEY PRINTER - STARTING UP 💰                 ║
    ║                                                           ║
    ║     Making money while you sleep...                       ║
    ║                                                           ║
    ║     🔧 Database Fixer    - $5.00/fix                      ║
    ║     💬 Customer Support  - $0.99/resolution               ║
    ║     📈 Sales Agent       - $2.50/meeting                  ║
    ║     📧 Email Responder   - $0.50/email                    ║
    ║     📅 Appointment Setter - $1.50/booking                 ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host=host, port=port)
