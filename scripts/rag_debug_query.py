"""Inspect JD FAQ RAG retrieval stages from the CLI.

Example:
    python3 scripts/rag_debug_query.py "生鲜商品可以拒收吗？"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from textwrap import shorten

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.rag.hybrid_retriever import retrieve_hybrid
from app.rag.schemas import RetrievalCandidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug JD FAQ hybrid RAG retrieval.")
    parser.add_argument("query", help="User query to retrieve against the FAQ knowledge base.")
    parser.add_argument("--category", default=None, help="Optional category filter.")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--dense-top-k", type=int, default=10)
    parser.add_argument("--sparse-top-k", type=int, default=10)
    parser.add_argument("--max-context-chars", type=int, default=2400)
    parser.add_argument("--json", action="store_true", help="Print full trace as JSON.")
    return parser.parse_args()


def candidate_line(index: int, candidate: RetrievalCandidate) -> str:
    dense = "-" if candidate.dense_score is None else f"{candidate.dense_score:.3f}"
    sparse = "-" if candidate.sparse_score is None else f"{candidate.sparse_score:.3f}"
    final = "-" if candidate.final_score is None else f"{candidate.final_score:.3f}"
    sources = "+".join(candidate.sources) if candidate.sources else "-"
    return (
        f"{index:02d}. final={final} dense={dense} bm25={sparse} "
        f"src={sources} type={candidate.doc_type} cat={candidate.category} "
        f"id={candidate.id} title={candidate.question}"
    )


def print_candidates(title: str, candidates: list[RetrievalCandidate], *, limit: int = 10, show_reasons: bool = False) -> None:
    print(f"\n## {title} ({len(candidates)})")
    if not candidates:
        print("(empty)")
        return
    for index, candidate in enumerate(candidates[:limit], start=1):
        print(candidate_line(index, candidate))
        if show_reasons and candidate.rerank_reasons:
            print(f"    reasons: {'; '.join(candidate.rerank_reasons)}")


async def main() -> None:
    args = parse_args()
    trace = await retrieve_hybrid(
        args.query,
        category=args.category,
        top_k=args.top_k,
        dense_top_k=args.dense_top_k,
        sparse_top_k=args.sparse_top_k,
        max_context_chars=args.max_context_chars,
    )

    if args.json:
        print(json.dumps(trace.model_dump(), ensure_ascii=False, indent=2))
        return

    analysis = trace.analysis
    print("## Query Analysis")
    print(f"raw: {analysis.raw_query}")
    print(f"normalized: {analysis.normalized_query}")
    print(f"category: {analysis.category or '-'}")
    print(f"keywords: {', '.join(analysis.keywords) if analysis.keywords else '-'}")
    print(f"needs_business_tool: {analysis.needs_business_tool}")

    print_candidates("Dense FAQ Recall", trace.dense_faq, limit=args.dense_top_k)
    print_candidates("Dense Chunk Recall", trace.dense_chunk, limit=args.dense_top_k)
    print_candidates("BM25 Recall", trace.sparse, limit=args.sparse_top_k)
    print_candidates("Merged Candidates", trace.merged, limit=20)
    print_candidates("Reranked Candidates", trace.reranked, limit=20, show_reasons=True)

    selection = trace.selection
    print(f"\n## Selected Contexts ({len(selection.contexts)})")
    print(f"coverage: {selection.coverage} total_chars: {selection.total_chars}")
    for index, candidate in enumerate(selection.contexts, start=1):
        print(candidate_line(index, candidate))
        print(f"    url: {candidate.url}")
        print(f"    snippet: {shorten(candidate.text.replace(chr(10), ' '), width=260, placeholder='...')}")


if __name__ == "__main__":
    asyncio.run(main())
