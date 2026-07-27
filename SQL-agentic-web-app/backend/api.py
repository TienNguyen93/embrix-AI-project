from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
import time

from db_connection import get_engine, check_empty_tables
from infer_schema import build_schema_context
from sql_agent import load_knowledge_graph, load_agentic_skills, create_sql_agent, generate_suggested_questions
import memory

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Embrix Multi-Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SessionRequest(BaseModel):
    title: str = "New Chat"

@app.post("/sessions")
def create_session_endpoint(req: SessionRequest):
    session_id = memory.create_session(title=req.title)
    return {"session_id": session_id}

@app.get("/sessions")
def get_sessions_endpoint():
    return memory.get_sessions()

@app.delete("/sessions/{session_id}")
def delete_session_endpoint(session_id: str):
    memory.delete_session(session_id)
    return {"status": "success"}

@app.get("/sessions/{session_id}/messages")
def get_messages_endpoint(session_id: str):
    return memory.get_messages(session_id)

@app.get("/schema/empty_tables")
def get_empty_tables(schema_name: str):
    engine = get_engine(schema_name=schema_name)
    row_counts = check_empty_tables(engine, schema_name=schema_name)
    empty_tables = [t for t, count in row_counts.items() if count == 0]
    return {"empty_tables": empty_tables}

class QueryRequest(BaseModel):
    session_id: str
    question: str
    schema_name: str

class QueryResponse(BaseModel):
    sql: str
    result: str
    message_id: str
    nl_response: str
    chart_spec: dict | None
    empty_tables: list[str] = []
    follow_ups: list[str] = []

