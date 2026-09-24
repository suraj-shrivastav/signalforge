"""Pipeline stages. Each depends on protocols only, never on a concrete provider.

Order: ingest, cluster, filter, topic_intel, [editor review 1], research, write,
verify, seo, [editor review 2], publish, analytics.
"""
