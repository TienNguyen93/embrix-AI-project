import requests

base_url = "http://localhost:8000"

print("1. Creating session...")
res = requests.post(f"{base_url}/sessions", json={"title": "Test Chat"})
session_id = res.json()["session_id"]
print(f"Session ID: {session_id}")

print("\n2. Sending Q1...")
q1 = {
    "session_id": session_id,
    "question": "Show me the top 3 records in file_header_record by processed_date",
    "schema_name": "core_usage"
}
res1 = requests.post(f"{base_url}/query", json=q1)
print(res1.json())

print("\n3. Sending Q2 (follow-up)...")
q2 = {
    "session_id": session_id,
    "question": "Change that to top 5 instead",
    "schema_name": "core_usage"
}
res2 = requests.post(f"{base_url}/query", json=q2)
print("NL:", res2.json().get("nl_response"))
print("Chart:", res2.json().get("chart_spec"))
print("SQL:", res2.json().get("sql"))
