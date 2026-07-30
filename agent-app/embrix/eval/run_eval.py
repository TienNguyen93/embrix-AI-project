"""
embrix.eval.run_eval
────────────────────
CLI Benchmark Runner for Phase 7 RAG Evaluation.
"""

import os
import sys
import logging
from tabulate import tabulate

# Add package directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from embrix.eval.evaluator import RAGEvaluator

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("run_eval")


def run():
    dataset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_dataset.jsonl")
    logger.info("Initializing RAG Benchmark Evaluator...")
    
    evaluator = RAGEvaluator()
    metrics = evaluator.run_benchmark(dataset_path=dataset_path, top_k=5)

    summary_table = [
        ["Total Evaluation Queries", metrics.total_queries],
        ["Recall@5", f"{metrics.recall_at_k * 100:.2f}%"],
        ["Precision@5", f"{metrics.precision_at_k * 100:.2f}%"],
        ["Mean Reciprocal Rank (MRR)", f"{metrics.mrr:.4f}"],
        ["EXPLAIN Pass Rate", f"{metrics.explain_pass_rate:.1f}%"],
        ["Average Latency per Query", f"{metrics.avg_latency_sec * 1000:.1f} ms"]
    ]

    print("\n" + "=" * 60)
    print("      EMBRIX AI AGENT — RAG BENCHMARK EVALUATION RESULT")
    print("=" * 60)
    print(tabulate(summary_table, headers=["Metric", "Score / Value"], tablefmt="github"))
    print("=" * 60 + "\n")

    logger.info("=== PHASE 7 BENCHMARK EVALUATION COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    run()
