"""Agent 1 — Selector.

Takes a manually-exported Sensor Tower creative list (already scoped to a
genre/adjacency the user chose at export time) and picks a top-10 shortlist
for the downstream creative-analysis tool: 6 "proven" long-running winners +
4 "emerging" recently-first-seen creatives already gaining impression share.

Deterministic filtering/scoring happens in pandas; an optional Claude call at
the end sanity-checks tier labels, flags likely duplicate creatives, and
writes the per-creative rationale that Agent 2 will read.

Usage:
    python selector.py --input sample_data/sensor_tower_export_sample.csv --no-llm
    python selector.py --input path/to/export.csv --output-dir output/
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from prompt import SYSTEM_PROMPT, FINALIZE_TOOL, build_user_message  # noqa: E402


def _read_csv_robust(input_path: str) -> pd.DataFrame:
    """Sensor Tower/Excel exports are often UTF-16 or tab-delimited rather
    than plain UTF-8 comma-separated — try the common combinations instead
    of making the user guess."""
    last_err: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            return pd.read_csv(input_path, encoding=encoding)
        except UnicodeError as e:
            last_err = e
        except pd.errors.ParserError as e:
            try:
                return pd.read_csv(input_path, encoding=encoding, sep=None, engine="python")
            except Exception as e2:
                last_err = e2
    raise RuntimeError(
        f"Could not read {input_path} as UTF-8, UTF-16, or Latin-1 CSV. "
        f"Try re-exporting it as a plain CSV. Original error: {last_err}"
    )


def load_data(input_path: str) -> pd.DataFrame:
    df = _read_csv_robust(input_path)
    df.columns = [c.strip() for c in df.columns]
    missing = [col for col in config.COLUMN_MAP.values() if col not in df.columns]
    if missing:
        raise ValueError(
            f"Input is missing expected columns {missing}. "
            f"Adjust config.COLUMN_MAP if your export uses different headers."
        )
    df[config.COLUMN_MAP["first_seen"]] = pd.to_datetime(
        df[config.COLUMN_MAP["first_seen"]], errors="coerce"
    )
    df[config.COLUMN_MAP["last_seen"]] = pd.to_datetime(
        df[config.COLUMN_MAP["last_seen"]], errors="coerce"
    )
    df[config.COLUMN_MAP["impression_share"]] = pd.to_numeric(
        df[config.COLUMN_MAP["impression_share"]], errors="coerce"
    )

    dur_col = config.COLUMN_MAP["duration"]
    duration_numeric = pd.to_numeric(df[dur_col], errors="coerce")
    computed = (
        df[config.COLUMN_MAP["last_seen"]] - df[config.COLUMN_MAP["first_seen"]]
    ).dt.days
    df["_duration_days"] = duration_numeric.fillna(computed)

    before = len(df)
    df = df.dropna(
        subset=[
            config.COLUMN_MAP["first_seen"],
            config.COLUMN_MAP["last_seen"],
            config.COLUMN_MAP["impression_share"],
            "_duration_days",
        ]
    )
    dropped = before - len(df)
    if dropped:
        print(f"Dropped {dropped} row(s) with unparseable dates/impression share.", file=sys.stderr)
    return df


def filter_rows(df: pd.DataFrame) -> pd.DataFrame:
    obj_col = config.COLUMN_MAP["ad_objectives"]
    install_mask = (
        df[obj_col]
        .astype(str)
        .str.contains("|".join(config.INSTALL_OBJECTIVE_KEYWORDS), case=False, na=False)
    )

    type_col = config.COLUMN_MAP["type"]
    type_mask = df[type_col].astype(str).str.contains(
        "|".join(config.AD_TYPE_KEYWORDS), case=False, na=False
    )

    filtered = df[install_mask & type_mask].copy()
    print(
        f"Filtered {len(df)} -> {len(filtered)} rows "
        f"(install objective + {'/'.join(config.AD_TYPE_KEYWORDS)} type).",
        file=sys.stderr,
    )
    return filtered


def score_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    impr_col = config.COLUMN_MAP["impression_share"]
    first_seen_col = config.COLUMN_MAP["first_seen"]
    networks_col = config.COLUMN_MAP["networks"]

    # Rank within each network, not globally: networks differ wildly in how
    # long creatives typically run and how impression share is distributed
    # (e.g. AppLovin creatives can run for years; Meta/TikTok rotate much
    # faster), so a global percentile just rewards whichever network has
    # structurally bigger numbers instead of surfacing genuinely strong
    # creatives on each channel.
    grouped = df.groupby(networks_col)
    df["_impression_pct"] = grouped[impr_col].rank(pct=True)
    df["_duration_pct"] = grouped["_duration_days"].rank(pct=True)
    # Later first-seen date -> larger rank -> higher recency score.
    df["_recency_pct"] = grouped[first_seen_col].rank(pct=True)

    pw, ew = config.PROVEN_WEIGHTS, config.EMERGING_WEIGHTS
    df["_proven_score"] = (
        pw["impression_share"] * df["_impression_pct"] + pw["duration"] * df["_duration_pct"]
    )
    df["_emerging_score"] = (
        ew["impression_share"] * df["_impression_pct"] + ew["recency"] * df["_recency_pct"]
    )
    return df


def select_shortlist(df: pd.DataFrame) -> pd.DataFrame:
    adv_col = config.COLUMN_MAP["advertiser"]
    net_col = config.COLUMN_MAP["networks"]
    advertiser_counts: dict[str, int] = {}
    network_counts: dict[str, int] = {}
    picked_idx: list[int] = []
    tiers: dict[int, str] = {}

    def try_pick(sorted_df: pd.DataFrame, n: int, tier: str) -> None:
        taken = 0
        for idx, row in sorted_df.iterrows():
            if taken >= n:
                break
            if idx in picked_idx:
                continue
            advertiser = row[adv_col]
            network = row[net_col]
            if advertiser_counts.get(advertiser, 0) >= config.MAX_PER_ADVERTISER:
                continue
            if network_counts.get(network, 0) >= config.MAX_PER_NETWORK:
                continue
            picked_idx.append(idx)
            tiers[idx] = tier
            advertiser_counts[advertiser] = advertiser_counts.get(advertiser, 0) + 1
            network_counts[network] = network_counts.get(network, 0) + 1
            taken += 1
        if taken < n:
            print(
                f"Warning: only found {taken}/{n} '{tier}' picks within the "
                f"max-{config.MAX_PER_ADVERTISER}-per-advertiser / "
                f"max-{config.MAX_PER_NETWORK}-per-network caps.",
                file=sys.stderr,
            )

    try_pick(df.sort_values("_proven_score", ascending=False), config.TOP_PROVEN, "proven")
    try_pick(df.sort_values("_emerging_score", ascending=False), config.TOP_EMERGING, "emerging")

    shortlist = df.loc[picked_idx].copy()
    shortlist["_tier"] = [tiers[idx] for idx in picked_idx]
    return shortlist


def shortlist_to_records(shortlist: pd.DataFrame) -> list[dict]:
    cm = config.COLUMN_MAP
    records = []
    for _, row in shortlist.iterrows():
        records.append(
            {
                "app": row[cm["app"]],
                "creative_link": row[cm["creative_link"]],
                "networks": row[cm["networks"]],
                "tier": row["_tier"],
                "impression_share_pct": round(row[cm["impression_share"]] * 100, 3),
                "duration_days": int(row["_duration_days"]),
                "first_seen": row[cm["first_seen"]].date().isoformat(),
                "last_seen": row[cm["last_seen"]].date().isoformat(),
                "countries": row[cm["countries"]],
                "placements": row[cm["placements"]],
                "dimensions": row[cm["dimensions"]],
                "video_duration": row[cm["video_duration"]],
            }
        )
    return records


def finalize_with_llm(records: list[dict], pull_date: str, model: str) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[FINALIZE_TOOL],
        tool_choice={"type": "tool", "name": "finalize_selection"},
        messages=[{"role": "user", "content": build_user_message(records, pull_date)}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "finalize_selection":
            return block.input["selections"]
    raise RuntimeError("Claude did not return a finalize_selection tool call.")


def fallback_rationale(records: list[dict]) -> list[dict]:
    """Used when --no-llm is set or no API key is configured."""
    out = []
    for r in records:
        rationale = (
            f"{'Proven' if r['tier'] == 'proven' else 'Emerging'}: running "
            f"{r['duration_days']} days (first seen {r['first_seen']}, last seen "
            f"{r['last_seen']}) with {r['impression_share_pct']}% impression share "
            f"(within {r['networks']}) across {r['countries']}."
        )
        out.append(
            {
                "app": r["app"],
                "networks": r["networks"],
                "creative_link": r["creative_link"],
                "tier": r["tier"],
                "tier_corrected": False,
                "duplicate_flag": "",
                "rationale": rationale,
            }
        )
    return out


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def write_report_manifest(final: list[dict], out_dir: Path) -> Path:
    """Assigns each shortlisted creative a filename for its qualitative
    report and writes a manifest so Agent 2 can match report files back to
    the right creative — reports come back one-per-creative from the
    third-party analysis tool, so there's no reliable way to infer which
    report belongs to which creative except by filename convention."""
    for i, r in enumerate(final, 1):
        r["report_filename"] = f"{i:02d}_{r['tier']}_{slugify(r['app'])}.txt"

    manifest_path = out_dir / "report_manifest.csv"
    with manifest_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "report_filename", "tier", "app", "networks", "creative_link"])
        for i, r in enumerate(final, 1):
            writer.writerow(
                [i, r["report_filename"], r["tier"], r["app"], r["networks"], r["creative_link"]]
            )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 1 — Selector")
    parser.add_argument("--input", required=True, help="Path to Sensor Tower CSV export")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--pull-date", default=None, help="ISO date; defaults to max(Last Seen)")
    parser.add_argument("--model", default=config.DEFAULT_MODEL)
    parser.add_argument(
        "--no-llm", action="store_true", help="Skip the Claude sanity-check/rationale step"
    )
    args = parser.parse_args()

    df = load_data(args.input)
    filtered = filter_rows(df)
    if filtered.empty:
        print("No rows survived filtering — nothing to select.", file=sys.stderr)
        sys.exit(1)

    scored = score_rows(filtered)
    shortlist = select_shortlist(scored)
    records = shortlist_to_records(shortlist)

    pull_date = args.pull_date or df[config.COLUMN_MAP["last_seen"]].max().date().isoformat()

    use_llm = not args.no_llm and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not args.no_llm and not use_llm:
        print(
            "ANTHROPIC_API_KEY not set — falling back to templated rationale "
            "(pass --no-llm to silence this).",
            file=sys.stderr,
        )
    final = finalize_with_llm(records, pull_date, args.model) if use_llm else fallback_rationale(
        records
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = write_report_manifest(final, out_dir)
    out_json = out_dir / "agent1_shortlist.json"
    out_json.write_text(json.dumps(final, indent=2))

    print(f"\nWrote {len(final)} selections to {out_json}")
    print(f"Wrote report filename manifest to {manifest_path}\n")
    for i, r in enumerate(final, 1):
        print(f"{i}. [{r['tier']}] {r['app']} ({r.get('networks', 'n/a')})")
        print(f"   {r['creative_link']}")
        print(f"   {r['rationale']}")
        if r.get("duplicate_flag"):
            print(f"   ⚠ duplicate flag: {r['duplicate_flag']}")
        print(f"   -> save its report as: {r['report_filename']}")
        print()
    print(
        f"Next: run the 10 links above through your creative-analysis tool, save each "
        f"report as a .txt file named exactly as shown above into one folder (e.g. "
        f"{out_dir}/reports/), then run Agent 2 pointed at that folder."
    )


if __name__ == "__main__":
    main()
