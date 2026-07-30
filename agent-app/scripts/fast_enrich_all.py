#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from embrix.schema_store.store import SchemaStore

def generate_heuristic_description(qname, table):
    schema = table.schema_name
    tbl = table.table_name
    
    # Humanized table name
    words = tbl.replace("_", " ").title()
    
    if schema == "core_enums":
        desc = f"Enumeration lookup table storing valid system codes and labels for {words}."
    elif schema == "core_usage":
        desc = f"Usage readings and telemetry tracking table for {words} within the rating engine."
    elif schema == "core_revenue":
        desc = f"Financial ledger and revenue recognition table tracking {words}."
    elif schema == "core_oms":
        desc = f"Order management and service provisioning table tracking {words}."
    elif schema == "core_pricing":
        desc = f"Pricing catalog, discount, and rate-card configuration table for {words}."
    elif schema == "core_mediation":
        desc = f"CDR mediation, file ingestion, and carrier traffic processing record for {words}."
    elif schema == "core_migration":
        desc = f"Data migration staging and account onboarding record for {words}."
    elif schema == "core_gateway":
        desc = f"Third-party integration and gateway provider transaction log for {words}."
    elif schema == "core_config":
        desc = f"System configuration and rule parameter table for {words}."
    elif schema == "core_backup":
        desc = f"Historical snapshot and backup table for {words}."
    elif schema == "core_engine":
        desc = f"Rating engine execution state and rule evaluation record for {words}."
    else:
        desc = f"Database entity table representing {words} within the {schema} system."
        
    return desc

def main():
    store = SchemaStore()
    snapshot = store.load()
    
    count = 0
    for qname, table in snapshot.tables.items():
        if not table.description:
            table.description = generate_heuristic_description(qname, table)
            count += 1
            
        for col in table.columns:
            if not col.description:
                cwords = col.name.replace("_", " ").title()
                if col.name in table.primary_key:
                    col.description = f"Unique primary key identifier for {table.table_name}."
                elif col.name.endswith("id"):
                    col.description = f"Foreign key or reference identifier for {cwords[:-2]}."
                elif "date" in col.name or "time" in col.name or "created" in col.name or "updated" in col.name:
                    col.description = f"Timestamp recording when {cwords} occurred."
                elif "status" in col.name:
                    col.description = f"Current state or status code for {cwords[:-7]}."
                elif "amount" in col.name or "value" in col.name or "price" in col.name or "count" in col.name:
                    col.description = f"Quantitative numeric value representing {cwords}."
                else:
                    col.description = f"Attribute storing {cwords}."
                    
    store.save(snapshot)
    print(f"Successfully enriched {count} table descriptions across all {len(snapshot.tables)} tables in snapshot.")

if __name__ == "__main__":
    main()