@app.post("/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    start_time = time.time()
    session_id = request.session_id
    question = request.question
    schema_name = request.schema_name
    
    try:
        # Save user message
        user_msg_id = memory.add_message(session_id, "user", question)
        
        # Build chat history context
        messages = memory.get_messages(session_id)
        chat_history_lines = ["\nConversational History:"]
        for msg in messages[-6:]:  # Last 6 messages
            chat_history_lines.append(f"{msg['role'].capitalize()}: {msg['content']}")
            
        recent_contexts = memory.get_recent_turn_contexts(session_id, limit=3)
        if recent_contexts:
            chat_history_lines.append("\nPrevious Turn Contexts (Rolling Summary):")
            for ctx in recent_contexts:
                chat_history_lines.append(f"Question: {ctx['message_content']}")
                chat_history_lines.append(f"SQL Used: {ctx['sql_used']}")
                chat_history_lines.append(f"Summary: {ctx['result_summary']}")
        
        chat_history_context = "\n".join(chat_history_lines)
        
        engine = get_engine(schema_name=schema_name)
        row_counts = check_empty_tables(engine, schema_name=schema_name)
        schema_context = build_schema_context(engine, schema_name=schema_name, row_counts=row_counts)
        
        graph_obj = load_knowledge_graph()
        graph_context = ""
        if graph_obj:
            edges = []
            for u, v, data in graph_obj.edges(data=True):
                edges.append(f"{u}.{data.get('source_column')} -> {v}.{data.get('target_column')}")
            graph_context = "\nInferred Join Relationships (Knowledge Graph):\n" + "\n".join(edges)
            
        skills_context, _ = load_agentic_skills()
        
        # Build the graph agent
        agent = create_sql_agent(engine)
        
        initial_state = {
            "question": question,
            "schema_context": schema_context,
            "graph_context": graph_context,
            "skills_context": skills_context,
            "schema_name": schema_name,
            "chat_history_context": chat_history_context,
            "current_sql": None,
            "audit_feedback": None,
            "error_msg": None,
            "retry_count": 0,
            "success": False,
            "result_df": None,
            "result_error": None
        }
        
        final_state = agent.invoke(initial_state)
        
        if not final_state.get("success"):
            err = final_state.get("result_error") or final_state.get("error_msg") or "Unknown error"
            raise HTTPException(status_code=500, detail=f"Agent failed to execute query safely. Reason: {err}")
            
        result_df = final_state.get("result_df")
        sql = final_state.get("current_sql") or ""
        
        if result_df is None or result_df.empty:
            result_str = "[]"
        else:
            result_str = result_df.to_json(orient="records")
            
        # Save assistant response to memory
        duration = int(time.time() - start_time)
        nl_response = final_state.get("nl_response") or "Query executed successfully."
        nl_response += f"\n\n--thought for {duration} seconds--"
        follow_ups = final_state.get("follow_ups") or []
        
        chart_spec_str = final_state.get("chart_spec")
        chart_spec_dict = None
        if chart_spec_str:
            try:
                chart_spec_dict = json.loads(chart_spec_str)
            except:
                pass
                
        asst_msg_id = memory.add_message(session_id, "assistant", nl_response)
        memory.save_turn_context(session_id, user_msg_id, sql_used=sql, result_summary=nl_response, chart_spec=chart_spec_str)
            
        empty_tables = [t for t, count in row_counts.items() if count == 0]
            
        return QueryResponse(
            sql=sql, 
            result=result_str, 
            message_id=asst_msg_id,
            nl_response=nl_response,
            chart_spec=chart_spec_dict,
            empty_tables=empty_tables,
            follow_ups=follow_ups
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RerunRequest(BaseModel):
    session_id: str
    question: str
    schema_name: str
    new_sql: str

@app.post("/query/rerun", response_model=QueryResponse)
def rerun_endpoint(request: RerunRequest):
    start_time = time.time()
    session_id = request.session_id
    question = request.question
    schema_name = request.schema_name
    new_sql = request.new_sql
    
    try:
        user_msg_id = memory.add_message(session_id, "user", f"[RERUN] {question}")
        
        engine = get_engine(schema_name=schema_name)
        row_counts = check_empty_tables(engine, schema_name=schema_name)
        schema_context = build_schema_context(engine, schema_name=schema_name, row_counts=row_counts)
        
        graph_obj = load_knowledge_graph()
        graph_context = ""
        if graph_obj:
            edges = []
            for u, v, data in graph_obj.edges(data=True):
                edges.append(f"{u}.{data.get('source_column')} -> {v}.{data.get('target_column')}")
            graph_context = "\\nInferred Join Relationships (Knowledge Graph):\\n" + "\\n".join(edges)
            
        skills_context, _ = load_agentic_skills()
        
        agent = create_sql_agent(engine, entry_point="audit")
        
        initial_state = {
            "question": question,
            "schema_context": schema_context,
            "graph_context": graph_context,
            "skills_context": skills_context,
            "schema_name": schema_name,
            "chat_history_context": "",
            "current_sql": new_sql,
            "audit_feedback": None,
            "error_msg": None,
            "retry_count": 0,
            "success": False,
            "result_df": None,
            "result_error": None
        }
        
        final_state = agent.invoke(initial_state)
        
        if not final_state.get("success"):
            err = final_state.get("result_error") or final_state.get("error_msg") or "Unknown error"
            raise HTTPException(status_code=500, detail=f"Agent failed to execute query safely. Reason: {err}")
            
        result_df = final_state.get("result_df")
        sql = final_state.get("current_sql") or ""
        
        if result_df is None or result_df.empty:
            result_str = "[]"
        else:
            result_str = result_df.to_json(orient="records")
            
        duration = int(time.time() - start_time)
        nl_response = final_state.get("nl_response") or "Query executed successfully."
        nl_response += f"\n\n--thought for {duration} seconds--"
        follow_ups = final_state.get("follow_ups") or []
        
        chart_spec_str = final_state.get("chart_spec")
        chart_spec_dict = None
        if chart_spec_str:
            try:
                chart_spec_dict = json.loads(chart_spec_str)
            except:
                pass
                
        asst_msg_id = memory.add_message(session_id, "assistant", nl_response)
        memory.save_turn_context(session_id, user_msg_id, sql_used=sql, result_summary=nl_response, chart_spec=chart_spec_str)
            
        empty_tables = [t for t, count in row_counts.items() if count == 0]
            
        return QueryResponse(
            sql=sql, 
            result=result_str, 
            message_id=asst_msg_id,
            nl_response=nl_response,
            chart_spec=chart_spec_dict,
            empty_tables=empty_tables,
            follow_ups=follow_ups
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/suggested_questions")
def get_suggested_questions(schema_name: str = None):
    try:
        engine = get_engine(schema_name)
        row_counts = check_empty_tables(engine, schema_name=schema_name)
        schema_context = build_schema_context(engine, schema_name=schema_name, row_counts=row_counts)
        
        questions = generate_suggested_questions(schema_context)
        return {"status": "success", "questions": questions}
    except Exception as e:
        return {"status": "error", "message": str(e), "questions": []}
