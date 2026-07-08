"""Gate 2: Evidence Contract — deterministic validation of tool call payloads.

Returns structured result with a machine-readable 'code' for each rejection path.
"""

from typing import Dict, Any, List

REQUIRED_FIELDS: Dict[str, List[str]] = {
    "send_email": ["recipient", "subject", "evidence_ids"],
    "create_ticket": ["title", "description", "priority", "evidence_ids"],
    "deploy_service": ["service_name", "version", "environment", "evidence_ids"],
    "update_customer_record": ["customer_id", "field", "value", "evidence_ids"],
}

UNIVERSAL_REQUIRED = ["tool"]


def validate_evidence(
    manifest: Dict[str, Any],
    tool_call: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a tool call against a context manifest.

    Returns a dict with keys:
      - "allowed": bool
      - "code": str   (stable reason code)
      - "reason": str (human-readable)
    """
    # Universal required fields
    for field in UNIVERSAL_REQUIRED:
        if field not in tool_call:
            return {
                "allowed": False,
                "code": "missing_required_field",
                "reason": f"Missing required field '{field}' in tool call."
            }

    tool_name = tool_call["tool"]
    required_fields = REQUIRED_FIELDS.get(tool_name)
    if required_fields is None:
        return {
            "allowed": False,
            "code": "unknown_tool",
            "reason": f"Unknown tool '{tool_name}'. No schema defined."
        }

    for field in required_fields:
        if field not in tool_call:
            return {
                "allowed": False,
                "code": "missing_required_field",
                "reason": f"Missing required field '{field}' for tool '{tool_name}'."
            }

    evidence_ids: List[str] = tool_call.get("evidence_ids", [])
    if not evidence_ids:
        return {
            "allowed": False,
            "code": "missing_evidence_ids",
            "reason": f"Tool '{tool_name}' requires at least one evidence_id."
        }

    manifest_chunks: Dict[str, Dict[str, Any]] = {
        chunk["id"]: chunk for chunk in manifest.get("chunks", [])
    }

    for eid in evidence_ids:
        chunk = manifest_chunks.get(eid)
        if chunk is None:
            return {
                "allowed": False,
                "code": "evidence_missing",
                "reason": f"Evidence id '{eid}' not found in context manifest."
            }

        if not chunk.get("kept", False):
            return {
                "allowed": False,
                "code": "evidence_stale",
                "reason": f"Evidence id '{eid}' is stale (kept=False) and cannot be used."
            }

        if chunk.get("conflict_detected", False):
            return {
                "allowed": False,
                "code": "evidence_conflict",
                "reason": f"Evidence id '{eid}' has a detected conflict with more recent knowledge."
            }

    return {
        "allowed": True,
        "code": "evidence_ok",
        "reason": "All evidence present, fresh, and no conflicts."
    }