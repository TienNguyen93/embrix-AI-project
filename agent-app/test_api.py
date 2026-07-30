"""
Test script for Phase 6 FastAPI REST API endpoints & SQL-agentic-web-app integration.
"""

import logging
from fastapi.testclient import TestClient
from app import app

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("test_api")


def test_api_endpoints():
    client = TestClient(app)

    logger.info("--- 1. Testing GET /health ---")
    resp = client.get("/health")
    assert resp.status_code == 200, "GET /health must return 200"
    logger.info(f"Health Response: {resp.json()}")

    logger.info("\n--- 2. Testing POST /sessions & GET /sessions ---")
    sess_resp = client.post("/sessions", json={"title": "Test Chat Session"})
    assert sess_resp.status_code == 200, "POST /sessions must return 200"
    session_id = sess_resp.json()["session_id"]
    logger.info(f"Created Session ID: {session_id}")

    sessions_list = client.get("/sessions")
    assert sessions_list.status_code == 200
    logger.info(f"Active Sessions Count: {len(sessions_list.json())}")

    logger.info("\n--- 3. Testing GET /suggested_questions ---")
    sug_resp = client.get("/suggested_questions")
    assert sug_resp.status_code == 200
    logger.info(f"Suggested Questions: {sug_resp.json()['questions']}")

    logger.info("\n--- 4. Testing POST /query ---")
    query_payload = {
        "session_id": session_id,
        "question": "billing revenue and usage by country",
        "schema_name": "core_usage",
        "model_preference": "auto"
    }
    q_resp = client.post("/query", json=query_payload)
    assert q_resp.status_code == 200, f"POST /query failed: {q_resp.text}"
    q_data = q_resp.json()
    
    logger.info(f"Generated SQL: {q_data['sql']}")
    logger.info(f"NL Response: {q_data['nl_response']}")
    logger.info(f"Metrics: {q_data['execution_metrics']}")

    logger.info("\n=== PHASE 6 REST API INTEGRATION VERIFICATION PASSED ===")


if __name__ == "__main__":
    test_api_endpoints()
