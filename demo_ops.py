"""demo_ops.py – extended demo with closed‑loop recovery simulation and outcome taxonomy."""

import asyncio
from dotenv import load_dotenv
load_dotenv()

from gates.gate1_freshness import evaluate_freshness
from gates.gate2_evidence import validate_evidence
from gates.gate3_policy import evaluate_policy
from gates.ops_queue import (
    route_action,
    simulate_recovery,
    escalate_and_resolve,
    determine_final_outcome,
)

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
                 fake_evidence_id=None, simulate_recovery_attempt=True):
    print_header(f"Scenario: {name}")

    # Gate 1
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

    real_chunk_id = manifest["chunks"][0]["id"] if manifest["chunks"] else "unknown"
    evidence_id = fake_evidence_id if fake_evidence_id else real_chunk_id

    tool_call = {"tool": tool_name, "evidence_ids": [evidence_id]}
    if tool_extra:
        tool_call.update(tool_extra)

    # Gate 2
    print_header("Gate 2 – Evidence Contract")
    gate2 = validate_evidence(manifest, tool_call)

    # Gate 3
    gate3 = None
    final_decision = "BLOCKED"
    reason_code = gate2["code"]
    final_reason = gate2["reason"]
    expected_action = gate2["expected_action"]
    if gate2["allowed"]:
        gate3 = evaluate_policy(tool_name)
        final_decision = gate3["decision"].upper()
        reason_code = gate3["code"]
        final_reason = gate3["reason"]
        expected_action = gate3["expected_action"]

    # Audit Trail (6 steps)
    print_header("Audit Trail")
    audit = Table(title="6‑Step Trace (with recovery instruction)", box=box.MINIMAL)
    audit.add_column("Step", style="bold cyan")
    audit.add_column("Detail", style="white")

    audit.add_row("1. Item ID", evidence_id)

    chunk = next((c for c in manifest["chunks"] if c["id"] == evidence_id), None)
    if chunk:
        freshness = f"decay {chunk['decay_score']:.2f} → {'KEPT' if chunk['kept'] else 'DROPPED'}"
    else:
        freshness = "NOT IN MANIFEST"
    audit.add_row("2. Freshness Score / Status", freshness)

    evidence_status = gate2["reason"]
    if gate2["allowed"]:
        evidence_status = "✅ " + evidence_status
    else:
        evidence_status = "🛑 " + evidence_status
    audit.add_row("3. Evidence Contract", evidence_status)

    if gate3:
        policy_text = f"{gate3['decision'].upper()} — {gate3['reason']}"
    else:
        policy_text = "NOT REACHED (blocked at Gate 2)"
    audit.add_row("4. Policy Decision", policy_text)

    code_style = "[green]" if (gate2["allowed"] and gate3 and gate3['decision'] == 'auto') else "[bold red]"
    audit.add_row("5. Reason Code", f"{code_style}{reason_code}[/]")

    action_str = (
        f"[bold yellow]{expected_action['type']}[/] | owner: {expected_action['owner']} | "
        f"timeout: {expected_action['timeout']} | inspect: {expected_action['inspect']}"
    )
    audit.add_row("6. Expected Action", action_str)
    console.print(audit)

    # Closed-loop recovery simulation
    if simulate_recovery_attempt and final_decision != "AUTO":
        print_header("Ops Queue — Closed‑Loop Recovery Simulation")
        routing = route_action(expected_action)
        console.print(f"📬 Routing: [bold]{routing['routing_target']}[/] (owner: {routing['owner']})")

        # Use the full outcome taxonomy determination
        final_outcome = determine_final_outcome(
            gate_allowed=gate2["allowed"],
            expected_action=expected_action,
            evidence_id=evidence_id,
        )

        outcome_display = {
            "recovered_auto": "[green]RECOVERED AUTOMATICALLY[/green]",
            "escalated_resolved_sla": "[yellow]ESCALATED — RESOLVED WITHIN SLA[/yellow]",
            "escalated_breached_sla": "[red]ESCALATED — BREACHED SLA[/red]",
            "false_positive": "[dim]FALSE POSITIVE / NO ACTION NEEDED[/dim]",
            "recovery_failed_manual": "[red]RECOVERY FAILED — MANUAL INTERVENTION REQUIRED[/red]",
        }.get(final_outcome, f"UNKNOWN: {final_outcome}")

        console.print(Panel(f"Final Outcome: {outcome_display}", border_style="bold"))

        # If you want to show the individual steps that led to the outcome, you can still print them:
        # (optional – you can uncomment to see the detailed simulation steps)
        # recovery_result = simulate_recovery(expected_action["type"], evidence_id)
        # print(recovery_result)
        # if recovery_result["status"] == "recovery_failed":
        #     escalation_result = escalate_and_resolve(expected_action["type"], expected_action["owner"], evidence_id, routing["timeout_minutes"])
        #     print(escalation_result)

    console.print(Panel(
        f"Final result: {final_decision}\n{final_reason}",
        border_style="red" if final_decision != "AUTO" else "green"
    ))


def main():
    if hasattr(console, 'print'):
        console.print(Panel(
            "[bold blue]context-tool-gate[/bold blue] – Three‑Gate LLM Safety Demo\n"
            "Freshness → Evidence → Policy + Closed‑Loop Recovery + Outcome Taxonomy",
            border_style="blue"
        ))

    # Force a stale scenario with low threshold to always trigger recovery path
    run_scenario(
        "Stale Evidence – Closed‑Loop Recovery with Outcome Taxonomy",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Deploy hotfix. "
                                        "<context>https://arxiv.org/abs/1906.08237</context>"}
        ],
        tool_name="deploy_service",
        tool_extra={"service_name": "api", "version": "1.0", "environment": "prod"},
        threshold=0.01,   # guaranteed drop
        simulate_recovery_attempt=True
    )


if __name__ == "__main__":
    main()