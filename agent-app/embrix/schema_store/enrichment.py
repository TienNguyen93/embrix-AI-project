"""
embrix.schema_store.enrichment
──────────────────────────────
Phase 3: Contextual Pre-Embedding Enrichment Engine.

Bakes business terminology, user query synonyms, and domain tags into schema 
descriptions BEFORE vector embedding to eliminate the semantic gap between
technical database table names and plain-English user questions.
"""

import re
import logging
from typing import Dict, List, Optional
from embrix.schema_store.models import TableMetadata, ColumnMetadata, SchemaSnapshot

logger = logging.getLogger("embrix.schema_store.enrichment")

# Domain mapping dictionary based on schema prefixes and naming heuristics
DOMAIN_MAP: Dict[str, Dict[str, str]] = {
    "core_usage": {
        "domain": "Usage & Telemetry Rating Engine",
        "terms": "usage readings, meter readings, electricity consumption, data telemetry, call records, rating errors, proration"
    },
    "core_revenue": {
        "domain": "Revenue Accounting & Ledger",
        "terms": "revenue sharing, accounting entries, P&L data, deferral revenue, GL journal entries, billing adjustments"
    },
    "core_engine": {
        "domain": "Billing & Account Management",
        "terms": "invoices, account balance, customer accounts, invoice summary, payment installments, billing profile, tax details"
    },
    "core_oms": {
        "domain": "Order Management & Subscriptions",
        "terms": "billable service pricing, order items, service plans, product offerings, subscriptions"
    },
    "core_pricing": {
        "domain": "Pricing & Catalog Tariff",
        "terms": "pricing rules, rate cards, discounts, unit prices, tariff plans"
    },
    "core_mediation": {
        "domain": "CDR & Data Mediation",
        "terms": "raw usage files, CDR parsing, carrier interconexion, mediation control"
    },
    "core_config": {
        "domain": "System Configuration & Mapping",
        "terms": "GL account ranges, chart of accounts, collection profiles, usage platform config"
    }
}

# Common column name business synonym lookup
COLUMN_SYNONYMS: Dict[str, str] = {
    "accountid": "Customer Account Identifier / Account Number",
    "readingvalue": "Usage Consumption Volume / kWh / Units Used",
    "latestreadingdate": "Usage Timestamp / Date of Reading",
    "total_amount": "Total Billed Revenue / Invoice Total ($)",
    "tax_amount": "Sales Tax / Value-Added Tax (VAT)",
    "status": "Account / Invoice State (Active, Pending, Paid, Suspended)",
    "servicetype": "Type of Utility Service (Electricity, Voice, Broadband Data)",
    "country": "Geographic Country / Customer Location"
}


class SchemaEnricher:
    """
    Contextual Enrichment Engine.
    Populates factual descriptions + search synonym tags pre-embedding.
    """

    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm

    def enrich_table(self, table: TableMetadata) -> TableMetadata:
        """Enrich a single TableMetadata instance with domain tags and synonyms."""
        schema_info = DOMAIN_MAP.get(table.schema_name, {
            "domain": "General Core Database",
            "terms": "core transactional data"
        })

        domain_title = schema_info["domain"]
        domain_terms = schema_info["terms"]

        # Humanize table name
        clean_name = re.sub(r"[_\-]+", " ", table.table_name).title()
        
        # Build factual business description
        factual_desc = (
            f"Official database table representing {clean_name} within the {domain_title} domain. "
            f"Contains {len(table.columns)} columns."
        )

        # Build retrieval enrichment string (used strictly for embedding & vector search)
        enrichment_terms = f"Related business terms and query topics: {clean_name}, {domain_terms}."
        
        # Combined pre-embedding contextual description
        full_contextual_description = f"{factual_desc}\n\n{enrichment_terms}"

        # Update table description
        table.description = full_contextual_description

        # Enrich columns
        for col in table.columns:
            self.enrich_column(col, table.qualified_name)

        return table

    def enrich_column(self, col: ColumnMetadata, table_name: str):
        """Enrich ColumnMetadata with business synonyms."""
        synonym = COLUMN_SYNONYMS.get(col.name.lower(), "")
        
        col_clean = re.sub(r"[_\-]+", " ", col.name).title()
        col_desc = f"{col_clean} attribute in {table_name}."
        
        if synonym:
            col_desc += f" Synonym: {synonym}."
            
        col.description = col_desc

    def enrich_snapshot(self, snapshot: SchemaSnapshot) -> SchemaSnapshot:
        """Enrich an entire SchemaSnapshot prior to chunking and vector indexing."""
        logger.info(f"Enriching {len(snapshot.tables)} tables with domain tags and business synonyms...")
        for _, table_meta in snapshot.tables.items():
            self.enrich_table(table_meta)
        logger.info("Contextual pre-embedding enrichment complete.")
        return snapshot
