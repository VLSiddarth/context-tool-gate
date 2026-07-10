"""Ops Queue Simulator — routes expected_action, simulates recovery,
   escalates, and returns a structured outcome taxonomy.

Outcome taxonomy (Matt Bell's 5 states):
- recovered_auto             : automatic recovery succeeded
- escalated_resolved_sla     : escalated and resolved within SLA
- escalated_breached_sla     : escalated but resolution breached SLA
- false_positive             : block was unnecessary / no action needed
- recovery_failed_manual     : recovery action failed and required manual intervention
"""

import time
import random
from typing import Dict, Any, Optional

# Routing table: owner → target queue
ROUTING_MAP = {
    "data_pipeline": "jira:data_eng",
    "ops_team": "pagerduty:ops_squad",
    "security": "pagerduty:secops",
    "agent": "noop",
    "developer": "slack:dev_channel",
    "tool_owner": "jira:tools",
}

# Recovery simulation config
RECOVERY_CONFIG = {
    "refresh_context": {"simulate": True, "success_rate": 0.6},
    "fix_tool_payload": {"simulate": True, "success_rate": 0.9},
    "register_tool": {"simulate": False},
    "await_approval": {"simulate": False},
    "block_tool": {"simulate": False},
    "execute": {"simulate": True, "success_rate": 1.0},
}

# SLA timeouts in minutes (default if not parsed)
DEFAULT_SLA_MINUTES = 30


def parse_timeout_minutes(timeout_str: str) -> int:
    """Convert a timeout string like '15m' or 'immediate' to minutes."""
    if not timeout_str or timeout_str == "immediate":
        return 1  # immediate is treated as 1 minute
    timeout_str = timeout_str.lower().replace(" ", "")
    if timeout_str.endswith("m"):
        try:
            return int(timeout_str[:-1])
        except ValueError:
            return DEFAULT_SLA_MINUTES
    if timeout_str.endswith("h"):
        try:
            return int(timeout_str[:-1]) * 60
        except ValueError:
            return DEFAULT_SLA_MINUTES
    return DEFAULT_SLA_MINUTES


def route_action(expected_action: Dict[str, str]) -> Dict[str, Any]:
    """Determine the routing target for an expected action."""
    owner = expected_action.get("owner", "unknown")
    target = ROUTING_MAP.get(owner, "unknown_queue")
    return {
        "action_type": expected_action.get("type"),
        "owner": owner,
        "routing_target": target,
        "timeout_minutes": parse_timeout_minutes(expected_action.get("timeout", "immediate")),
        "inspect_artifact": expected_action.get("inspect", "unknown"),
    }


def simulate_recovery(action_type: str, evidence_id: str) -> Dict[str, Any]:
    """Simulate an automated recovery attempt."""
    config = RECOVERY_CONFIG.get(action_type, {})
    if not config.get("simulate", False):
        return {
            "status": "not_attempted",
            "reason": f"Recovery for '{action_type}' is not automated.",
            "evidence_id": evidence_id,
            "timestamp": time.time(),
        }

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


def escalate_and_resolve(action_type: str, owner: str, evidence_id: str, timeout_minutes: int) -> Dict[str, Any]:
    """Simulate escalation and resolution within/outside SLA."""
    # Simulate time taken to resolve after escalation (random)
    resolution_time = random.randint(5, 120)  # minutes
    resolved_within_sla = resolution_time <= timeout_minutes

    return {
        "status": "escalated",
        "action_type": action_type,
        "owner": owner,
        "evidence_id": evidence_id,
        "escalation_target": ROUTING_MAP.get(owner, "unknown"),
        "resolution_time_minutes": resolution_time,
        "sla_timeout_minutes": timeout_minutes,
        "resolved_within_sla": resolved_within_sla,
        "timestamp": time.time(),
    }


def determine_final_outcome(
    gate_allowed: bool,
    expected_action: Dict[str, str],
    evidence_id: str,
    manual_review_false_positive: bool = False,
) -> str:
    """
    Determine the final recovery outcome taxonomy after a gate decision.
    This runs the full simulation of routing, recovery, escalation, and resolution.
    Returns one of the five taxonomy states.
    """
    action_type = expected_action["type"]

    # If the gate allowed, it's a normal execution (not a block). But we're only called
    # when a block/approval decision has been made, so this path is for non-auto cases.
    # Auto-runs (execute) would be success, but we map them to 'recovered_auto' if needed.
    if gate_allowed and action_type == "execute":
        return "recovered_auto"

    # Simulate possible false positive (random 10% chance if evidence was actually fresh but blocked)
    if random.random() < 0.1:
        return "false_positive"

    # Try automatic recovery
    recovery_result = simulate_recovery(action_type, evidence_id)
    if recovery_result["status"] == "recovered":
        return "recovered_auto"

    # Recovery failed → escalate
    routing = route_action(expected_action)
    sla_minutes = routing["timeout_minutes"]
    escalation_result = escalate_and_resolve(action_type, expected_action["owner"], evidence_id, sla_minutes)

    if escalation_result["resolved_within_sla"]:
        return "escalated_resolved_sla"
    else:
        return "escalated_breached_sla"