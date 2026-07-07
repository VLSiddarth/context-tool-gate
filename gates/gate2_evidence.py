"""Gate 2: Evidence Contract — deterministic validation of tool call payloads.

This module enforces a hard schema on tool calls before execution.
It answers two questions automatically:
1. Does every piece of evidence the tool claims to rely on actually exist and is still fresh?
2. Does the tool call contain all the required fields for that action?

If either fails, the call is blocked. No model judgement, no grey area.
"""

from typing import Dict, Any, List, Optional

# ---------------------------------------------------------------------------
# Tool schemas: every tool listed here must provide these fields.
# Extend this table as new tools are added.
# ---------------------------------------------------------------------------
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "send_email": ["recipient", "subject", "evidence_ids"],
    "create_ticket": ["title", "description", "priority", "evidence_ids"],
    "deploy_service": ["service_name", "version", "environment", "evidence_ids"],
    "update_customer_record": ["customer_id", "field", "value", "evidence_ids"],
}

# Fields that are required for *any* tool call, regardless of type.
UNIVERSAL_REQUIRED = ["tool"]

# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------
def validate_evidence(
    manifest: Dict[str, Any],
    tool_call: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a tool call against a context manifest (Gate 1 output).

    Args:
        manifest: The context_manifest dict produced by Gate 1.
                  Expected structure:
                  {
                      "chunks": [
                          {"id": ..., "kept": bool, "conflict_detected": bool, ...},
                          ...
                      ],
                      "summary": {...}
                  }
        tool_call: The tool payload to validate.
                   Must contain at least a "tool" field.
                   Should contain an "evidence_ids" list (references to manifest chunks).

    Returns:
        A dict with:
        - "allowed": bool   – True if the tool call passes all checks.
        - "reason": str     – explanation for the decision.
    """

    # ------------------------------------------------------------------
    # 1. Check for universal required fields
    # ------------------------------------------------------------------
    for field in UNIVERSAL_REQUIRED:
        if field not in tool_call:
            return {
                "allowed": False,
                "reason": f"Missing required field '{field}' in tool call."
            }

    tool_name = tool_call["tool"]

    # ------------------------------------------------------------------
    # 2. Check tool‑specific required fields
    # ------------------------------------------------------------------
    required_fields = REQUIRED_FIELDS.get(tool_name)
    if required_fields is None:
        # Unknown tool – block by default (safe fail‑closed)
        return {
            "allowed": False,
            "reason": f"Unknown tool '{tool_name}'. No schema defined."
        }

    for field in required_fields:
        if field not in tool_call:
            return {
                "allowed": False,
                "reason": f"Missing required field '{field}' for tool '{tool_name}'."
            }

    # ------------------------------------------------------------------
    # 3. Evidence validation
    # ------------------------------------------------------------------
    evidence_ids: List[str] = tool_call.get("evidence_ids", [])
    if not evidence_ids:
        # If the tool schema requires evidence but none provided, block.
        return {
            "allowed": False,
            "reason": f"Tool '{tool_name}' requires at least one evidence_id."
        }

    # Build a lookup of manifest chunks by id
    manifest_chunks: Dict[str, Dict[str, Any]] = {
        chunk["id"]: chunk for chunk in manifest.get("chunks", [])
    }

    for eid in evidence_ids:
        chunk = manifest_chunks.get(eid)
        if chunk is None:
            return {
                "allowed": False,
                "reason": f"Evidence id '{eid}' not found in context manifest. "
                          f"It may have been dropped or never existed."
            }

        if not chunk.get("kept", False):
            return {
                "allowed": False,
                "reason": f"Evidence id '{eid}' is stale (kept=False) and cannot be used."
            }

        if chunk.get("conflict_detected", False):
            return {
                "allowed": False,
                "reason": f"Evidence id '{eid}' has a detected conflict with more recent knowledge."
            }

    # ------------------------------------------------------------------
    # All checks passed
    # ------------------------------------------------------------------
    return {
        "allowed": True,
        "reason": "All evidence present, fresh, and no conflicts."
    }