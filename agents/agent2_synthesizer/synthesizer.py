"""Agent 2 — Trend Synthesizer.

Takes Agent 1's shortlist (agent1_shortlist.json) plus the qualitative creative-analysis
reports a human ran through a third-party tool, and clusters them into a small number of
trend archetypes with metrics-grounded justification — the "research summary + why we
should catch this trend" deliverable.

Reports can be supplied two ways:
  --reports-dir           one .txt file per creative, named per report_manifest.csv
  --combined-reports-file one file with all reports pasted together, unlabeled — Claude
                           matches each section to the right creative itself

Usage:
    python synthesizer.py \\
        --shortlist sample_data/sample_agent1_output/agent1_shortlist.json \\
        --reports-dir sample_data/sample_agent1_output/reports \\
        --no-llm

    python synthesizer.py --shortlist output/agent1_shortlist.json --reports-dir output/reports

    python synthesizer.py --shortlist output/agent1_shortlist.json \\
        --combined-reports-file output/all_summaries.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from prompt import (  # noqa: E402
    SYSTEM_PROMPT,
    SYNTHESIZE_TOOL,
    build_user_message,
    build_user_message_combined,
)


def load_shortlist(shortlist_path: str) -> list[dict]:
    data = json.loads(Path(shortlist_path).read_text())
    if not isinstance(data, list) or not data:
        raise ValueError(f"{shortlist_path} did not contain a non-empty list of creatives.")
    missing_filename = [r["app"] for r in data if "report_filename" not in r]
    if missing_filename:
        raise ValueError(
            "Shortlist entries are missing 'report_filename' — regenerate it with the "
            "current version of agents/agent1_selector/selector.py."
        )
    return data


def attach_reports(shortlist: list[dict], reports_dir: str) -> list[dict]:
    reports_path = Path(reports_dir)
    combined = []
    missing = []
    for record in shortlist:
        report_file = reports_path / record["report_filename"]
        if not report_file.exists():
            missing.append(record["report_filename"])
            continue
        combined.append({**record, "qualitative_report": report_file.read_text().strip()})

    if missing:
        print(
            f"Warning: {len(missing)}/{len(shortlist)} report file(s) not found in "
            f"{reports_dir}, proceeding without them: {missing}",
            file=sys.stderr,
        )
    if not combined:
        raise RuntimeError(f"No report files found in {reports_dir} — nothing to synthesize.")
    if len(combined) < config.MIN_REPORTS_RECOMMENDED:
        print(
            f"Warning: only {len(combined)}/{len(shortlist)} reports available — synthesis "
            f"quality will be weaker with this few data points.",
            file=sys.stderr,
        )
    return combined


def load_combined_reports(path: str) -> str:
    text = Path(path).read_text().strip()
    if not text:
        raise ValueError(f"{path} is empty.")
    return text


def synthesize_with_llm_combined(shortlist: list[dict], combined_text: str, model: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[SYNTHESIZE_TOOL],
        tool_choice={"type": "tool", "name": "synthesize_trends"},
        messages=[{"role": "user", "content": build_user_message_combined(shortlist, combined_text)}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "synthesize_trends":
            return block.input
    raise RuntimeError("Claude did not return a synthesize_trends tool call.")


def fallback_synthesis_combined(shortlist: list[dict], combined_text: str) -> dict:
    """Used when --no-llm is set or no API key is configured. Matching reports to
    creatives by game name requires the LLM, so there's no meaningful placeholder
    beyond confirming the inputs loaded."""
    return {
        "executive_summary": (
            f"[placeholder] {len(shortlist)} shortlisted creatives and "
            f"{len(combined_text)} characters of combined report text loaded; "
            f"no matching or synthesis performed (--no-llm)."
        ),
        "trend_archetypes": [],
        "overall_justification": "Run without --no-llm — matching reports to creatives needs the LLM.",
    }


def synthesize_with_llm(combined: list[dict], model: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[SYNTHESIZE_TOOL],
        tool_choice={"type": "tool", "name": "synthesize_trends"},
        messages=[{"role": "user", "content": build_user_message(combined)}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "synthesize_trends":
            return block.input
    raise RuntimeError("Claude did not return a synthesize_trends tool call.")


def fallback_synthesis(combined: list[dict]) -> dict:
    """Used when --no-llm is set or no API key is configured. Naive grouping by
    tier only — no real pattern clustering, just enough to exercise the pipeline."""
    proven = [r["app"] for r in combined if r["tier"] == "proven"]
    emerging = [r["app"] for r in combined if r["tier"] == "emerging"]
    archetypes = []
    if proven:
        archetypes.append(
            {
                "name": "[placeholder] proven tier grouping",
                "pattern_description": (
                    "No LLM clustering performed (--no-llm). This is just every "
                    "'proven' tier creative bucketed together, not a real pattern."
                ),
                "supporting_creatives": proven,
                "tier_signal": "proven",
                "justification": "Run without --no-llm for real synthesis.",
            }
        )
    if emerging:
        archetypes.append(
            {
                "name": "[placeholder] emerging tier grouping",
                "pattern_description": (
                    "No LLM clustering performed (--no-llm). This is just every "
                    "'emerging' tier creative bucketed together, not a real pattern."
                ),
                "supporting_creatives": emerging,
                "tier_signal": "emerging",
                "justification": "Run without --no-llm for real synthesis.",
            }
        )
    return {
        "executive_summary": (
            f"[placeholder] {len(combined)} creatives loaded with reports; "
            f"no real synthesis performed (--no-llm)."
        ),
        "trend_archetypes": archetypes,
        "overall_justification": "Run without --no-llm for a real justification.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 2 — Trend Synthesizer")
    parser.add_argument("--shortlist", required=True, help="Path to agent1_shortlist.json")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--reports-dir", help="Directory of per-creative .txt reports, named per report_manifest.csv"
    )
    input_group.add_argument(
        "--combined-reports-file",
        help=(
            "A single file containing all reports pasted together, unlabeled — Claude "
            "matches each section to the right creative by the game name in its text."
        ),
    )
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--model", default=config.DEFAULT_MODEL)
    parser.add_argument(
        "--no-llm", action="store_true", help="Skip the Claude synthesis step (placeholder output)"
    )
    args = parser.parse_args()

    shortlist = load_shortlist(args.shortlist)
    use_llm = not args.no_llm and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not args.no_llm and not use_llm:
        print(
            "ANTHROPIC_API_KEY not set — falling back to placeholder synthesis "
            "(pass --no-llm to silence this).",
            file=sys.stderr,
        )

    if args.combined_reports_file:
        combined_text = load_combined_reports(args.combined_reports_file)
        result = (
            synthesize_with_llm_combined(shortlist, combined_text, args.model)
            if use_llm
            else fallback_synthesis_combined(shortlist, combined_text)
        )
    else:
        combined = attach_reports(shortlist, args.reports_dir)
        result = synthesize_with_llm(combined, args.model) if use_llm else fallback_synthesis(combined)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "agent2_trend_summary.json"
    out_json.write_text(json.dumps(result, indent=2))

    print(f"\nWrote trend synthesis to {out_json}\n")
    print("EXECUTIVE SUMMARY")
    print(result["executive_summary"])
    print()
    for i, arche in enumerate(result["trend_archetypes"], 1):
        print(f"{i}. {arche['name']} [{arche['tier_signal']}]")
        print(f"   Pattern: {arche['pattern_description']}")
        print(f"   Evidence: {', '.join(arche['supporting_creatives'])}")
        print(f"   Why it matters: {arche['justification']}")
        print()
    print("OVERALL JUSTIFICATION")
    print(result["overall_justification"])


if __name__ == "__main__":
    main()
