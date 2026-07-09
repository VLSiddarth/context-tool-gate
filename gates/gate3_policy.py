"""Gate 3: Authority / Risk — policy-based execution decision."""

from typing import Literal, Dict

Decision = Literal["auto", "approve", "block"]

TOOL_RISK: Dict[str, str] = {
    "send_email":             "low",
    "create_ticket":          "low",
    "update_customer_record": "high",
    "deploy_service":         "high",
    "delete_db":              "high",
    "grant_permissions":      "high",
    "run_destructive_test":   "high",
    "send_invoice":           "high",
}

POLICY: Dict[str, Dict[str, Decision]] = {
    "send_email":             {"low": "auto",    "high": "approve"},
    "create_ticket":          {"low": "auto",    "high": "approve"},
    "update_customer_record": {"low": "approve", "high": "approve"},
    "deploy_service":         {"low": "approve", "high": "block"},
    "delete_db":              {"low": "approve", "high": "block"},
    "grant_permissions":      {"low": "approve", "high": "block"},
    "run_destructive_test":   {"low": "approve", "high": "block"},
    "send_invoice":           {"low": "approve", "high": "approve"},
}

# Expected actions for each policy decision
ACTION_MAP = {
    "auto": {
        "type": "execute",
        "owner": "agent",
        "timeout": "immediate",
        "inspect": "tool_log"
    },
    "approve": {
        "type": "await_approval",
        "owner": "ops_team",
        "timeout": "30m",
        "inspect": "approval_queue"
    },
    "block": {
        "type": "block_tool",
        "owner": "security",
        "timeout": "immediate",
        "inspect": "policy_violation_log"
    }
}


def evaluate_policy(tool_name: str, risk_override: str = None) -> Dict[str, any]:
    """
    Decide what to do with a tool call.

    Returns:
        dict with keys "decision", "reason", "code", "expected_action"
    """
    risk = risk_override or TOOL_RISK.get(tool_name, "high")
    tool_policy = POLICY.get(tool_name, {})
    decision = tool_policy.get(risk, "approve")

    code_map = {
        "auto": "policy_auto",
        "approve": "policy_requires_approval",
        "block": "policy_blocked_tool"
    }
    code = code_map.get(decision, "policy_unknown")

    reason = (
        f"Tool '{tool_name}' classified as {risk} risk. "
        f"Decision: {decision}."
    )
    expected_action = ACTION_MAP[decision]

    return {
        "decision": decision,
        "reason": reason,
        "code": code,
        "expected_action": expected_action
    }   