"""context-tool-gate demo — Three‑Gate LLM Safety Pipeline."""

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


def run_scenario(name, messages, tool_name, threshold=None):
    print_header(f"Scenario: {name}")
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
        table = Table(title="Chunk Details", box=box.MINIMAL)
        table.add_column("ID", style="dim")
        table.add_column("Decay", justify="right")
        table.add_column("Status")
        table.add_column("Reason", style="dim")
        for c in manifest["chunks"]:
            status = "[green]KEPT[/green]" if c["kept"] else "[red]DROPPED[/red]"
            table.add_row(
                c["id"],
                f"{c['decay_score']:.2f}" if c['decay_score'] is not None else "N/A",
                status,
                c["reason"]
            )
        console.print(table)
    else:
        console.print("No context chunks found.")

    # Build tool call using the first chunk's real ID
    chunk_id = manifest["chunks"][0]["id"] if manifest["chunks"] else "unknown"
    tool_call = {
        "tool": tool_name,
        "evidence_ids": [chunk_id],
    }
    if tool_name == "deploy_service":
        tool_call.update({
            "service_name": "payment-api",
            "version": "2.4.1",
            "environment": "production"
        })
    elif tool_name == "send_email":
        tool_call.update({
            "recipient": "customer@example.com",
            "subject": "Welcome!"
        })

    # Gate 2
    print_header("Gate 2 – Evidence Contract")
    result = validate_evidence(manifest, tool_call)
    if result["allowed"]:
        console.print(Panel(f"✅ {result['reason']}", border_style="green"))
        # Gate 3
        print_header("Gate 3 – Authority / Risk Policy")
        decision = evaluate_policy(tool_name)
        console.print(Panel(
            f"Tool: {tool_name}\nDecision: {decision['decision']}\n{decision['reason']}",
            border_style="yellow" if decision['decision'] == "approve" else "green"
        ))
    else:
        console.print(Panel(f"🛑 {result['reason']}", border_style="red"))
        console.print("[bold red]Execution blocked by Gate 2.[/bold red]")


def main():
    if hasattr(console, 'print'):
        console.print(Panel(
            "[bold blue]context-tool-gate[/bold blue] – Three‑Gate LLM Safety Demo\n"
            "Freshness → Evidence → Policy",
            border_style="blue"
        ))

    # ── Stale scenario: real old arXiv paper (2019) ──
    run_scenario(
        "Stale Context – Expected Gate 2 BLOCK (real 2019 arXiv paper)",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Deploy the latest hotfix. "
                                        "<context>https://arxiv.org/abs/1906.08237</context>"}
        ],
        tool_name="deploy_service",
        threshold=0.5   # rely on real decay score, not a forced low threshold
    )

    # ── Fresh scenario: recent arXiv paper (2025) ──
    run_scenario(
        "Fresh Context – Expected ALL PASS",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Send a welcome email to the new customer. "
                                        "<context>https://arxiv.org/abs/2501.05409</context>"}
        ],
        tool_name="send_email",
        threshold=0.5
    )


if __name__ == "__main__":
    main()