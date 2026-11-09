// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  articleJsonLd,
  articleMarkdown,
  articleMetadata,
  breadcrumbJsonLd,
  atomFeed,
  escapeXml,
  jsonLdString,
  keyFacts,
  newsSitemap,
} from "./seo";
import { parseArticle, type PublicArticle } from "./public";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";

const SITE = "https://example.org";

const article: PublicArticle = {
  slug: "granite-5",
  figure: null,
  kind: null,
  source_label: "",
  headline: null,
  title: "Granite Speech 5.0 adds keyword biasing",
  seo_title: "Granite Speech 5.0 adds keyword biasing",
  meta_description: "IBM released Granite Speech 5.0.",
  dek: "A 2B model with keyword biasing.",
  byline: "SignalForge Editorial",
  process_note: "Checked against sources.",
  editor_analysis: "",
  published_at: "2026-10-21T10:00:00Z",
  modified_at: "2026-10-22T10:00:00Z",
  cover: { src: "https://cdn.example.org/c.jpg", alt: "Cover", credit: null },
  sections: [{ heading: "What changed", paragraphs: ["It is new."] }],
  claims: [
    { text: "Supports 2,000 terms.", status: "verified", source_indices: [0] },
    { text: "Maybe faster.", status: "uncertain", source_indices: [0] },
    { text: "Bad link claim.", status: "supported", source_indices: [1] },
  ],
  sources: [
    { label: "IBM blog", url: "https://huggingface.co/blog/ibm" },
    { label: "bad", url: "javascript:alert(1)" },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("keyFacts", () => {
  it("keeps verified and supported claims and only safe source links", () => {
    expect(keyFacts(article)).toEqual([
      {
        text: "Supports 2,000 terms.",
        sources: [
          { label: "IBM blog", url: "https://huggingface.co/blog/ibm" },
        ],
      },
      { text: "Bad link claim.", sources: [] },
    ]);
  });
});

describe("articleJsonLd", () => {
  it("describes a NewsArticle that matches the page", () => {
    const ld = articleJsonLd(article, SITE);
    expect(ld["@type"]).toBe("NewsArticle");
    expect(ld.headline).toBe(article.title);
    expect(ld.datePublished).toBe(article.published_at);
    expect(ld.dateModified).toBe(article.modified_at);
    expect(ld.author).toEqual({
      "@type": "Organization",
      name: "SignalForge Editorial",
    });
    expect(ld.mainEntityOfPage).toEqual({
      "@type": "WebPage",
      "@id": `${SITE}/articles/granite-5`,
    });
    expect(ld.image).toEqual([`${SITE}/articles/granite-5/og.png`]);
    expect(ld.citation).toEqual([
      {
        "@type": "CreativeWork",
        name: "IBM blog",
        url: "https://huggingface.co/blog/ibm",
      },
    ]);
  });

  it("uses a Person for a named editor", () => {
    const ld = articleJsonLd(
      {
        ...article,
        byline: "Asha Rao",
        cover: { src: null, alt: "a", credit: null },
      },
      SITE,
    );
    expect((ld.author as { "@type": string })["@type"]).toBe("Person");
  });

  it("cannot break out of the script tag", () => {
    const out = jsonLdString({
      headline: "</script><script>alert(1)</script>",
    });
    expect(out).not.toContain("</script>");
    expect(JSON.parse(out).headline).toContain("</script>");
  });
});

describe("articleMetadata", () => {
  it("sets canonical, article Open Graph, large previews and agent alternates", () => {
    const meta = articleMetadata(article, SITE);
    const url = `${SITE}/articles/granite-5`;
    expect(meta.title).toBe(article.seo_title);
    expect(meta.description).toBe(article.meta_description);
    expect(meta.alternates?.canonical).toBe(url);
    expect(meta.alternates?.types).toMatchObject({
      "text/markdown": `${url}/md`,
      "application/json": `${url}/json`,
    });
    expect(meta.openGraph).toMatchObject({
      type: "article",
      publishedTime: article.published_at,
      modifiedTime: article.modified_at,
    });
    expect(meta.robots).toMatchObject({
      index: true,
      googleBot: { "max-image-preview": "large", "max-snippet": -1 },
    });
    expect(meta.twitter).toMatchObject({ card: "summary_large_image" });
  });

  it("always uses the large card and the PNG share card", () => {
    const meta = articleMetadata(
      { ...article, cover: { src: null, alt: "a", credit: null } },
      SITE,
    );
    expect(meta.twitter).toMatchObject({ card: "summary_large_image" });
    expect(meta.openGraph).toMatchObject({
      images: [{ url: `${SITE}/articles/granite-5/og.png`, width: 1200 }],
    });
  });
});

describe("duplicate source URLs", () => {
  const dup: PublicArticle = {
    ...article,
    sources: [
      { label: "arXiv abstract", url: "https://arxiv.org/abs/1" },
      { label: "arXiv paper", url: "https://arxiv.org/abs/1" },
    ],
    claims: [
      {
        text: "A verified claim.",
        status: "verified",
        source_indices: [0, 1],
      },
    ],
  };

  it("lists each URL once in facts, citations and the markdown sources", () => {
    expect(keyFacts(dup)[0].sources).toHaveLength(1);
    expect(articleJsonLd(dup, SITE).citation).toHaveLength(1);
    const md = articleMarkdown(dup, SITE);
    expect(md.match(/arxiv\.org\/abs\/1\)/g)).toHaveLength(2); // fact ref + source list
  });
});

describe("breadcrumbJsonLd", () => {
  it("lists Home then the article with absolute URLs", () => {
    const ld = breadcrumbJsonLd(article, SITE);
    expect(ld["@type"]).toBe("BreadcrumbList");
    expect(ld.itemListElement).toEqual([
      { "@type": "ListItem", position: 1, name: "Home", item: `${SITE}/` },
      {
        "@type": "ListItem",
        position: 2,
        name: article.title,
        item: `${SITE}/articles/granite-5`,
      },
    ]);
  });
});

describe("articleMarkdown", () => {
  it("keeps the canonical URL, key facts and numbered sources", () => {
    const md = articleMarkdown(article, SITE);
    expect(md).toContain("# Granite Speech 5.0 adds keyword biasing");
    expect(md).toContain(`Canonical: ${SITE}/articles/granite-5`);
    expect(md).toContain(
      "- Supports 2,000 terms. ([IBM blog](https://huggingface.co/blog/ibm))",
    );
    expect(md).toContain("1. [IBM blog](https://huggingface.co/blog/ibm)");
  });
});

describe("feeds", () => {
  it("escapes XML in the Atom feed and uses the latest modified date", () => {
    const xml = atomFeed([{ ...article, title: "A & B <c>" }], SITE);
    expect(xml).toContain("A &amp; B &lt;c&gt;");
    expect(xml).toContain("<updated>2026-10-22T10:00:00Z</updated>");
    const doc = new DOMParser().parseFromString(xml, "application/xml");
    expect(doc.getElementsByTagName("parsererror")).toHaveLength(0);
  });

  it("lists only articles from the last two days in the news sitemap", () => {
    const now = new Date("2026-10-22T12:00:00Z");
    const old = {
      ...article,
      slug: "old",
      published_at: "2026-10-01T00:00:00Z",
    };
    const xml = newsSitemap([article, old], SITE, now);
    expect(xml).toContain(`${SITE}/articles/granite-5`);
    expect(xml).not.toContain("/articles/old");
    expect(xml).toContain("<news:publication_date>2026-10-21T10:00:00Z");
  });

  it("escapes the five XML characters", () => {
    expect(escapeXml(`<a href="x">&'</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;&amp;&apos;&lt;/a&gt;",
    );
  });
});

describe("parseArticle", () => {
  it("drops unknown fields and rejects malformed ones", () => {
    const parsed = parseArticle({ ...article, review_summary: "secret" });
    expect("review_summary" in parsed).toBe(false);
    expect(() => parseArticle({ ...article, sections: "nope" })).toThrow();
  });
});

describe("robots and sitemap", () => {
  it("allows search crawlers and hides private paths", () => {
    vi.stubEnv("SITE_URL", SITE);
    const r = robots();
    const rules = Array.isArray(r.rules) ? r.rules : [r.rules];
    expect(rules[0]).toMatchObject({ userAgent: "*", allow: "/" });
    expect(rules[0].disallow).toContain("/editor");
    expect(JSON.stringify(rules)).toContain("OAI-SearchBot");
    expect(JSON.stringify(rules)).not.toContain("GPTBot");
    expect(r.sitemap).toEqual([
      `${SITE}/sitemap.xml`,
      `${SITE}/news-sitemap.xml`,
    ]);
  });

  it("blocks training crawlers only when asked", () => {
    vi.stubEnv("AI_TRAINING_CRAWLERS", "block");
    const rules = robots().rules as {
      userAgent: string | string[];
      disallow?: string;
    }[];
    const blocked = rules.find(
      (x) => Array.isArray(x.userAgent) && x.userAgent.includes("GPTBot"),
    );
    expect(blocked?.disallow).toBe("/");
    expect(JSON.stringify(blocked)).not.toContain("OAI-SearchBot");
  });

  it("lists articles with their real modified date", async () => {
    vi.stubEnv("SITE_URL", SITE);
    vi.stubEnv("API_BASE_URL", "http://api.test");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json([article])),
    );
    const entries = await sitemap();
    expect(entries.map((e) => e.url)).toEqual([
      `${SITE}/`,
      `${SITE}/articles/granite-5`,
    ]);
    expect(entries[1].lastModified).toEqual(new Date(article.modified_at));
  });
});

describe("tables in the Markdown twin and the API shape", () => {
  const table = {
    caption: "Word error rate",
    header: ["Model", "WER"],
    rows: [
      ["Granite", "5.06"],
      ["A | B", "7.40"],
    ],
    source: { label: "IBM model card", url: "https://huggingface.co/ibm" },
  };

  it("writes a GitHub-style table with its caption and source", () => {
    const md = articleMarkdown(
      {
        ...article,
        sections: [{ heading: "Results", paragraphs: ["See below."], table }],
      },
      SITE,
    );
    expect(md).toContain("**Word error rate**");
    expect(md).toContain("| Model | WER |\n| --- | --- |\n| Granite | 5.06 |");
    expect(md).toContain("| A \\| B | 7.40 |");
    expect(md).toContain(
      "Source: [IBM model card](https://huggingface.co/ibm)",
    );
    expect(md.indexOf("See below.")).toBeLessThan(md.indexOf("| Model |"));
  });

  it("leaves the source out of Markdown when its link is unsafe", () => {
    const md = articleMarkdown(
      {
        ...article,
        sections: [
          {
            heading: "Results",
            paragraphs: ["x."],
            table: { ...table, source: { label: "Bad", url: "javascript:x" } },
          },
        ],
      },
      SITE,
    );
    expect(md).not.toContain("Source:");
  });

  it("parses a table from the API and drops a malformed one without failing", () => {
    const base = {
      slug: "s",
      title: "T",
      dek: "D",
      meta_description: "M",
      published_at: "2026-10-21T10:00:00Z",
      modified_at: "2026-10-21T10:00:00Z",
      cover: { src: null, alt: "a", credit: null },
      seo_title: "T",
      byline: "B",
      process_note: "P",
      editor_analysis: "",
      claims: [],
      sources: [],
      figure: null,
    };
    const good = parseArticle({
      ...base,
      sections: [{ heading: "H", paragraphs: ["p"], table }],
    });
    expect(good.sections[0].table?.rows[1]).toEqual(["A | B", "7.40"]);
    expect(good.sections[0].table?.source?.label).toBe("IBM model card");
    const ragged = parseArticle({
      ...base,
      sections: [
        {
          heading: "H",
          paragraphs: ["p"],
          table: { ...table, rows: [["only one cell"]] },
        },
      ],
    });
    expect(ragged.sections[0].table).toBeNull();
    const none = parseArticle({
      ...base,
      sections: [{ heading: "H", paragraphs: ["p"] }],
    });
    expect(none.sections[0].table).toBeNull();
  });

  it("keeps the table in the JSON twin through the article object", () => {
    const withTable = {
      ...article,
      sections: [{ heading: "H", paragraphs: ["p"], table }],
    };
    expect(
      JSON.parse(JSON.stringify(withTable)).sections[0].table.header,
    ).toEqual(["Model", "WER"]);
  });
});
