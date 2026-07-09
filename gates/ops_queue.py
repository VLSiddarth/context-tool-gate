"""Ops Queue Simulator — routes expected_action, simulates recovery, and audits the result.

This is a lightweight simulation of what would become a Jira/PagerDuty
integration in production. Every function returns a structured dict that can
be logged as a trace event.
"""

import time
from typing import Dict, Any

# Routing table: owner → target queue
ROUTING_MAP = {
    "data_pipeline": "jira:data_eng",
    "ops_team": "pagerduty:ops_squad",
    "security": "pagerduty:secops",
    "agent": "noop",          # auto-run, no routing needed
    "developer": "slack:dev_channel",
    "tool_owner": "jira:tools",
}

# Recovery simulation: which actions can be auto-recovered, and their success probability
RECOVERY_CONFIG = {
    "refresh_context": {"simulate": True, "success_rate": 0.7},
    "fix_tool_payload": {"simulate": True, "success_rate": 0.9},
    "register_tool": {"simulate": False},  # needs human
    "await_approval": {"simulate": False},
    "block_tool": {"simulate": False},
    "execute": {"simulate": True, "success_rate": 1.0},
}


def route_action(expected_action: Dict[str, str]) -> Dict[str, Any]:
    """Determine the routing target for an expected action."""
    owner = expected_action.get("owner", "unknown")
    target = ROUTING_MAP.get(owner, "unknown_queue")
    return {
        "action_type": expected_action.get("type"),
        "owner": owner,
        "routing_target": target,
        "timeout_minutes": expected_action.get("timeout", "unknown"),
        "inspect_artifact": expected_action.get("inspect", "unknown"),
    }


def simulate_recovery(action_type: str, evidence_id: str) -> Dict[str, Any]:
    """Simulate an automated recovery attempt. Returns a trace event."""
    config = RECOVERY_CONFIG.get(action_type, {})
    if not config.get("simulate", False):
        return {
            "status": "not_attempted",
            "reason": f"Recovery for '{action_type}' is not automated.",
            "evidence_id": evidence_id,
            "timestamp": time.time(),
        }

    # Simulate success/failure based on config
    import random
    success = random.random() < config.get("success_rate", 0.5)
    if success:
        return {
            "status": "recovered",
            "action_type": action_type,
            "evidence_id": evidence_id,
            "timestamp": time.time(),
        }
    else:
        return {
            "status": "recovery_failed",
            "action_type": action_type,
            "evidence_id": evidence_id,
            "timestamp": time.time(),
        }


def escalate(action_type: str, owner: str, evidence_id: str) -> Dict[str, Any]:
    """Create an escalation event after recovery failure."""
    return {
        "status": "escalated",
        "action_type": action_type,
        "owner": owner,
        "evidence_id": evidence_id,
        "escalation_target": ROUTING_MAP.get(owner, "unknown"),
        "timestamp": time.time(),
    }