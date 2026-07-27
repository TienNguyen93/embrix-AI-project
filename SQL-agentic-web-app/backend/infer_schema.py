import os
import json
import networkx as nx
from dotenv import load_dotenv
from db_connection import get_engine, get_schema_tables, get_table_columns
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.1")

def build_schema_context(engine, schema_name=None, row_counts=None):
    """
    Fetches all tables and their columns to build a text representation of the schema.
    """
    # If not provided, rely on default in get_schema_tables
    tables = get_schema_tables(engine, schema=schema_name) if schema_name else get_schema_tables(engine)
    schema_context = []
    for table in tables:
        if row_counts and table in row_counts and row_counts[table] == 0:
            continue
            
        columns = get_table_columns(engine, table, schema=schema_name) if schema_name else get_table_columns(engine, table)
        col_strings = [f"{col['name']} ({str(col['type'])})" for col in columns]
        row_count_str = ""
        if row_counts and table in row_counts:
            rc = row_counts[table]
            if rc > 0:
                row_count_str = f" (Rows: {rc})"
        schema_context.append(f"Table: {table}{row_count_str}\nColumns: {', '.join(col_strings)}")
        
    return "\n\n".join(schema_context)

def infer_relationships_with_llm(schema_text):
    """
    Uses local Qwen3.5 to analyze the schema text and infer foreign key relationships.
    """
    llm = ChatOllama(
        model="qwen3.5",
        base_url=OLLAMA_BASE_URL,
        temperature=0.0
    )
    
    prompt = PromptTemplate.from_template(
        """You are an expert database architect. Analyze the following database schema and infer the logical foreign key relationships between the tables.
Pay close attention to column names (e.g., 'customer_id' in 'invoices' likely maps to 'id' in 'customers').

Schema:
{schema_text}

Output your response strictly as a JSON list of objects, with no markdown formatting or extra text. Each object should have the following keys:
- source_table: the table containing the foreign key
- source_column: the foreign key column
- target_table: the table being referenced
- target_column: the primary key column being referenced

Example output:
[
  {{"source_table": "orders", "source_column": "user_id", "target_table": "users", "target_column": "id"}}
]
"""
    )
    
    chain = prompt | llm
    print("Sending schema to Llama 3.1 for inference. This may take a moment depending on your local hardware...")
    
    response = chain.invoke({"schema_text": schema_text})
    
    # Clean the response in case the model added markdown blocks like ```json ... ```
    content = response.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
        
    try:
        relationships = json.loads(content.strip())
        return relationships
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM output as JSON. Raw output:\n{response.content}")
        return []

def build_and_save_knowledge_graph(relationships, row_counts=None, output_file="schema_graph.graphml"):
    """
    Builds a networkx directed graph from the inferred relationships and saves it to disk.
    """
    G = nx.DiGraph()
    
    for rel in relationships:
        src = rel["source_table"]
        tgt = rel["target_table"]
        # Add edge from source to target representing the foreign key dependency
        # We store the column mapping as edge attributes
        G.add_edge(src, tgt, source_column=rel["source_column"], target_column=rel["target_column"])
        
    if row_counts:
        for node in G.nodes():
            rc = row_counts.get(node, -1)
            G.nodes[node]["row_count"] = rc
            G.nodes[node]["is_empty"] = (rc == 0)
            
    print(f"Graph built with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    
    # Save graph for later use by the agent
    nx.write_graphml(G, output_file)
    print(f"Knowledge Graph saved to {output_file}")
    return G

if __name__ == "__main__":
    engine = get_engine()
    
    from db_connection import check_empty_tables
    print("Checking for empty tables to enrich graph profiling...")
    row_counts = check_empty_tables(engine)
    
    print("Extracting schema context...")
    schema_text = build_schema_context(engine, row_counts=row_counts)
    
    if not schema_text:
        print("No schema found or connection failed. Please check your .env settings.")
    else:
        print(f"Schema context extracted ({len(schema_text)} characters).\nInferring relationships...")
        relationships = infer_relationships_with_llm(schema_text)
        
        if relationships:
            print(f"Inferred {len(relationships)} relationships:")
            for r in relationships:
                print(f"  {r['source_table']}.{r['source_column']} -> {r['target_table']}.{r['target_column']}")
                
            build_and_save_knowledge_graph(relationships, row_counts=row_counts)
        else:
            print("No relationships inferred or JSON parsing failed.")
