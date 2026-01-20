"""
brain.py - AI Intelligence Layer
Connects to OpenRouter/DeepSeek to power multiple agent types
"""

import os
import json
import httpx
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Import agent configurations
from .agents import AgentConfig, AgentType, get_agent_config, DATABASE_FIXER_CONFIG


class AIBrain:
    """The AI brain that generates database fixes using DeepSeek via OpenRouter."""
    
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")
    
    async def generate_fix(
        self,
        error_message: str,
        database_schema: Optional[str] = None,
        sample_data: Optional[str] = None,
        context: Optional[str] = None
    ) -> dict:
        """
        Generate a database fix based on the error.
        
        Returns:
            {
                "fix_type": "sql" | "python",
                "code": "...",
                "explanation": "...",
                "risk_level": "low" | "medium" | "high",
                "estimated_rows_affected": int
            }
        """
        
        system_prompt = """You are an expert database repair AI. Your job is to:
1. Analyze database errors sent by automated systems
2. Generate SAFE, minimal fixes that solve the specific problem
3. Always prefer SELECT before UPDATE/DELETE to verify scope
4. Never drop tables or delete data unless explicitly required
5. Return fixes in a structured JSON format

CRITICAL SAFETY RULES:
- Always add WHERE clauses to UPDATE/DELETE statements
- Limit affected rows when possible
- Prefer reversible operations
- Include rollback instructions for risky operations"""

        user_prompt = f"""
DATABASE ERROR REPORT:
{error_message}

{"SCHEMA CONTEXT:" + chr(10) + database_schema if database_schema else ""}
{"SAMPLE DATA:" + chr(10) + sample_data if sample_data else ""}
{"ADDITIONAL CONTEXT:" + chr(10) + context if context else ""}

Generate a fix. Respond ONLY with valid JSON in this exact format:
{{
    "fix_type": "sql" or "python",
    "code": "the actual fix code",
    "explanation": "what this fix does and why",
    "risk_level": "low", "medium", or "high",
    "estimated_rows_affected": number or -1 if unknown,
    "verification_query": "SQL to verify the fix worked",
    "rollback_code": "code to undo the fix if needed"
}}
"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ai-money-printer.local",
            "X-Title": "AI Money Printer"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,  # Low temperature for consistent, safe outputs
            "max_tokens": 2000
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Parse the JSON response
            # Handle potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            fix_data = json.loads(content.strip())
            
            # Validate required fields
            required_fields = ["fix_type", "code", "explanation", "risk_level"]
            for field in required_fields:
                if field not in fix_data:
                    raise ValueError(f"AI response missing required field: {field}")
            
            return fix_data
    
    async def analyze_error(self, error_message: str) -> dict:
        """
        Quick analysis of an error to determine if it's fixable.
        
        Returns:
            {
                "is_fixable": bool,
                "category": "data_integrity" | "schema" | "performance" | "connection" | "unknown",
                "confidence": float (0-1),
                "requires_human": bool
            }
        """
        
        prompt = f"""Analyze this database error and categorize it:

ERROR: {error_message}

Respond with JSON only:
{{
    "is_fixable": true/false (can an automated system safely fix this?),
    "category": "data_integrity", "schema", "performance", "connection", or "unknown",
    "confidence": 0.0 to 1.0,
    "requires_human": true/false (does this need human review?),
    "reason": "brief explanation"
}}
"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            if "```" in content:
                content = content.split("```")[1].split("```")[0]
                if content.startswith("json"):
                    content = content[4:]
            
            return json.loads(content.strip())
    
    async def process_request(
        self,
        agent_type: str | AgentType,
        input_data: Dict[str, Any],
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Universal processor that works with ANY agent type.
        
        Args:
            agent_type: The type of agent to use (support, sales, etc.)
            input_data: The incoming request data
            context: Additional context if available
        
        Returns:
            JSON response based on the agent's response_format
        """
        config = get_agent_config(agent_type)
        
        # Build the user prompt from input data
        input_text = json.dumps(input_data, indent=2) if isinstance(input_data, dict) else str(input_data)
        
        user_prompt = f"""
INPUT DATA:
{input_text}

{"ADDITIONAL CONTEXT:" + chr(10) + context if context else ""}

Respond with JSON matching this exact format:
{json.dumps(config.response_format, indent=2)}
"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ai-money-printer.local",
            "X-Title": f"AI Money Printer - {config.name}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": config.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": config.max_response_length
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            response_data = json.loads(content.strip())
            
            # Add metadata
            response_data["_agent_type"] = config.agent_type.value
            response_data["_price"] = config.price_per_outcome
            
            return response_data
    
    def check_outcome_success(
        self,
        response: Dict[str, Any],
        agent_type: str | AgentType
    ) -> bool:
        """
        Check if the agent's response indicates a successful outcome.
        This determines whether to bill the client.
        """
        config = get_agent_config(agent_type)
        
        outcome_value = response.get(config.outcome_field)
        
        # Handle boolean strings
        if isinstance(outcome_value, str):
            outcome_value = outcome_value.lower() == "true"
        
        return outcome_value == config.success_value


# Singleton instance
_brain_instance: Optional[AIBrain] = None


def get_brain() -> AIBrain:
    """Get or create the singleton brain instance."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = AIBrain()
    return _brain_instance

