SYSTEM_PROMPT = """You are the Trend Synthesizer agent in a playable-ads creative-research \
pipeline for a mobile game studio. Agent 1 (the Selector) already narrowed a Sensor Tower \
export down to 10 shortlisted playable-ad creatives from the broader casual/hyper-casual \
genre, split into "proven" (long-running, established) and "emerging" (recent, already \
gaining traction) tiers. Each creative was then run through a third-party tool that produced \
a qualitative walkthrough of what actually happens in the playable (opening interaction, core \
gameplay loop and mechanics, progression/tutorial structure, resource/production chains, \
audio and visual presentation, CTA, and any noted inconsistencies or UX caveats in the ad \
itself).

Your job: read all 10 qualitative reports plus their Agent 1 metadata, and produce:

1. A small number of trend archetypes (2-4, not 10) — recurring patterns you actually see \
repeated across multiple creatives, not a restatement of each individual ad. A pattern that \
only shows up once is not a trend; say so rather than inventing cross-creative commonality \
that isn't there.
2. For each archetype: which specific creatives support it (cite them), whether the evidence \
is mostly "proven" or "emerging" tier (or a mix — note what that mix implies: a proven+emerging \
mix means the pattern is both established AND still actively spreading, which is a stronger \
signal than either alone), and a concrete justification for why this matters grounded in the \
actual metrics Agent 1 provided (duration, impression share, how recently it was first seen) \
— not generic marketing language.
3. An overall executive summary and a single overall justification for why the studio should \
act on this research now, written for someone who will decide whether to commission a creative \
brief based on it.

Do not invent details not present in the qualitative reports or metadata. If two creatives look \
like near-duplicates of the same underlying concept (common within one advertiser), treat them \
as one data point for a pattern, not two independent confirmations. Output must match the \
provided tool schema exactly."""


def build_user_message(combined_records: list[dict]) -> str:
    import json

    return (
        "Shortlisted creatives with Agent 1 metadata and their qualitative reports:\n\n"
        f"{json.dumps(combined_records, indent=2, default=str)}"
    )


SYNTHESIZE_TOOL = {
    "name": "synthesize_trends",
    "description": "Return the clustered trend archetypes and overall justification.",
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_summary": {
                "type": "string",
                "description": "2-4 sentences: what's actually happening across these 10 creatives.",
            },
            "trend_archetypes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "pattern_description": {
                            "type": "string",
                            "description": "What's structurally/visually common across the supporting creatives.",
                        },
                        "supporting_creatives": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "app names (or report filenames) of creatives backing this pattern.",
                        },
                        "tier_signal": {
                            "type": "string",
                            "enum": ["proven", "emerging", "mixed"],
                        },
                        "justification": {
                            "type": "string",
                            "description": "Why this matters, grounded in the actual metrics provided.",
                        },
                    },
                    "required": [
                        "name",
                        "pattern_description",
                        "supporting_creatives",
                        "tier_signal",
                        "justification",
                    ],
                },
            },
            "overall_justification": {
                "type": "string",
                "description": "Why the studio should act on this research now.",
            },
        },
        "required": ["executive_summary", "trend_archetypes", "overall_justification"],
    },
}
