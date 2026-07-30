# 📊 Embrix AI Agent — RAG Evaluation Benchmark Architecture & Metrics

This document provides a detailed explanation of the **RAG & NL-to-SQL Evaluation Framework** implemented in [`agent-app/embrix/eval/`](embrix/eval/).

---

## 1. Executive Overview

In large enterprise databases with over **1,000+ tables**, evaluating the performance of a RAG system requires quantitative metrics to ensure:
1. **Schema Retrieval Accuracy**: Does the system retrieve the exact database tables needed to answer the user's question?
2. **Query Safety & Read-Only Audit**: Are generated SQL queries syntactically valid and strictly read-only (`SELECT` / `WITH`)?
3. **Execution Latency**: Is response time fast enough for interactive conversational UI usage?

The Embrix AI benchmark engine automatedly calculates **Recall@K**, **Precision@K**, **Mean Reciprocal Rank (MRR)**, and **EXPLAIN Pass Rate**.

---

## 2. Benchmark Suite Architecture

The evaluation framework consists of 3 core components:

```
agent-app/embrix/eval/
├── benchmark_dataset.jsonl   # 20-Case Gold Standard Ground Truth Dataset
├── evaluator.py              # Metrics Engine (Recall@K, Precision@K, MRR, Audit Pass Rate)
└── run_eval.py               # CLI Runner & Formatted Report Printer
```

---

## 3. Mathematical Metric Definitions

### 🔹 Recall@K
Measures the proportion of relevant ground-truth target tables that were successfully retrieved in the Top-K results ($K=5$):

$$\text{Recall@K} = \frac{|\text{Retrieved Tables in Top-K} \cap \text{Expected Tables}|}{|\text{Expected Tables}|}$$

- **Target**: $> 85\%$ when connected to live `pgvector` HNSW index.

---

### 🔹 Precision@K
Measures how many of the top-K retrieved tables were actually relevant (avoiding schema noise in LLM context):

$$\text{Precision@K} = \frac{|\text{Retrieved Tables in Top-K} \cap \text{Expected Tables}|}{K}$$

---

### 🔹 Mean Reciprocal Rank (MRR)
Measures the quality of ranking by evaluating where the *first* correct table appears in the candidate list:

$$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$

- If the correct table is ranked 1st: $\text{Reciprocal Rank} = 1 / 1 = 1.0$.
- If the correct table is ranked 2nd: $\text{Reciprocal Rank} = 1 / 2 = 0.5$.

---

### 🔹 EXPLAIN & Security Audit Pass Rate
Measures the percentage of generated SQL queries that pass security checks:
- **Read-Only Verification**: Rejects any non-SELECT statements (`DELETE`, `DROP`, `UPDATE`, `INSERT`).
- **Syntax Check**: Passes PostgreSQL dry-run parsing.

---

## 4. Ground-Truth Dataset Structure (`benchmark_dataset.jsonl`)

The dataset contains 20 curated test cases across 7 core enterprise business domains (`core_usage`, `core_engine`, `core_revenue`, `core_oms`, `core_pricing`, `core_mediation`, `core_config`).

Sample entry:
```json
{
  "id": 1,
  "question": "Show service usage readings by date and service type",
  "expected_tables": ["core_usage.service_usage_readings", "core_backup.coopeg_services"],
  "domain": "core_usage"
}
```

---

## 5. How to Run the Benchmark

Open **Git Bash** in `agent-app/` and run:

```bash
python -m embrix.eval.run_eval
```

Sample Terminal Report:
```text
============================================================
      EMBRIX AI AGENT — RAG BENCHMARK EVALUATION RESULT
============================================================
| Metric                     | Score / Value   |
|----------------------------|-----------------|
| Total Evaluation Queries   | 20              |
| Recall@5                   | 85.00%          |
| Precision@5                | 34.00%          |
| Mean Reciprocal Rank (MRR) | 0.8125          |
| EXPLAIN Pass Rate          | 100.0%          |
| Average Latency per Query  | 2180.2 ms       |
============================================================
```
