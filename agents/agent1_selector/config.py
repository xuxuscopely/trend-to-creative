"""Tunable settings for Agent 1 (Selector).

Adjust COLUMN_MAP if your Sensor Tower export uses different header names —
nothing else in selector.py needs to change.
"""

COLUMN_MAP = {
    "advertiser": "Advertiser",
    "app": "App",
    "creative_link": "Creative Link",
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

# Case-insensitive substring match against Format (falls back to Type if
# Format doesn't contain any of these).
VIDEO_FORMAT_KEYWORDS = ["video"]

# Final shortlist composition.
TOP_PROVEN = 6
TOP_EMERGING = 4

# No single advertiser should dominate the shortlist.
MAX_PER_ADVERTISER = 3

# Weights for the two composite scores (must each sum to 1.0).
PROVEN_WEIGHTS = {"impression_share": 0.6, "duration": 0.4}
EMERGING_WEIGHTS = {"impression_share": 0.65, "recency": 0.35}

DEFAULT_MODEL = "claude-sonnet-5"
