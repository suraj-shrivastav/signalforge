# Article quality review, 2026-11-15

Two reviewer agents read six published articles as readers would and checked each one against its primary source. This file records what they found. It is the spec for Milestone 2, "Readable and honest articles".

## Method

Each reviewer:

- fetched the article from the public API (`GET /articles/{slug}`);
- read its title, dek and every section in order;
- opened the primary source and spot-checked 3 to 5 claims;
- checked whether the secondary sources were relevant;
- scored seven criteria from 1 to 5: hook, clarity, structure, depth, accuracy, length and takeaway.

## Scores

Each article is scored hook, clarity, structure, depth, accuracy, length and takeaway, in that order.

| Article | Words | Band | Scores | Worst defect |
|---|---|---|---|---|
| Single-Camera Occlusion Detection (arXiv 2611.06899) | 283 | 500-800 | 2/1/2/1/3/1/2 | The whole "The problem" section is one sentence that opens "This detector dependence...", and nothing before it says what "this" is. "0.3 ms" is the cost of the score alone; the full pipeline takes 6.3 s per frame and the authors make no real-time claim. "Up to 34%" is the gap in one example frame. |
| PEARL (arXiv 2611.05358) | 485 | 500-800 | 2/2/3/2/4/2/3 | The dek is a sentence taken from the body. "The authors note... not a guarantee" is not in the paper. The narrow-trigger results are left out. |
| Altermagnetism (SLAC release) | 426 | 700-1000 | 2/2/1/1/3/2/2 | It uses the scientist's quotes as its own sentences, without quotation marks. A source is a Belgian arts academy page. The structure is backwards: the experiment comes before the concept. |
| Geometric constraints in online RL (GSBR) | 527 | 500-800 | 2/2/3/1/4/3/2 | 72% of the text is copied verbatim from the paper. It never says all results come from simulation. On LIBERO, the most realistic benchmark, the method only ties the baselines, and the article leaves those numbers out. |
| Liquid AI LFM3 | 556 | 700-1000 | 3/2/2/2/3/2/2 | "Beats larger models" is selective: Qwen3.5-9B wins on GPQA, SWE-bench and MCP-Atlas. The vendor's own "not recommended for agentic coding" is left out. A section opens "This layer composition..." after the sentence it refers to was deleted. |
| KierstonBench | 334 | 500-800 | 1/2/2/1/2/1/2 | The headline ("only frontier models can reliably investigate") contradicts the paper. No model solved any of the five suspect tasks, and the wording comes from an AI summary on Hugging Face, not from the paper. |

The numbers the articles quote were mostly correct. The damage comes from what is left out, from text that no longer reads in order, and from titles that claim more than the source.

## Defects and their causes in the code

The code references are to main at d2282f5.

| # | Defect | Cause |
|---|---|---|
| D1 | Sentences that point back at nothing ("This...", "It..."), one-sentence sections, and deks taken from the body. | `src/signalforge/auto_review.py` `decide()` deletes every flagged sentence with no repair. `_lead_sentence` copies the first unflagged body sentence into the dek. Nothing checks the text after the deletions. |
| D2 | Titles overclaim: "only", "reliably", "solve", "beats", "reshape". | The only title check is for numbers that are missing from the claims (`src/signalforge/stages/draft.py`, `sentence_problems(title, ...)`). |
| D3 | All six articles are shorter than their template band. | `ReviewPolicy.min_words` is 250 for every template. `decide()` filters length failures out of `publish_gate` (`if not f.startswith("length")`). |
| D4 | Every article says "An editor reviewed and approved this article before it was published", even when the automated review approved it. | `publish_approved` always uses `settings.publish_process_note` (`apps/api/routes/articles.py`). |
| D5 | Thin research: 6 to 15 claims per article, no motivation, prior work, worked example or limitations. | Research extracts few claims, and there is no coverage check. |
| D6 | No context: undefined jargon, no lede, the text reads as a patchwork of source sentences. | The writer prompt says "No uncited transitions, opinions or background". |
| D7 | Key facts are dropped. Sentences copied straight from an abstract are marked `uncertain`. | The claim judge sees too narrow an evidence window for claims made at the level of the abstract. |
| D8 | About 9 of 15 secondary sources are unused, irrelevant or duplicates. Quotes are not attributed. | There is no check that a source is relevant or cited, and no check for text copied from a source. |
| D9 | Visuals carry no information. The figure only repeats the section headings, `headline` is null or a fragment such as "Reveals Only", and tables show raw LaTeX or "NN". | The figure is built from the headings. Tables are copied with their markup. |

## Requirements for Milestone 2a (this plan)

- **R1 (D1).** Rewrite flagged sentences instead of deleting them. A draft that still reads badly goes back for a redraft; it is never published.
- **R2 (D1).** The dek is never replaced by a body sentence.
- **R3 (D2).** A title may not use a strong word (only, first, best, beats, outperforms, solves, reliably, always, never, breaks, eliminates, replaces, transforms, revolutionizes, reshapes, guarantees, proves, conclusive, unprecedented, breakthrough) unless a claim the article cites uses it.
- **R4 (D3).** The automated review enforces each template's minimum word count. The floor is a setting, chosen from a measured baseline.
- **R5 (D4).** The process note tells readers the truth about who approved the article. Articles already published are corrected.
- **R6.** Measure before and after, with the same checks the review applies.

D5 to D9 go to Milestone 2b, which gets its own plan after 2a is measured.
