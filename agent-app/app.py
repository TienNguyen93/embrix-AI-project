"""
app.py
──────
FastAPI REST API Server for Embrix Conversational BI & UI Integration.
Serves SQL-agentic-web-app/frontend React application.
"""

import os
import sys
import uuid
import time
import logging
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# Add package directory to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from embrix.api.schemas import (
    SessionRequest, QueryRequest, QueryResponse, RerunRequest, HealthResponse
)
from embrix.api.pipeline import execute_nl2sql_pipeline
from embrix.cli import _get_engine

logger = logging.getLogger("embrix.app")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

app = FastAPI(
    title="Embrix AI Agent Production REST API",
    description="Upgraded REST API powering Embrix Web UI with pgvector Hybrid RAG & Multi-Model Gemini Pool",
    version="2.0.0"
)

# Enable CORS for React Frontend (Vite localhost:5173 / localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory Session Store
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_MESSAGES: Dict[str, List[Dict[str, Any]]] = {}


@app.get("/health", response_model=HealthResponse)
def health_check():
    """GET /health - System & DB readiness status check."""
    engine = _get_engine()
    db_online = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_online = True
    except Exception:
        db_online = False

    return HealthResponse(
        status="OK" if db_online else "DEGRADED",
        database_connected=db_online,
        metadata_store_type="pgvector / SQLite fallback",
        active_llm_provider="ResilientLLMProvider (Gemini Pool -> Ollama)"
    )


@app.post("/sessions")
def create_session(req: SessionRequest):
    """POST /sessions - Create new chat session."""
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {
        "id": session_id,
        "title": req.title,
        "created_at": time.time()
    }
    _MESSAGES[session_id] = []
    return {"session_id": session_id}


@app.get("/sessions")
def list_sessions():
    """GET /sessions - List active chat sessions."""
    return list(_SESSIONS.values())


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """DELETE /sessions/{session_id} - Delete session and message history."""
    _SESSIONS.pop(session_id, None)
    _MESSAGES.pop(session_id, None)
    return {"status": "success"}


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    """GET /sessions/{session_id}/messages - Get session chat history."""
    return _MESSAGES.get(session_id, [])


@app.get("/schema/empty_tables")
def get_empty_tables(schema_name: str = "core_usage"):
    """GET /schema/empty_tables - Return empty tables in schema."""
    return {"empty_tables": []}


@app.post("/query", response_model=QueryResponse)
def run_query_endpoint(request: QueryRequest):
    """
    POST /query - Main NL-to-SQL execution endpoint for Embrix Web UI.
    Fuses Hybrid RAG + Multi-Model Gemini Pool + EXPLAIN Audit + Data Fetching.
    """
    session_id = request.session_id
    question = request.question

    if session_id not in _MESSAGES:
        _MESSAGES[session_id] = []

    # Store user message
    user_msg_id = str(uuid.uuid4())
    _MESSAGES[session_id].append({
        "id": user_msg_id,
        "role": "user",
        "content": question,
        "timestamp": time.time()
    })

    try:
        pipeline_res = execute_nl2sql_pipeline(
            question=question,
            schema_name=request.schema_name,
            model_preference=request.model_preference,
            preferred_model=request.preferred_model
        )


        asst_msg_id = str(uuid.uuid4())
        _MESSAGES[session_id].append({
            "id": asst_msg_id,
            "role": "assistant",
            "content": pipeline_res["nl_response"],
            "sql": pipeline_res["sql"],
            "timestamp": time.time()
        })

        return QueryResponse(
            sql=pipeline_res["sql"],
            result=pipeline_res["result_json"],
            message_id=asst_msg_id,
            nl_response=pipeline_res["nl_response"],
            chart_spec=None,  # Dashboard creation opted out per user instruction
            empty_tables=[],
            follow_ups=[
                "Show service usage breakdown by month",
                "Show top 10 accounts by total billing revenue"
            ],
            execution_metrics=pipeline_res["metrics"]
        )
    except Exception as e:
        logger.error(f"Error executing /query endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/rerun", response_model=QueryResponse)
def rerun_query_endpoint(request: RerunRequest):
    """POST /query/rerun - Rerun modified user SQL query."""
    engine = _get_engine()
    start_time = time.time()
    
    try:
        df = pd.read_sql(text(request.new_sql), engine)
        result_json = df.to_json(orient="records") if not df.empty else "[]"
        exec_duration = time.time() - start_time
        
        asst_msg_id = str(uuid.uuid4())
        nl_response = f"Rerun executed successfully returning {len(df)} rows.\n\n--thought for {int(exec_duration)} seconds--"
        
        return QueryResponse(
            sql=request.new_sql,
            result=result_json,
            message_id=asst_msg_id,
            nl_response=nl_response,
            chart_spec=None,
            empty_tables=[],
            follow_ups=[],
            execution_metrics={"execution_time_sec": exec_duration, "db_status": "ONLINE"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rerun execution failed: {e}")


@app.get("/suggested_questions")
def get_suggested_questions(schema_name: str = "core_usage"):
    """GET /suggested_questions - Return sample suggested prompts."""
    return {
        "status": "success",
        "questions": [
            "Show total service usage readings by date and service type",
            "What is the total invoice billing revenue by country?",
            "List top 10 accounts by active service usage",
            "Show unpaid customer accounts and total overdue balance"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
