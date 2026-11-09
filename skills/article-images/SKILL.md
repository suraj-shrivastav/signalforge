---
name: article-images
description: Create the two images (cover and inline figure) for a published SignalForge article from its verified facts, upload them to Supabase and attach them. Use after an article is published and has no images.
---

# Article images

Every published article gets exactly two images: a **cover** and an **inline figure**.
You never draw. You fill in two small JSON specs. The script checks them against the
article, draws the SVG, uploads it and attaches it. The same spec always gives the same
image. Different articles give different images because the look is derived from the slug.

## Unattended default: `auto`

The scheduler runs `articleimg.py auto` every 15 minutes. It gives every published article
without images a **title-card** cover (the title, nothing else) and a **layers** figure built
from the article's first three section headings. It uses no model, picks no number and so
never skips an article, including articles with no numbers. Run it by hand with
`python scripts/articleimg.py auto --dry-run DIR` to preview.

The model workflow below is the optional upgrade for a fact-led image (one verified number).
It is no longer required for an article to have images.

## Rules that never bend

1. Use only numbers, names and facts that appear in the article's title, dek or verified claims. The script rejects any number it cannot find there.
2. The `waveform` template is only for audio, speech or signal articles; the validator rejects it elsewhere.
3. Two different templates: the cover and the figure must not use the same template.
4. No faces, logos, brand marks, photos, emoji or invented statistics.
5. Do not edit the script. Do not write SVG. Do not change colours, fonts or sizes.
6. Text limits are hard: label 28 characters, figure 8, caption 34, alt 140, layer item 30, block name 14, block text 8, architecture box 14, bar name 14, bar text 8.
7. If the validator prints `INVALID`, fix the listed problem and run it again. Do not publish around it.

## Steps

1. **Read the article.** `GET $API_BASE_URL/articles/<slug>` returns title, dek, claims (each with `status`) and sources. Use only claims whose status is `verified` or `supported`.
2. **Find the headline fact for the cover.** The single most important number in the title or dek, with the unit that makes it meaningful (for example `5.06%` with `word error rate`, `$118M` with `raised from BlackRock`, `390K` with `hours of public audio`). Write it exactly as the article writes it.
3. **Choose the cover template** with the table below. Take the first row that matches.
4. **Choose a different figure template** for the inline image. It shows a second aspect of the article (a different number, a comparison, the structure, a count). Use the table again, skipping the cover's template.
5. **Fill each spec** using the form for its template (see `references/templates.md`). Copy the shape from `examples/`.
6. **Write `alt`** for each image: one plain sentence saying what the image shows and the fact it carries. Under 140 characters.
7. **Publish both** with one command:

```
python3 scripts/articleimg.py publish --slug <slug> --cover cover.json --figure figure.json
```

Use `--dry-run DIR` first to render into a folder without uploading. Needs only `API_BASE_URL` and `EDITOR_API_KEY` (the agent key works). The script sends the rendered SVGs to `POST /editor/articles/{slug}/images/upload`; the API holds the storage key and stores them. Never print the keys.

## Template choice (first match wins)

| If the article is mainly about | Template | Fields to fill |
|---|---|---|
| Three to six named things with a number of the same kind (scores, latency, price, size), one of them the article's subject | `bar-chart` | `values.bars` (3 to 6), optional `caption` |
| Two named things compared, each with a number of the same kind (parameters, price, score, size) | `compare-blocks` | `values.a`, `values.b` |
| An amount of money, users, data or time raised, trained or spent | `figure-ripples` | `figure`, `caption` |
| A rate, score, speed or accuracy of something audio, speech, time series or signal | `waveform` | `figure`, `caption` |
| A count of things that connect: languages, partners, backers, integrations, regions (3 to 9) | `constellation` | `figure`, `caption`, `values.count` |
| A benchmark, dataset, test set or evaluation with a size | `spectrogram` | `figure` (a short word or number), `caption` |
| How something works or is built, as exactly three steps or components | `layers` | `values.items` (3) |
| How data moves through a system: 3 to 5 named components in order (pipeline, model stages, request path) | `architecture` | `values.boxes` (3 to 5), optional `caption` |

For the inline figure, prefer a template that shows structure or comparison if the cover shows a single number, and the reverse.

## The spec

```
{
  "role": "cover" | "figure",
  "template": "<one of the eight>",
  "label": "TOPIC IN FEW WORDS",         // at most 28 characters, shown in capitals
  "figure": "5.06%",                     // hero text, at most 8 characters (not for compare-blocks, layers, architecture, bar-chart)
  "caption": "word error rate",          // at most 34 characters (not for compare-blocks, layers, architecture, bar-chart)
  "alt": "One sentence describing the image and its fact",
  "values": { }                          // only for compare-blocks, constellation, layers, architecture, bar-chart
}
```

`compare-blocks` values: `{"a": {"value": 2000, "text": "2B", "name": "parameters"}, "b": {"value": 470, "text": "470M", "name": "TurboCTC"}}`. `value` sets the block size, so use comparable plain numbers (2000 and 470 in millions). Both blocks must measure the same thing.

`constellation` values: `{"count": 7}`. `layers` values: `{"items": ["step one", "step two", "step three"]}`.

`bar-chart` values: `{"bars": [{"name": "Granite", "value": 5.06, "text": "5.06%"}, ...]}`: 3 to 6 bars, `name` 14 characters at most, `text` 8 at most. `value` must equal the first number in `text`: it sets the bar length on one scale from zero, so every bar must measure the same thing in the same unit. List the article's own subject first; its bar is the dark one. Use the caption for the direction (`lower is better`). It takes an optional `caption` and no `figure`.

`architecture` values: `{"boxes": ["Audio in", "Encoder", "Decoder", "Text out"]}`: 3 to 5 component names, 14 characters at most each, in the order the data flows. The script draws one arrow from each box to the next. It takes an optional `caption` and no `figure`. Use names the article itself uses; do not add a component the article does not describe.

## Check before publishing

- The figure and every number in the captions appear in the article text.
- The cover and the figure use different templates and tell different things.
- `label` names the topic, not the headline. `caption` says what the number measures.
- If no fact in the article fits any row of the table, use `figure-ripples` with the most important number and its unit. If the article has no number at all, stop and report it; do not invent one.
