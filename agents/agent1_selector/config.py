"""Tunable settings for Agent 1 (Selector).

Adjust COLUMN_MAP if your Sensor Tower export uses different header names —
nothing else in selector.py needs to change.
"""

COLUMN_MAP = {
    # This export has no separate studio/publisher column — "Advertiser App
    # Name" is the closest thing to both "advertiser" and "app", so both
    # keys point at it. The per-advertiser diversity cap groups on this.
    "advertiser": "Advertiser App Name",
    "app": "Advertiser App Name",
    "creative_link": "Creative URL",
    "networks": "Networks",
    "duration": "Duration",
    "first_seen": "First Seen",
    "last_seen": "Last Seen",
    "impression_share": "Impression Share",
    "countries": "Countries",
    "type": "Type",
    "format": "Format",
    "ad_objectives": "Ad Objectives",
    "placements": "Placements",
    "dimensions": "Dimensions",
    "video_duration": "Video Duration",
}

# Case-insensitive substring match against the Ad Objectives column.
INSTALL_OBJECTIVE_KEYWORDS = ["install"]

# Case-insensitive substring match against the Type column. The real export
# only contains "playable" (no "video" rows at all) — this pipeline is for
# playable-ad research, so that's exactly what we want.
AD_TYPE_KEYWORDS = ["playable"]

# Final shortlist composition.
TOP_PROVEN = 6
TOP_EMERGING = 4

# No single advertiser, and no single network, should dominate the shortlist.
MAX_PER_ADVERTISER = 3
MAX_PER_NETWORK = 4

# Weights for the two composite scores (must each sum to 1.0).
PROVEN_WEIGHTS = {"impression_share": 0.6, "duration": 0.4}
EMERGING_WEIGHTS = {"impression_share": 0.65, "recency": 0.35}

DEFAULT_MODEL = "claude-sonnet-5"
