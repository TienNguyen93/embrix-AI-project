# AGENTS.md — Embrix AI Agent Directives

## Post-Clone Setup & Database Readiness Task

After cloning the repository (in VS Code, Codex, Antigravity, or Cursor):

1. **Virtual Environment Creation & Activation**:
   Always create and activate a Python virtual environment before installing packages:
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # Git Bash
   pip install sqlalchemy psycopg2-binary pydantic python-dotenv pandas tabulate

   ```

2. **One-Time Initialization Task**:
   Run the setup check command in terminal:
   ```bash
   python -m embrix.cli --init
   ```
   When completed, the system will output:
   `"Database is ready for questions!"`

3. **Zero-Scratch-File Protocol**:
   - DO NOT call `write_to_file` or create temporary Python scripts (e.g. `inspect_schema.py`, `execute_query.py`, `get_summary.py`).
   - Read schema metadata in-memory using `schema_snapshot.json` or run `python -m embrix.cli "<question>"`.

4. **Required Output Format for Data Questions**:
   When responding to any database question, output the response in this exact structured format:
   
   - **Generated SQL Query**: Valid, read-only SELECT query formatted inside a ````sql ... ```` block.
   - **Query Execution Results**: Clean Markdown table of the returned rows (or EXPLAIN plan status).
   - **Token Usage & Cost Estimation**:
     - *Input Tokens*: Prompt / schema tokens
     - *Output Tokens*: Generated SQL / reasoning tokens
     - *Total Tokens*: Input + Output
     - *Estimated Cost*: USD calculation ($0.075/1M input, $0.30/1M output — **Cloud/AI Chat Mode Only**; Local CLI mode prints **Free/Local**)

5. **Read-Only Enforcement & Security**:
   - Only execute SELECT/WITH statements. Never execute DML/DDL (INSERT, UPDATE, DELETE, DROP).
