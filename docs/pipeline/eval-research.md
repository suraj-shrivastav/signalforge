# Research eval

`scripts/eval_research.py` replays research on accepted cards and measures how deep and reliable it is. It is a dry run: it calls `_process_card` and never writes to the database (the gateway session never commits and is rolled back after each card, so no `llm_calls` rows are kept).

## Run

Needs `DATABASE_URL` and the provider keys the worker uses (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_*`; `TAVILY_API_KEY` optional, without it only primary sources are used). With any of them missing it exits with a message. Cost is about 30 x $0.005 for 30 cards.

```
python scripts/eval_research.py --limit 30 --label before --out docs/pipeline/eval-research-before.json
```

Run it on the unchanged pipeline with `--label before`, and again after the changes with `--label after`.

## Read the table

One row per card (newest accepted first, any research status): documents, whether the primary was read as a full paper (`full`), claims, claims containing a digit (`num`), status, failure class, cost, LLM calls and extraction failures (`xfail`).

Totals:

- `researched_share`: cards reaching `researched`.
- `mean_claims`: claims per card.
- `numeric_share_of_researched`: researched cards with at least one numeric claim.
- `full_text_share_arxiv`: arXiv-hosted cards whose primary was read as full text (URL under `/html/` or ar5iv); an approximation.
- `mean_cost_usd`, `mean_calls`: cost can be 0 when a model has no configured price, so trust calls then.
- `extraction_success_rate`: documents extracted over documents attempted.
- `failure_classes`: counts by failure class prefix.
