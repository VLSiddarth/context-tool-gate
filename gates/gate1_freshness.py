"""Gate 1: Source Freshness — deterministic context decay scoring.

This module uses KU‑Gateway's internal evaluation engine to:
1. Extract <context> blocks from messages
2. Score them via the Knowledge Universe API
3. Drop any chunk above the decay threshold
4. Reconstruct clean messages
5. Return a structured context_manifest for Gate 2 (evidence contract)
"""

import asyncio
from typing import List, Dict, Any, Tuple, Optional

from ku_gateway.evaluator import Evaluator
from ku_gateway.stripper import Stripper
from ku_gateway.models import ContextChunk
from ku_gateway.config import Settings
from ku_gateway.utils import extract_context_chunks
from ku_gateway.telemetry import logger   # reuse the gateway's logger

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
    stripper.threshold = effective_threshold

    results = await evaluator.evaluate_chunks(chunks)

    # ----- Detect and warn about fallback scores -----
    for r in results:
        if r.decay_score == 0.5 and r.confidence == 0.0:
            logger.warning(
                f"Chunk {r.chunk_id} scored 0.50 (confidence 0.0) – likely fallback. "
                "KU API may be unreachable."
            )

    fresh_chunks, fresh_results, blocked_chunks = stripper.filter_chunks(
        chunks, results
    )

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

    clean_messages = stripper.reconstruct_messages(
        messages, fresh_chunks, chunks
    )

    await evaluator.close()
    return clean_messages, manifest