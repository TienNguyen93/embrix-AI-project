import os
import networkx as nx
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import text
from db_connection import get_engine, get_schema_tables, get_table_columns
from infer_schema import build_schema_context
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.1")
SCHEMA_NAME = os.getenv("SCHEMA_NAME", "core_revenue")

# Initialize Local LLM
llm = ChatOllama(
    model=LLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0.0
)

def load_knowledge_graph(file_path="schema_graph.graphml"):
    """Loads the pre-computed schema knowledge graph."""
    if os.path.exists(file_path):
        return nx.read_graphml(file_path)
    return None

def load_agentic_skills(skills_dir=".agents/skills"):
    """Loads all SKILL.md files from the agentic skills directory to enhance the prompt."""
    skills_text = ""
    loaded_skills = []
    if os.path.exists(skills_dir):
        for root, dirs, files in os.walk(skills_dir):
            for file in files:
                if file == "SKILL.md":
                    try:
                        skill_name = os.path.basename(root)
                        with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                            skills_text += f"\n--- Advanced Skill Playbook: {skill_name} ---\n"
                            skills_text += f.read() + "\n"
                        loaded_skills.append(skill_name)
                    except Exception as e:
                        pass
    return skills_text, loaded_skills

def generate_sql(question, schema_context, graph, skills_context="", schema_name=SCHEMA_NAME):
    """
    Uses the local LLM to translate a natural language question into PostgreSQL.
    Provides the schema and inferred graph relationships for context.
    """
    graph_context = ""
    if graph:
        edges = []
        for u, v, data in graph.edges(data=True):
            edges.append(f"{u}.{data.get('source_column')} -> {v}.{data.get('target_column')}")
        graph_context = "\nInferred Join Relationships (Knowledge Graph):\n" + "\n".join(edges)
        
    prompt = PromptTemplate.from_template(
        """You are an expert PostgreSQL developer. Write a syntactically correct PostgreSQL query to answer the following question.
If any Advanced Skill Playbooks are provided below, you MUST follow their reasoning and instructions to write the best SQL.

=== ADVANCED SKILL PLAYBOOKS ===
{skills_context}
================================

{schema_context}
{graph_context}

Question: {question}

Important Rules:
1. Only use the tables and columns provided in the schema.
2. Use the "Inferred Join Relationships" to guide how to join tables together.
3. Never include DML operations (INSERT, UPDATE, DELETE). Only SELECT.
4. You MUST explicitly define the schema then the table for every table you query (e.g., SELECT * FROM {schema_name}.table_name;).
5. Output ONLY the raw SQL query. Do not include markdown formatting like ```sql or ``` at the beginning or end.

SQL Query:"""
    )
    
    chain = prompt | llm
    response = chain.invoke({
        "schema_context": schema_context, 
        "graph_context": graph_context,
        "skills_context": skills_context,
        "question": question,
        "schema_name": schema_name
    })
    
    sql = response.content.strip()
    # Clean markdown if model ignored the instruction
    if sql.startswith("```sql"):
        sql = sql[6:]
    if sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]
        
    return sql.strip()

def execute_sql(engine, sql):
    """Executes the SQL safely and returns a pandas DataFrame, or an error message."""
    try:
        # Use pandas to execute the query and format nicely
        df = pd.read_sql_query(text(sql), engine.connect())
        return True, df
    except Exception as e:
        return False, str(e)

def self_correct_sql(question, failed_sql, error_msg, schema_context, graph, schema_name=SCHEMA_NAME):
    """
    If the SQL execution fails, we feed the error back to the LLM to fix it.
    """
    print(f"\n[!] SQL Execution Failed. Attempting to self-correct...")
    prompt = PromptTemplate.from_template(
        """You are an expert PostgreSQL developer. You wrote a query that failed to execute.

Question: {question}

Failed SQL Query:
{failed_sql}

Database Error Message:
{error_msg}

{schema_context}

Rewrite the SQL query to fix the error. 
Important Rules:
1. You MUST explicitly define the schema then the table for every table you query (e.g., SELECT * FROM {schema_name}.table_name;).
2. DO NOT output the exact same Failed SQL Query again. Find a different approach or fix the syntax error.
3. Output ONLY the raw SQL query. Do not include markdown formatting like ```sql.

Corrected SQL Query:"""
    )
    chain = prompt | llm
    response = chain.invoke({
        "question": question,
        "failed_sql": failed_sql,
        "error_msg": error_msg,
        "schema_context": schema_context,
        "schema_name": schema_name
    })
    
    sql = response.content.strip()
    if sql.startswith("```sql"):
        sql = sql[6:]
    if sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]
    return sql.strip()

def chat_loop():
    print("======================================================")
    print(" Embrix Conversational BI Agent (Local Llama 3.1)")
    print("======================================================")
    
    from db_connection import get_all_schemas_and_tables
    temp_engine = get_engine(schema_name='public')
    schemas = get_all_schemas_and_tables(temp_engine)
    print("\n--- Available Schemas in Database ---")
    for schema, tables in schemas.items():
        print(f"[{schema}]")
        for table in tables[:5]:
            print(f"  ├─ {table}")
        if len(tables) > 5:
            print(f"  └─ ... and {len(tables)-5} more tables")
    print("-------------------------------------")
    
    schema_input = input(f"\nEnter the schema you want to query [default: {SCHEMA_NAME}]: ").strip()
    schema_to_use = schema_input if schema_input else SCHEMA_NAME
    
    print(f"\nInitializing connection to schema '{schema_to_use}'...")
    engine = get_engine(schema_name=schema_to_use)
    
    print("Checking for empty tables in schema...")
    from db_connection import check_empty_tables
    row_counts = check_empty_tables(engine, schema_name=schema_to_use)
    
    schema_context = build_schema_context(engine, schema_name=schema_to_use, row_counts=row_counts)
    graph = load_knowledge_graph()
    skills_context, loaded_skills = load_agentic_skills()
    
    if not schema_context:
        print("Could not load schema. Please check database connection.")
        return
        
    if loaded_skills:
        print(f"[i] Loaded {len(loaded_skills)} agentic skill playbooks:")
        for skill in loaded_skills:
            print(f"    - {skill}")
    print("Type 'quit' or 'exit' to stop.\n")
    
    while True:
        try:
            question = input("Ask a business question: ")
            if question.strip().lower() in ['quit', 'exit']:
                break
            if not question.strip():
                continue
                
            print("\nGenerating SQL...")
            sql = generate_sql(question, schema_context, graph, skills_context, schema_name=schema_to_use)
            print(f"--- Generated SQL ---\n{sql}\n---------------------")
            
            print("Executing...")
            success, result = execute_sql(engine, sql)
            
            # Simple 1-step self-correction loop
            if not success:
                sql = self_correct_sql(question, sql, result, schema_context, graph, schema_name=schema_to_use)
                print(f"--- Corrected SQL ---\n{sql}\n---------------------")
                success, result = execute_sql(engine, sql)
                
            if success:
                print("\n--- Results ---")
                if result.empty:
                    print("(No data returned)")
                else:
                    print(result.to_string(index=False))
                print("---------------\n")
            else:
                print("\n[X] Failed to execute query even after correction.")
                print(f"Error: {result}\n")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    chat_loop()
