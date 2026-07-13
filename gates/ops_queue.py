"""Ops Queue Simulator — routes, recovers, escalates, and assigns next owner.

Outcome taxonomy (Matt Bell's 5 states) + next_owner mapping:
- recovered_auto             → next_owner: agent (resume)
- escalated_resolved_sla     → next_owner: ops_team (close ticket)
- escalated_breached_sla     → next_owner: manager (review SLA breach)
- false_positive             → next_owner: data_science (tune thresholds)
- recovery_failed_manual     → next_owner: on_call_engineer (manual fix)
"""

import time
import random
from typing import Dict, Any

ROUTING_MAP = {
    "data_pipeline": "jira:data_eng",
    "ops_team": "pagerduty:ops_squad",
    "security": "pagerduty:secops",
    "agent": "noop",
    "developer": "slack:dev_channel",
    "tool_owner": "jira:tools",
}

RECOVERY_CONFIG = {
    "refresh_context": {"simulate": True, "success_rate": 0.6},
    "fix_tool_payload": {"simulate": True, "success_rate": 0.9},
    "register_tool": {"simulate": False},
    "await_approval": {"simulate": False},
    "block_tool": {"simulate": False},
    "execute": {"simulate": True, "success_rate": 1.0},
}

# Next owner assignment per outcome
NEXT_OWNER_MAP = {
    "recovered_auto": "agent",
    "escalated_resolved_sla": "ops_team",
    "escalated_breached_sla": "manager",
    "false_positive": "data_science",
    "recovery_failed_manual": "on_call_engineer",
}

DEFAULT_SLA_MINUTES = 30


def parse_timeout_minutes(timeout_str: str) -> int:
    if not timeout_str or timeout_str == "immediate":
        return 1
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
    resolution_time = random.randint(5, 120)
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
) -> tuple[str, str]:
    """
    Simulate the entire recovery flow and return (outcome_label, next_owner).
    """
    action_type = expected_action["type"]

    if gate_allowed and action_type == "execute":
        return "recovered_auto", NEXT_OWNER_MAP["recovered_auto"]

    # Simulate possible false positive (10%)
    if random.random() < 0.1:
        return "false_positive", NEXT_OWNER_MAP["false_positive"]

    recovery_result = simulate_recovery(action_type, evidence_id)
    if recovery_result["status"] == "recovered":
        return "recovered_auto", NEXT_OWNER_MAP["recovered_auto"]

    # Recovery failed – escalate
    routing = route_action(expected_action)
    sla_minutes = routing["timeout_minutes"]
    escalation_result = escalate_and_resolve(
        action_type, expected_action["owner"], evidence_id, sla_minutes
    )

    if escalation_result["resolved_within_sla"]:
        return "escalated_resolved_sla", NEXT_OWNER_MAP["escalated_resolved_sla"]
    else:
        # If escalation also breached, it's manual intervention scenario
        # But we already distinguish; escalated_breached_sla is the label.
        # recovery_failed_manual would be if manual step fails, but we can treat
        # escalated_breached_sla as needing manual review by manager.
        return "escalated_breached_sla", NEXT_OWNER_MAP["escalated_breached_sla"]