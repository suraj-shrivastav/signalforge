# SEO and GEO strategy for SignalForge articles

Date: 2026-10-21. Written for the SignalForge team, to decide what the publishing step must build so articles get indexed, ranked and cited by both search engines and AI agents.

Method: web search for the landscape, then reading primary sources (Google Search Central, the GEO paper on arXiv, OpenAI, Anthropic and Perplexity crawler docs, llmstxt.org, IndexNow, schema.org, web.dev). Search results were mostly vendor blogs, so every claim below carries a confidence label.

- **Verified**: read on the primary source page.
- **Paper**: read in the GEO paper itself, with the limits noted.
- **Vendor claim**: repeated by SEO blogs, not checked against a primary source. Do not build on these.

## 1. The short answer

1. **No technique guarantees a higher rank than other publishers, and Google says so.** For Google's AI Overviews and AI Mode there are "no additional requirements" and "no special schema.org structured data" to add. A page needs to be indexed and eligible to show with a snippet. Ranking then comes from the same people-first, original, trustworthy content it always did. Anyone selling a secret GEO trick is selling a vendor claim.
2. **What does move citations, with evidence:** adding concrete statistics, expert quotations and cited sources to a page raised its visibility in generative answers by roughly 30 to 40 percent in the GEO paper, while keyword stuffing lowered it. This is one academic study on a simplified engine plus a small Perplexity test, so treat it as direction, not a guarantee.
3. **Our structural advantage is real and rare.** Every SignalForge claim already links to a stored source and an exact quote. That is the shape both search engines (trust, original information) and AI engines (extractable facts with attribution) reward. Most publishers cannot show it.
4. **Our structural risk is also real.** Google warns about "mainly summarizing what others have to say without adding much value" and about scaled AI content without human review. A research-then-summarize pipeline sits close to that line. The human review step, a real byline, honest disclosure, and original synthesis are what keep us on the right side.
5. **Plumbing is the cheapest win.** Today the public site has an article page and an RSS feed, but no page metadata, no structured data, no sitemap and no robots policy. Those are table stakes and mostly one PR.

## 2. What search engines require and reward (Google, verified)

**Eligibility and AI features** (Google, AI features and your website, updated 2025-12-10)
- To appear in AI Overviews or AI Mode, "a page must be indexed and eligible to be shown in Google Search with a snippet." Indexing and serving "isn't guaranteed."
- No new files, AI text files or special markup are needed. Recommended basics: crawling allowed in robots.txt and by the CDN or host, internal links, a good page experience, important content in text form, and structured data that "matches the visible text on the page."
- AI Overviews "are only shown when our systems determine that it is additive to classic Search."
- Traffic from AI features is counted in Search Console under the "Web" search type. There is no separate AI report.

**People-first content** (Google, creating helpful content, updated 2026-10-05)
- The self-assessment questions: does the title describe the content without exaggerating, is it clear who wrote it, is the use of automation or AI clear, does it provide "original information, reporting, research, or analysis," is it written or reviewed by someone who knows the topic.
- "Of these aspects, trust is most important." E-E-A-T "isn't a specific ranking factor" but the signals feed the systems that are.
- Warning signs: mainly summarizing others without adding value, extensive automation across many topics.

**AI-generated content** (Google, using generative AI content, updated 2026-10-01)
- Allowed: generative AI "to add structure to original content" and for research.
- Spam: generating "many pages without adding value" can violate the scaled content abuse policy.
- "It is critical to manually factcheck and review all AI-generated content for accuracy and trustworthiness before publishing," including titles, meta descriptions, structured data and image alt text.
- Fabricated author profiles (AI headshots, invented names or credentials) are called deception.
- Disclosure is not required for Search, but "AI or automation disclosures are useful" where a reader might ask how it was made.

**Titles and headings** (title links, updated 2025-12-10)
- No length limit, but titles are truncated to device width. Each page needs a distinct title that describes it. Put the title text in the first visible `<h1>`. Avoid boilerplate and keyword stuffing.

