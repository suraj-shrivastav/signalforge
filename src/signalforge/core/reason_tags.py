"""Editor decision reason tags. Single source; the web client mirrors this list in api.ts."""

REASON_TAGS: tuple[str, ...] = (
    "off_niche",
    "too_incremental",
    "duplicate",
    "already_covered",
    "low_quality_source",
    "great_angle",
    "timely",
    "evergreen",
    "needs_more_evidence",
)
