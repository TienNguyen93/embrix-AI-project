"""
embrix.api.schemas
──────────────────
Pydantic Request and Response DTO schemas for API integration.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class SessionRequest(BaseModel):
    title: str = "New Chat"


class QueryRequest(BaseModel):
    session_id: str
    question: str
    schema_name: str = "core_usage"
    model_preference: str = "auto"
    preferred_model: Optional[str] = None



class QueryResponse(BaseModel):
    sql: str
    result: str
    message_id: str
    nl_response: str
    chart_spec: Optional[Dict[str, Any]] = None
    empty_tables: List[str] = []
    follow_ups: List[str] = []
    execution_metrics: Optional[Dict[str, Any]] = None


class RerunRequest(BaseModel):
    session_id: str
    question: str
    schema_name: str = "core_usage"
    new_sql: str


class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    metadata_store_type: str
    active_llm_provider: str