**Structured data** (Article, updated 2026-09-08, and structured data policies, updated 2026-07-10)
- Allowed types: `Article`, `NewsArticle`, `BlogPosting`. "There are no required properties." Recommended: `author` (with `name` and `url`), `datePublished`, `dateModified`, `headline`, `image`. Dates in ISO 8601 with timezone. Include every author as a separate entry.
- Images: several high-resolution images, at least 50,000 pixels, in 16x9, 4x3 and 1x1 ratios, crawlable and indexable.
- JSON-LD is the recommended format on the policies page. Markup must describe visible content and be a true representation of it. Misleading markup can cost rich-result eligibility (it does not change web ranking).
- Top Stories has no markup requirement.

**Sitemaps** (build a sitemap, updated 2026-07-08)
- 50,000 URLs or 50 MB per file. Absolute URLs, UTF-8.
- `lastmod` is used only if it is "consistently and verifiably" accurate and reflects a significant change, not a copyright-year edit. Google ignores `priority` and `changefreq`. A sitemap is "merely a hint."
- News sitemap: only URLs for articles from the last two days, at most 1,000 `news:news` entries, with `news:publication` (name must match Google News), `news:language`, `news:publication_date` and `news:title` (without author or publication name). Google says either a news sitemap or plain sitemap is fine; it is not required for Top Stories.

**Discover** (updated 2026-03-09)
- Eligible if indexed and policy-compliant. No special tags needed. Wants images at least 1200 px wide (more than 300,000 pixels), via `max-image-preview:large` and a schema or `og:image` image. No generic logo images, no clickbait or sensationalism.

**Preview controls** (robots meta tag, updated 2026-03-24)
- `nosnippet` also "prevents the content from being used as a direct input for AI Overviews and AI Mode." `max-snippet:0` is the same. `max-snippet:-1` lets Google choose. `max-image-preview:large` allows large previews. `data-nosnippet` hides parts of a page. The more restrictive rule wins, and all rules are ignored if robots.txt blocks the URL. `noarchive` is obsolete.

**Core Web Vitals** (web.dev, last updated 2024-10-31)
- Good: LCP at most 2.5 s, INP at most 200 ms, CLS at most 0.1, at the 75th percentile of loads. Google lists page experience as something its ranking systems reward.

## 3. How AI engines choose what to cite (GEO)

### 3.1 The one piece of real research

"GEO: Generative Engine Optimization" (Aggarwal, Murahari, Rajpurohit, Kalyan, Narasimhan, Deshpande; arXiv 2311.09735, KDD 2024). Paper, from Table 1 as printed:

| Method | Visibility score (position-adjusted word count) | Change vs 19.3 baseline |
| --- | --- | --- |
| Quotation addition | 27.2 | +41 percent |
| Statistics addition | 25.2 | +31 percent |
| Fluency optimization | 24.7 | +28 percent |
| Cite sources | 24.6 | +27 percent |
| Technical terms | 22.7 | +18 percent |
| Authoritative tone | 21.3 | +10 percent |
| Easy to understand | 22.0 | +14 percent |
| Unique words | 20.5 | +6 percent |
| **Keyword stuffing** | **17.7** | **-8 percent** |

Percent changes are my arithmetic from the printed scores. The paper states the best methods improve "by 41% and 28% on Position-Adjusted Word Count and Subjective Impression," and that cite sources, quotation addition and statistics addition gave "30-40%" on the first metric.

Limits you should hold in mind:
- The test engine was the authors' own pipeline (gpt-3.5-turbo answering from the top 5 Google results), plus a smaller test on Perplexity.ai. It is not Google AI Overviews or ChatGPT search.
- The paper itself says "the efficacy of these strategies varies across domains."
- The subjective-impression metric is itself model-judged, and the paper notes these functions are "not well-defined yet for generative engines."
- A secondary reading says lower-ranked pages gained most (rank 5 up about 115 percent, rank 1 down about 30 percent). I could not confirm that from the verbatim text, so verify Table 2 of the paper before relying on it.

