"""Gate 3: Authority / Risk — policy-based execution decision.

This module answers one question: given a tool and its risk classification,
should the system auto-execute, require human approval, or block the action?

It does NOT re-evaluate evidence or context. Those are handled by Gate 1 & 2.
Gate 3 only decides on risk posture, based on the tool and the risk level of
the current context/request.
"""

from typing import Literal, Dict

# Possible decisions
Decision = Literal["auto", "approve", "block"]

# ---------------------------------------------------------------------------
# Tool risk classification
# ---------------------------------------------------------------------------
# low  – reversible, internal, limited blast radius
# high – irreversible, customer-facing, financial/safety impact
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

# ---------------------------------------------------------------------------
# Policy table: tool → risk level → decision
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------
def evaluate_policy(tool_name: str, risk_override: str = None) -> Dict[str, str]:
    """
    Decide what to do with a tool call based on its risk level.

    Args:
        tool_name: The name of the tool (e.g., 'send_email').
        risk_override: If provided, overrides the default risk classification.
                       Useful when a specific request carries additional risk context.

    Returns:
        A dict with:
        - "decision": "auto" | "approve" | "block"
        - "reason":   human-readable explanation
    """
    # Determine the risk level (default from TOOL_RISK, or overridden)
    risk = risk_override or TOOL_RISK.get(tool_name, "high")  # unknown tools default to high risk

    # Look up the decision for this tool + risk level
    tool_policy = POLICY.get(tool_name, {})
    decision = tool_policy.get(risk, "approve")  # default to "approve" for undefined combinations

    reason = (
        f"Tool '{tool_name}' classified as {risk} risk. "
        f"Decision: {decision}."
    )

    return {"decision": decision, "reason": reason}