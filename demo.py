"""context-tool-gate demo — Three‑Gate LLM Safety Pipeline with negative‑test matrix."""

import asyncio
from dotenv import load_dotenv
load_dotenv()

from gates.gate1_freshness import evaluate_freshness
from gates.gate2_evidence import validate_evidence
from gates.gate3_policy import evaluate_policy

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    console = Console()
except ImportError:
    console = None


def print_header(text: str):
    if hasattr(console, 'rule'):
        console.rule(f"[bold cyan]{text}[/bold cyan]")
    else:
        print(f"\n--- {text} ---")


def run_scenario(name, messages, tool_name, tool_extra=None, threshold=None,
                 fake_evidence_id=None):
    """
    Run a single scenario and print the 5‑step audit trail.

    Parameters
    ----------
    name : str
        Human‑readable scenario description.
    messages : list
        Messages to send through Gate 1 (must contain at least one <context>).
    tool_name : str
        The tool the (simulated) LLM wants to call.
    tool_extra : dict, optional
        Extra fields to add to the tool call (e.g., recipient, subject).
    threshold : float, optional
        Decay threshold override. Defaults to KU_DECAY_THRESHOLD from .env.
    fake_evidence_id : str, optional
        If given, the tool call will use this id instead of the real chunk id,
        allowing us to simulate a missing evidence scenario.
    """
    print_header(f"Scenario: {name}")

    # ---------- Gate 1 ----------
    print_header("Gate 1 – Source Freshness")
    clean_messages, manifest = asyncio.run(
        evaluate_freshness(messages, decay_threshold=threshold)
    )

    summary = manifest["summary"]
    console.print(Panel(
        f"Total chunks: {summary['total']}\n"
        f"Kept: {summary['kept']}\n"
        f"Dropped: {summary['dropped']}\n"
        f"Threshold: {summary['threshold']}",
        title="Context Manifest Summary",
        border_style="green" if summary["dropped"] == 0 else "red"
    ))

    if manifest["chunks"]:
        tbl = Table(title="Chunk Details", box=box.MINIMAL)
        tbl.add_column("ID", style="dim")
        tbl.add_column("Decay", justify="right")
        tbl.add_column("Status")
        tbl.add_column("Reason", style="dim")
        for c in manifest["chunks"]:
            status = "[green]KEPT[/green]" if c["kept"] else "[red]DROPPED[/red]"
            tbl.add_row(
                c["id"],
                f"{c['decay_score']:.2f}" if c['decay_score'] is not None else "N/A",
                status,
                c["reason"]
            )
        console.print(tbl)
    else:
        console.print("No context chunks found.")

    # ----- Build tool call -----
    # Use the first chunk's real ID unless a fake one is provided (for the missing‑id test)
    real_chunk_id = manifest["chunks"][0]["id"] if manifest["chunks"] else "unknown"
    evidence_id = fake_evidence_id if fake_evidence_id else real_chunk_id

    tool_call = {
        "tool": tool_name,
        "evidence_ids": [evidence_id],
    }
    if tool_extra:
        tool_call.update(tool_extra)

    # ---------- Gate 2 ----------
    print_header("Gate 2 – Evidence Contract")
    gate2 = validate_evidence(manifest, tool_call)

    # ---------- Gate 3 ----------
    gate3 = None
    final_decision = "BLOCKED"
    reason_code = gate2.get("code", "unknown")
    final_reason = gate2["reason"]

    if gate2["allowed"]:
        gate3 = evaluate_policy(tool_name)
        final_decision = gate3["decision"].upper()
        reason_code = gate3.get("code", "unknown")
        final_reason = gate3["reason"]

    # ---------- Print Audit Trail ----------
    print_header("Audit Trail")
    audit = Table(title="5‑Step Trace", box=box.MINIMAL)
    audit.add_column("Step", style="bold cyan")
    audit.add_column("Detail", style="white")

    # 1. Item ID
    audit.add_row("1. Item ID", evidence_id)

    # 2. Freshness score / kept or dropped
    chunk = next((c for c in manifest["chunks"] if c["id"] == evidence_id), None)
    if chunk:
        freshness = f"decay {chunk['decay_score']:.2f} → {'KEPT' if chunk['kept'] else 'DROPPED'}"
    else:
        freshness = "NOT IN MANIFEST"
    audit.add_row("2. Freshness Score / Status", freshness)

    # 3. Evidence contract check
    evidence_status = gate2["reason"]
    if gate2["allowed"]:
        evidence_status = "✅ " + evidence_status
    else:
        evidence_status = "🛑 " + evidence_status
    audit.add_row("3. Evidence Contract", evidence_status)

    # 4. Policy decision
    if gate3:
        policy_text = f"{gate3['decision'].upper()} — {gate3['reason']}"
    else:
        policy_text = "NOT REACHED (blocked at Gate 2)"
    audit.add_row("4. Policy Decision", policy_text)

    # 5. Final reason code
    code_style = "[green]" if (gate2["allowed"] and gate3 and gate3['decision'] == 'auto') else "[bold red]"
    audit.add_row("5. Reason Code", f"{code_style}{reason_code}[/]")

    console.print(audit)
    console.print(Panel(
        f"Final result: {final_decision}\n{final_reason}",
        border_style="red" if final_decision != "AUTO" else "green"
    ))


def main():
    if hasattr(console, 'print'):
        console.print(Panel(
            "[bold blue]context-tool-gate[/bold blue] – Three‑Gate LLM Safety Demo\n"
            "Freshness → Evidence → Policy",
            border_style="blue"
        ))

    # ── Scenario 1: evidence_id missing from manifest → block ──
    run_scenario(
        "Missing Evidence ID – Expected Gate 2 BLOCK (evidence_missing)",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Send welcome email. "
                                        "<context>https://arxiv.org/abs/2501.05409</context>"}
        ],
        tool_name="send_email",
        tool_extra={"recipient": "hi@example.com", "subject": "Welcome"},
        threshold=0.5,
        fake_evidence_id="non_existent_id"   # forces missing evidence
    )

    # ── Scenario 2: evidence present but stale/dropped → block ──
    run_scenario(
        "Stale Evidence – Expected Gate 2 BLOCK (evidence_stale)",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Deploy hotfix. "
                                        "<context>https://arxiv.org/abs/1906.08237</context>"}
        ],
        tool_name="deploy_service",
        tool_extra={"service_name": "api", "version": "1.0", "environment": "prod"},
        threshold=0.5   # real decay will be high
    )

    # ── Scenario 3: evidence fresh, but tool risk high → require approval ──
    run_scenario(
        "Fresh Evidence + High‑Risk Tool – Expected APPROVAL REQUIRED (policy_requires_approval)",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Update customer record. "
                                        "<context>https://arxiv.org/abs/2501.05409</context>"}
        ],
        tool_name="update_customer_record",
        tool_extra={"customer_id": "123", "field": "address", "value": "New address"},
        threshold=0.5
    )

    # ── Scenario 4: evidence fresh + low‑risk tool → auto‑run ──
    run_scenario(
        "Fresh Evidence + Low‑Risk Tool – Expected AUTO (policy_auto)",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Send welcome email. "
                                        "<context>https://arxiv.org/abs/2501.05409</context>"}
        ],
        tool_name="send_email",
        tool_extra={"recipient": "hi@example.com", "subject": "Welcome"},
        threshold=0.5
    )


if __name__ == "__main__":
    main()