### 3.2 Vendor claims, not verified

Search results repeatedly cited share-of-citation figures (for example Wikipedia at 47.9 percent of ChatGPT's top factual sources, Reddit at 46.7 percent of Perplexity's top sources, Reddit at about 21 percent of AI Overview citations). These come from different SEO vendor studies with different methods. They are not comparable and I did not verify any of them. The only safe reading is that AI engines lean on a few high-authority, high-density sources, so being a clearly attributed, fact-dense source matters.

### 3.3 AI crawlers (verified from each vendor's page)

Each vendor separates crawlers by purpose. The practical split is "allow the ones that put you in answers, decide separately about training."

| Vendor | Crawler | Purpose | robots.txt |
| --- | --- | --- | --- |
| OpenAI | `OAI-SearchBot` | Surfaces sites in ChatGPT search. Opting out means you will not be shown in ChatGPT search answers. OpenAI recommends allowing it. | Honors it. Changes take about 24 hours. |
| OpenAI | `GPTBot` | Crawls content that may train foundation models | Honors it |
| OpenAI | `ChatGPT-User` | User-triggered fetches inside ChatGPT. Not used for automatic crawling and "not used to determine whether content may appear in Search." | "robots.txt rules may not apply" |
| Perplexity | `PerplexityBot` | Surfaces and links sites in Perplexity search. Not used for foundation model training. Recommended allowed. | Honors it |
| Perplexity | `Perplexity-User` | User-triggered fetches | "generally ignores robots.txt" |
| Anthropic | `ClaudeBot` | Collects content that may train models | Honors it |
| Anthropic | `Claude-SearchBot` | Indexes content to improve search results. Disabling "may reduce your site's visibility." | Honors it |
| Anthropic | `Claude-User` | User-directed fetches. Disabling "may reduce your site's visibility for user-directed web search." | Honors it |
| Google | `Googlebot` for Search and AI features, `Google-Extended` for "AI training and grounding in some of Google's other systems" | See section 2 | Control for Search is robots.txt for Googlebot |

Notes:
- All three vendors publish IP ranges and recommend allowing both the user agent and the IP range, and several note firewalls and CDNs can block a bot that robots.txt allows. Check the CDN settings when we deploy.
- Anthropic's names and guidance are from a support page dated 2026-04-07. Vendors rename bots, so re-check before shipping the robots.txt.
- The Google-Extended detail beyond one sentence was not on the pages I read, so I have not described exactly what it does.

### 3.4 `llms.txt` (verified as a proposal, not a standard)

llmstxt.org describes `/llms.txt` as "a proposal" (Jeremy Howard, September 2024): a Markdown file with an H1, a short summary and link lists for agents. It "complements robots.txt." The page says OpenAI, Anthropic and Google publish one for their own developer docs, but it does not claim any AI company reads it for crawling or ranking. The OpenAI and Anthropic crawler pages I read do not mention it. Google states no such file is needed for its AI features. Verdict: cheap to publish (an hour of work), unproven benefit, low priority.

### 3.5 Fast indexing (IndexNow, verified mechanics)

- IndexNow lets a site push changed URLs. A key file `{key}.txt` at the host root proves ownership. A single URL is a GET to `/indexnow?url=...&key=...`. A batch is a POST with `host`, `key` and `urlList` of up to 10,000 URLs. Responses: 200 accepted, 202 key validation pending, 400 bad format, 403 bad key, 422 mismatch, 429 too many requests.
- Participating engines share submissions. The protocol authors are Seznam, Yandex and Microsoft. The pages I read did not list Bing, Naver or Yep explicitly, and did not mention Google at all, so I cannot confirm Google uses it. Treat it as a way to reach Bing-family and Yandex-family indexes quickly, which matters if ChatGPT search leans on Bing (that dependency is a vendor claim, not verified here).
- For Google, rely on an accurate sitemap `lastmod`, internal links and Search Console submission.

