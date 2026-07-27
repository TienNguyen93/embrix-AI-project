import networkx as nx
import matplotlib.pyplot as plt

def export_to_png():
    print("Loading schema_graph.graphml...")
    try:
        G = nx.read_graphml("schema_graph.graphml")
    except Exception as e:
        print(f"Error loading graphml: {e}")
        return
        
    plt.figure(figsize=(14, 10))
    
    # Use a layout that spreads nodes out
    pos = nx.spring_layout(G, k=2, seed=42)
    
    # Draw nodes
    nx.draw_networkx_nodes(G, pos, node_size=3000, node_color='skyblue', alpha=0.8)
    
    # Draw edges
    nx.draw_networkx_edges(G, pos, edge_color='gray', arrows=True, arrowsize=20, width=1.5)
    
    # Draw node labels (table names)
    nx.draw_networkx_labels(G, pos, font_size=9, font_weight='bold')
    
    # Draw edge labels (foreign key columns)
    edge_labels = {}
    for u, v, data in G.edges(data=True):
        src_col = data.get('source_column', '')
        tgt_col = data.get('target_column', '')
        edge_labels[(u, v)] = f"{src_col}\n↓\n{tgt_col}"
        
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8, font_color='darkred')
    
    plt.title("Core Usage - Schema Knowledge Graph", size=16, pad=20)
    plt.axis('off')
    
    output_file = "schema_graph.png"
    plt.tight_layout()
    plt.savefig(output_file, format="PNG", dpi=300, bbox_inches='tight')
    print(f"Knowledge graph successfully exported to {output_file}!")

if __name__ == "__main__":
    export_to_png()
