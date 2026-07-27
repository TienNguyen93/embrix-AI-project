# SQL Agentic Web App

The **SQL Agentic Web App** is an AI-powered conversational Business Intelligence (BI) web application. It combines a **FastAPI backend** running a multi-agent LangGraph pipeline with a **React/Vite frontend** featuring a glassmorphic user interface, dynamic charts, SQL query editing, and real-time execution logs.

---

## Folder Structure

```
SQL-agentic-web-app/
├── backend/            # FastAPI orchestration server, LangGraph SQL agent, database handlers
├── frontend/           # React + Vite frontend application (Recharts, glassmorphic UI)
├── .env                # Environment variables configuration for backend
├── .env.template       # Environment variable template
└── README.md           # Instructions for building and running the web app
```

---

## Prerequisites

- **Python**: Version 3.10+
- **Node.js**: Version 18+ (with `npm`)
- **Ollama**: Running locally with `llama3.1` and `qwen3.5` models pulled:
  ```bash
  ollama pull llama3.1
  ollama pull qwen3.5
  ```
- **PostgreSQL**: A running PostgreSQL instance containing target database tables.

---

## Environment Setup

Create a `.env` file in `SQL-agentic-web-app/.env` (or copy from `.env.template`):

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=embrix_db
DB_USER=postgres
DB_PASSWORD=your_password
SCHEMA_NAME=core_revenue
OLLAMA_BASE_URL=http://localhost:11434
LLAMA_MODEL=llama3.1
```

---

## 1. Backend Setup (FastAPI + LangGraph)

1. **Navigate to `SQL-agentic-web-app/backend`**:
   ```bash
   cd SQL-agentic-web-app/backend
   ```

2. **Activate your Python Virtual Environment**:
   ```bash
   # On Windows (Git Bash):
   source ../../venv/Scripts/activate
   
   # On Windows (PowerShell):
   ..\..\venv\Scripts\Activate.ps1
   
   # On Linux/macOS:
   source ../../venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install fastapi uvicorn pydantic sqlalchemy psycopg2-binary pandas networkx langgraph langchain-google-genai python-dotenv
   ```

4. **Initialize Metadata Schema (Optional)**:
   ```bash
   python init_db.py
   ```

5. **Start the Uvicorn Dev Server**:
   ```bash
   python -m uvicorn api:app --host 0.0.0.0 --port 8001 --reload
   ```
   *The backend server will run on `http://localhost:8001`.*

---

## 2. Frontend Setup (React + Vite)

1. **Navigate to `SQL-agentic-web-app/frontend`**:
   ```bash
   cd SQL-agentic-web-app/frontend
   ```

2. **Install Node Dependencies**:
   ```bash
   npm install
   ```

3. **Start the Development Server**:
   ```bash
   npm run dev
   ```
   *The web application will open on `http://localhost:5173`.*

---

## Key Features

- **Natural Language to SQL**: Converts natural language prompts into executable PostgreSQL queries.
- **SQL Security Auditor**: Validates generated SQL queries to block destructive DML/DDL operations (e.g., `DROP`, `DELETE`, `UPDATE`, `INSERT`).
- **Interactive Query Editor**: Allows users to inspect generated SQL, edit queries directly in the UI, and rerun them.
- **Rolling Context Memory**: Maintains chat history across questions for follow-up analysis.
- **Business Follow-up Suggestions**: Generates interactive follow-up question pills automatically.
- **Dynamic Data Visualization**: Uses Recharts to render Bar, Line, or Pie charts based on query results.
- **Empty Table Detection**: Detects empty tables during initialization to prevent query hallucinations.