## 4. The blend: rules for every SignalForge article

Each rule says why it exists and what in our pipeline provides it.

**Search (SEO)**
1. **One distinct, descriptive title and a matching `<h1>`.** The title states the specific event ("Granite Speech 5.0 adds keyword biasing up to 2,000 terms"), not a teaser. No clickbait (Google and Discover both penalize it). The writer already produces a title; the publish step should store a separate `seo_title` and a plain-language `meta_description`.
2. **Real byline and an honest process note.** Google asks who wrote it and whether AI use is clear, and calls invented authors deception. Use the real editor as the author, and add a short "How this was made" line stating that sources were collected and checked automatically and a named editor reviewed it. This is our strongest answer to the scaled-AI-content policy.
3. **Original value beyond summary.** The review step is where the editor adds a take, a comparison, or data the sources lack. Without it we sit in the "mainly summarizing" warning. The product should make an "editor's analysis" field a first-class, visible part of the article.
4. **Stable URLs, canonical tag, `datePublished` and a truthful `dateModified`** (only when the article materially changes). `lastmod` that lies gets ignored.
5. **Article structured data in JSON-LD** matching the visible page: `NewsArticle` (or `Article`) with `headline`, `image`, `datePublished`, `dateModified` and `author` with name and url. Google requires nothing, but it helps entity understanding and must match visible text.
6. **Images**: a 16x9 cover at least 1200 px wide, plus 4x3 and 1x1 crops, with `max-image-preview:large`. Never a logo.
7. **Sitemap with accurate `lastmod`, a news sitemap for the last two days, and an RSS feed (already built).**
8. **Speed**: server-render the article, keep it under LCP 2.5 s, INP 200 ms, CLS 0.1.

