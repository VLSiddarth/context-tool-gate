"""Gate 2: Evidence Contract — deterministic validation of tool call payloads.

Returns structured result with a machine‑readable 'code' and an 'expected_action'
for each rejection path.
"""

from typing import Dict, Any, List

REQUIRED_FIELDS: Dict[str, List[str]] = {
    "send_email": ["recipient", "subject", "evidence_ids"],
    "create_ticket": ["title", "description", "priority", "evidence_ids"],
    "deploy_service": ["service_name", "version", "environment", "evidence_ids"],
    "update_customer_record": ["customer_id", "field", "value", "evidence_ids"],
}

UNIVERSAL_REQUIRED = ["tool"]

# Recovery actions for each reason code
ACTION_MAP = {
    "missing_required_field": {
        "type": "fix_tool_payload",
        "owner": "developer",
        "timeout": "immediate",
        "inspect": "tool_call_schema"
    },
    "unknown_tool": {
        "type": "register_tool",
        "owner": "tool_owner",
        "timeout": "24h",
        "inspect": "tool_registry"
    },
    "missing_evidence_ids": {
        "type": "fix_tool_payload",
        "owner": "developer",
        "timeout": "immediate",
        "inspect": "tool_call_schema"
    },
    "evidence_missing": {
        "type": "refresh_context",
        "owner": "data_pipeline",
        "timeout": "15m",
        "inspect": "retrieval_manifest"
    },
    "evidence_stale": {
        "type": "refresh_context",
        "owner": "data_pipeline",
        "timeout": "15m",
        "inspect": "retrieval_manifest"
    },
    "evidence_conflict": {
        "type": "refresh_context",
        "owner": "data_pipeline",
        "timeout": "15m",
        "inspect": "retrieval_manifest"
    },
    "evidence_ok": {
        "type": "proceed",
        "owner": "agent",
        "timeout": "immediate",
        "inspect": "evidence_manifest"
    }
}


def validate_evidence(
    manifest: Dict[str, Any],
    tool_call: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a tool call against a context manifest.

    Returns a dict with:
      - "allowed": bool
      - "code": str          (stable reason code)
      - "reason": str        (human‑readable)
      - "expected_action": dict
    """
    # Universal required fields
    for field in UNIVERSAL_REQUIRED:
        if field not in tool_call:
            code = "missing_required_field"
            return {
                "allowed": False,
                "code": code,
                "reason": f"Missing required field '{field}' in tool call.",
                "expected_action": ACTION_MAP[code]
            }

    tool_name = tool_call["tool"]
    required_fields = REQUIRED_FIELDS.get(tool_name)
    if required_fields is None:
        code = "unknown_tool"
        return {
            "allowed": False,
            "code": code,
            "reason": f"Unknown tool '{tool_name}'. No schema defined.",
            "expected_action": ACTION_MAP[code]
        }

    for field in required_fields:
        if field not in tool_call:
            code = "missing_required_field"
            return {
                "allowed": False,
                "code": code,
                "reason": f"Missing required field '{field}' for tool '{tool_name}'.",
                "expected_action": ACTION_MAP[code]
            }

    evidence_ids: List[str] = tool_call.get("evidence_ids", [])
    if not evidence_ids:
        code = "missing_evidence_ids"
        return {
            "allowed": False,
            "code": code,
            "reason": f"Tool '{tool_name}' requires at least one evidence_id.",
            "expected_action": ACTION_MAP[code]
        }

    manifest_chunks: Dict[str, Dict[str, Any]] = {
        chunk["id"]: chunk for chunk in manifest.get("chunks", [])
    }

    for eid in evidence_ids:
        chunk = manifest_chunks.get(eid)
        if chunk is None:
            code = "evidence_missing"
            return {
                "allowed": False,
                "code": code,
                "reason": f"Evidence id '{eid}' not found in context manifest.",
                "expected_action": ACTION_MAP[code]
            }

        if not chunk.get("kept", False):
            code = "evidence_stale"
            return {
                "allowed": False,
                "code": code,
                "reason": f"Evidence id '{eid}' is stale (kept=False) and cannot be used.",
                "expected_action": ACTION_MAP[code]
            }

        if chunk.get("conflict_detected", False):
            code = "evidence_conflict"
            return {
                "allowed": False,
                "code": code,
                "reason": f"Evidence id '{eid}' has a detected conflict with more recent knowledge.",
                "expected_action": ACTION_MAP[code]
            }

    code = "evidence_ok"
    return {
        "allowed": True,
        "code": code,
        "reason": "All evidence present, fresh, and no conflicts.",
        "expected_action": ACTION_MAP[code]
    }