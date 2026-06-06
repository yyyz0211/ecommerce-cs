"""在 CLI 中查看京东 FAQ RAG 的各个检索阶段。

示例：
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

from app.rag.pipeline import run_rag_pipeline
from app.rag.schemas import RetrievalCandidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="调试京东 FAQ 混合 RAG 检索。")
    parser.add_argument("query", help="要在 FAQ 知识库中检索的用户问题。")
    parser.add_argument("--category", default=None, help="可选分类过滤条件。")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--dense-top-k", type=int, default=10)
    parser.add_argument("--sparse-top-k", type=int, default=10)
    parser.add_argument("--max-context-chars", type=int, default=2400)
    parser.add_argument("--json", action="store_true", help="以 JSON 格式打印完整 trace。")
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
    trace = await run_rag_pipeline(
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
    print("## 查询分析")
    print(f"原始问题: {analysis.raw_query}")
    print(f"归一化问题: {analysis.normalized_query}")
    print(f"推断分类: {analysis.category or '-'}")
    print(f"关键词: {', '.join(analysis.keywords) if analysis.keywords else '-'}")
    print(f"是否需要业务工具: {analysis.needs_business_tool}")

    print_candidates("向量 FAQ 召回", trace.dense_faq, limit=args.dense_top_k)
    print_candidates("向量 Chunk 召回", trace.dense_chunk, limit=args.dense_top_k)
    print_candidates("BM25 召回", trace.sparse, limit=args.sparse_top_k)
    print_candidates("合并候选结果", trace.merged, limit=20)
    print_candidates("重排后候选结果", trace.reranked, limit=20, show_reasons=True)

    selection = trace.selection
    print(f"\n## 最终选中的上下文 ({len(selection.contexts)})")
    print(f"覆盖程度: {selection.coverage} total_chars: {selection.total_chars}")
    for index, candidate in enumerate(selection.contexts, start=1):
        print(candidate_line(index, candidate))
        print(f"    url: {candidate.url}")
        print(f"    片段: {shorten(candidate.text.replace(chr(10), ' '), width=260, placeholder='...')}")


if __name__ == "__main__":
    asyncio.run(main())
