import json
import networkx as nx
from db_connection import get_engine, get_table_columns

def export_to_json():
    print("Loading schema_graph.graphml...")
    try:
        G = nx.read_graphml("schema_graph.graphml")
    except Exception as e:
        print(f"Error loading graphml: {e}")
        return
        
    engine = get_engine()
    
    print("Fetching column metadata for each table in the graph...")
    for node in G.nodes():
        # Fetch columns from the database for this table
        columns = get_table_columns(engine, node)
        # Convert type to string since SQLAlchemy types aren't JSON serializable
        col_list = [{"name": col["name"], "type": str(col["type"])} for col in columns]
        
        # Add metadata to the node
        G.nodes[node]["columns"] = col_list
        G.nodes[node]["table_name"] = node

    # Convert graph to dictionary format suitable for JSON
    data = nx.node_link_data(G)
    
    output_file = "schema_graph.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    print(f"Knowledge graph exported successfully to {output_file}!")

if __name__ == "__main__":
    export_to_json()