**AI engines (GEO)**
9. **Answer first.** Open with a two or three sentence summary that states the finding with its key numbers, then the detail. AI engines quote the top of a section, and readers skim it too. Generate it from the verified claims, not freehand.
10. **Fact density with attribution** (the paper's strongest levers): concrete numbers, direct quotations from the source, and a named source for each fact, in plain sentences. We already store the quote and source per claim, so the structured claim list can be rendered as a visible "Key facts" block with links.
11. **One claim per sentence, one idea per paragraph, descriptive `<h2>` headings phrased the way people ask** ("What changed in Granite Speech 5.0?"). Easy to lift and quote.
12. **Plain text and plain HTML.** Important content must be real text, not images or script-only widgets, so crawlers that do not run scripts can read it.
13. **A visible sources list with outbound links to the primary documents.** Engines and readers trust pages that show their evidence. It also gives agents a path to verify.
14. **Do not keyword stuff.** The paper measured it as the one tactic that lowered visibility, and Google treats it as spam.
15. **Machine-readable twin of each article.** Offer the same article at a stable `.md` or JSON URL (title, summary, claims with quotes and source URLs). The PRD says the product serves "humans and AI systems", and an agent reading the twin gets the claim-to-evidence mapping directly. This is our differentiator and costs little because the data exists. The benefit is unproven as ranking, so measure it (section 6).

**Crawl policy**
16. Allow `Googlebot`, `OAI-SearchBot`, `PerplexityBot`, `Claude-SearchBot`, `Claude-User` and `Bingbot`. Make the training-bot decision (`GPTBot`, `ClaudeBot`, `Google-Extended`) a conscious business choice: blocking them does not remove you from AI search answers, per the vendor pages above. Publish IP-aware allow rules at the CDN.
17. Do not block `ChatGPT-User` or `Perplexity-User` in robots.txt expecting an effect; vendors say user-triggered fetches may ignore it.

## 5. What not to do

- No keyword stuffing, hidden text, or text only crawlers see.
- No fabricated authors, headshots or credentials.
- No structured data for content that is not on the page, no fake reviews or ratings.
- No mass publishing to fill a slot. The product rule "skip the slot if nothing meets the bar" is also the right SEO policy: Google's scaled-content-abuse policy targets volume without value.
- No `nosnippet` or `max-snippet:0` on articles we want cited, since that also removes them from AI Overviews.
- Do not chase vendor "GEO score" tools or per-platform citation percentages from blogs.

## 6. Measuring whether it works

- **Search Console**: Performance report, "Web" type, covers classic and AI features together. Watch indexed pages, impressions, clicks, and the sitemap report.
- **Server logs by user agent**: count visits from `OAI-SearchBot`, `PerplexityBot`, `Claude-SearchBot`, `Claude-User`, `ChatGPT-User`, `Perplexity-User`, `Bingbot`, `Googlebot`. Visits from user-triggered agents mean someone asked an assistant about a page of ours.
- **Referrals**: referrer and UTM breakdown for chat.openai.com, perplexity.ai, and similar.
- **Citation probes**: a fixed list of 30 to 50 questions our articles should answer. Ask each AI engine weekly and record whether we are cited. This is the only direct GEO measurement we can run ourselves, and it also tests the machine-readable twin (rule 15) as an A/B across articles.
- **Content checks in our own golden set**: add per-article metrics for fact density (numbers and quotes per 100 words), answer-first presence and source-link count.

## 7. What to build, in order

| # | Change | Size |
| --- | --- | --- |
| 1 | Publish model: `slug`, `seo_title`, `meta_description`, `published_at`, `modified_at`, `canonical_url`, `byline`, `process_note`, `editor_analysis`, with a manual Publish action after approval | one PR with a migration |
| 2 | Public article page: `<title>`, meta description, canonical, Open Graph and Twitter tags, `max-image-preview:large`, JSON-LD `NewsArticle`, visible byline, dates, process note, key-facts block, sources list | one PR |
| 3 | `robots.txt` with the crawler policy, `sitemap.xml` with accurate `lastmod`, news sitemap, RSS kept | one small PR |
| 4 | Writer output: answer-first summary and "Key facts" generated from verified claims, question-style headings | prompt and schema change, measured on the golden set |
| 5 | Machine-readable twin (`/articles/{slug}.md` and `.json`) | small |
| 6 | IndexNow ping on publish, plus the key file | small |
| 7 | Cover image pipeline: 16x9 at least 1200 px, plus crops | depends on how covers are made today |
| 8 | Measurement: bot-visit log, referrals, weekly citation probe | small script plus a table |
| 9 | `llms.txt` | one hour, low priority |

## 8. Unverified or open

- Exact per-domain results and the ranking-position effect in the GEO paper (check Tables 2 and 3). The whole paper's setup is not a production engine.
- Whether ChatGPT search depends on the Bing index, and whether Google, Bing and others read `llms.txt`. No primary source I read says so.
- The full list of IndexNow-participating engines.
- What `Google-Extended` blocks beyond the one sentence on the AI features page.
- Real citation shares per platform. All figures seen were vendor studies.
- Whether Google's systems treat disclosed AI-assisted articles differently from undisclosed ones. Google says disclosure is not required for Search.

## Sources

Primary sources read:
- [Google: AI features and your website](https://developers.google.com/search/docs/appearance/ai-features)
- [Google: Creating helpful, reliable, people-first content](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)
- [Google: Using generative AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)
- [Google: Article structured data](https://developers.google.com/search/docs/appearance/structured-data/article)
- [Google: Structured data general guidelines](https://developers.google.com/search/docs/appearance/structured-data/sd-policies)
- [Google: Build a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google: News sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap)
- [Google: Discover](https://developers.google.com/search/docs/appearance/google-discover)
- [Google: Title links](https://developers.google.com/search/docs/appearance/title-link)
- [Google: Robots meta tag, data-nosnippet and X-Robots-Tag](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag)
- [web.dev: Core Web Vitals](https://web.dev/articles/vitals)
- [GEO: Generative Engine Optimization (arXiv 2311.09735)](https://arxiv.org/abs/2311.09735), [HTML version](https://arxiv.org/html/2311.09735v3)
- [OpenAI: crawlers overview](https://developers.openai.com/api/docs/bots)
- [Perplexity: bots](https://docs.perplexity.ai/guides/bots)
- [Anthropic: crawling and blocking ClaudeBot](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler)
- [llmstxt.org](https://llmstxt.org/)
- [IndexNow documentation](https://www.indexnow.org/documentation)
- [schema.org Article](https://schema.org/Article), [NewsArticle](https://schema.org/NewsArticle)

Secondary, vendor material (used only for the landscape and flagged above): the GEO guides from [Frase](https://frase.io/blog/what-is-generative-engine-optimization-geo), [Conductor](https://www.conductor.com/academy/glossary/generative-engine-optimization), [Search Engine Land](https://searchengineland.com/generative-engine-optimization-framework-introduced-research-paper-435855) and others returned by search.

## 9. Implementation status

- **Publish backend (shipped):** `published_articles` table (migration 0011) holds an immutable snapshot of the approved body plus `slug`, `seo_title`, `meta_description`, `byline`, `process_note`, `editor_analysis`, `published_at`, `modified_at` and a published or unpublished status. `POST /editor/drafts/{id}/publish` needs an approved, drafted, unflagged article. Slug and meta description default from the title and dek. The byline and process note come from `PUBLISH_BYLINE` and `PUBLISH_PROCESS_NOTE`. `POST /editor/articles/{slug}/unpublish` takes an article down without deleting it. Public read routes `GET /articles` and `GET /articles/{slug}` serve published articles through an explicit allow-list (no flags, review state, template or cost).
- **Set `PUBLISH_BYLINE` to the editor's real name.** The default is "SignalForge Editorial".
- **Public pages (shipped):** the article page renders title, dek, byline and dates, a key-facts block built from verified and supported claims with their source links, the sections, an optional editor's analysis, a numbered sources list and the process note. `generateMetadata` sets title, description, canonical, Open Graph (`article`, published and modified times), Twitter card, `max-image-preview:large`, and `<link rel="alternate">` to the Markdown and JSON twins. A `NewsArticle` JSON-LD block carries headline, dates, author, publisher, image (when there is one) and `citation` entries for the sources. `robots.txt` always allows Googlebot, Bingbot, OAI-SearchBot, PerplexityBot, Claude-SearchBot and Claude-User, hides `/editor`, `/api`, `/design` and `/search`, and blocks GPTBot, ClaudeBot and Google-Extended only when `AI_TRAINING_CRAWLERS=block`. `sitemap.xml` uses each article's real `modified_at`. `news-sitemap.xml` lists the last two days. `feed.xml` is a real Atom feed. `/articles/{slug}/md` and `/articles/{slug}/json` serve the agent twins with a canonical `Link` header and `X-Robots-Tag: noindex` so they never compete with the HTML page.
- **Set `SITE_URL`** in production. It drives canonical URLs, sitemaps and the feed (default `http://localhost:3000`).
- Found while testing against real article data: pages that read `SITE_URL` or the article list must be dynamic, not prerendered at build, or the sitemap and feed ship empty with localhost URLs. The fetch cache (5 minutes) keeps API load low.
- **Built (draft-v4):** the writer states the finding with its key number in the dek, opens paragraphs with the main point and uses question headings where they fit. Golden set, two runs: dek carries a number in 4 of 4 drafts; question headings appear in 2 of 4 (the others keep plain headings by design). Grounding rates stayed in the same range (0.74 to 1.0, judge is noisy).
- **Not built yet:** IndexNow ping, cover image pipeline (until covers exist, pages omit `image`), citation probes and bot-visit logging, `llms.txt`.
