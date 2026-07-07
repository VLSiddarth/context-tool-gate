"""Gate 1: Source Freshness — deterministic context decay scoring."""

import asyncio
from typing import List, Dict, Any, Tuple, Optional

from ku_gateway.evaluator import Evaluator
from ku_gateway.stripper import Stripper
from ku_gateway.models import ContextChunk
from ku_gateway.config import Settings
from ku_gateway.utils import extract_context_chunks

# Default settings from environment (used if no override)
settings = Settings()


async def evaluate_freshness(
    messages: List[Dict[str, Any]],
    decay_threshold: Optional[float] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Run the upstream freshness gate.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        decay_threshold: If given, overrides KU_DECAY_THRESHOLD for this call.

    Returns:
        (clean_messages, context_manifest)
    """
    chunks = extract_context_chunks(messages)
    effective_threshold = decay_threshold if decay_threshold is not None else settings.decay_threshold

    if not chunks:
        return messages, {
            "chunks": [],
            "summary": {
                "total": 0,
                "kept": 0,
                "dropped": 0,
                "threshold": effective_threshold,
            },
        }

    evaluator = Evaluator()
    stripper = Stripper()
    # Override the stripper's threshold for this run
    stripper.threshold = effective_threshold

    results = await evaluator.evaluate_chunks(chunks)
    fresh_chunks, fresh_results, blocked_chunks = stripper.filter_chunks(chunks, results)

    manifest = {
        "chunks": [],
        "summary": {
            "total": len(chunks),
            "kept": len(fresh_chunks),
            "dropped": len(blocked_chunks),
            "threshold": effective_threshold,
        },
    }

    result_by_id = {r.chunk_id: r for r in results}
    for chunk in chunks:
        res = result_by_id.get(chunk.id)
        kept = chunk in fresh_chunks
        reason = "kept" if kept else (
            f"decay_score {res.decay_score:.2f} ≥ threshold {effective_threshold}"
            if res else "not evaluated"
        )

        manifest["chunks"].append({
            "id": chunk.id,
            "content_preview": chunk.content[:80],
            "decay_score": res.decay_score if res else None,
            "confidence": res.confidence if res else None,
            "knowledge_velocity": res.knowledge_velocity if res else None,
            "conflict_detected": res.conflict_detected if res else False,
            "kept": kept,
            "reason": reason,
        })

    clean_messages = stripper.reconstruct_messages(messages, fresh_chunks, chunks)
    await evaluator.close()
    return clean_messages, manifest