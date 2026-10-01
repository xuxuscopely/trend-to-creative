SYSTEM_PROMPT = """You are the Selector agent in a creative-trend-research pipeline for a \
mobile game studio. A deterministic scoring step has already narrowed a Sensor Tower \
export down to a shortlist of install-objective video ad creatives, split into two tiers:

- "proven": long-running creatives with sustained high impression share (established winners)
- "emerging": recently-first-seen creatives already accumulating meaningful impression share \
(early signal, not yet fully saturated)

Your job is NOT to re-rank by gut feel. For each shortlisted creative:

1. Sanity-check the tier label against its own metrics (First Seen, Last Seen, Duration, \
Impression Share). If a creative is mislabeled (e.g. an "emerging" pick that has been running \
for months), say so in the rationale and correct the tier.
2. Flag likely duplicates — two entries from the same advertiser that look like the same \
creative concept (same dimensions/placements/duration, near-identical first/last seen dates) \
should not both occupy a slot. Note this in the rationale rather than silently dropping one.
3. Write a short, concrete rationale (1-2 sentences) per creative that cites its actual numbers \
(e.g. "Running 54 days across 12 countries with a 0.8% impression share — one of the longest \
sustained creatives in this pull" or "First seen 6 days ago but already at 0.3% impression \
share, climbing fast"). Do not invent metrics that weren't provided.

Do not change which creatives are selected — only confirm/correct tier labels, flag duplicates, \
and write rationale. Output must match the provided tool schema exactly."""


def build_user_message(shortlist: list[dict], pull_date: str) -> str:
    import json

    return (
        f"Sensor Tower data pull date: {pull_date}\n\n"
        f"Shortlisted creatives (deterministic scoring already applied):\n\n"
        f"{json.dumps(shortlist, indent=2, default=str)}"
    )


FINALIZE_TOOL = {
    "name": "finalize_selection",
    "description": "Return the sanity-checked, annotated final shortlist.",
    "input_schema": {
        "type": "object",
        "properties": {
            "selections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "app": {"type": "string"},
                        "advertiser": {"type": "string"},
                        "creative_link": {"type": "string"},
                        "tier": {"type": "string", "enum": ["proven", "emerging"]},
                        "tier_corrected": {
                            "type": "boolean",
                            "description": "true if you changed the tier from what was passed in",
                        },
                        "duplicate_flag": {
                            "type": "string",
                            "description": (
                                "Empty string if not a duplicate, otherwise note which "
                                "other creative in this shortlist it duplicates and why."
                            ),
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "app",
                        "advertiser",
                        "creative_link",
                        "tier",
                        "tier_corrected",
                        "duplicate_flag",
                        "rationale",
                    ],
                },
            }
        },
        "required": ["selections"],
    },
}
