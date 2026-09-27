// This file is a stand-in for the Phase 4 drafting pipeline, which does not
// exist yet. The article below is hand-written sample content used only to
// build and preview the triage draft-review view before real drafts exist.
// Do not import this module outside the triage draft-review view: once
// Phase 4 ships, drafts will come from the pipeline, and this fixture should
// be deleted rather than reused as a fallback.

export type MockArticleSection = {
  heading: string;
  paragraphs: string[];
};

export type MockArticleClaim = {
  text: string;
  sourceLabel: string;
  sourceUrl: string;
};

export type MockArticle = {
  template: string;
  title: string;
  dek: string;
  coverAlt: string;
  sections: MockArticleSection[];
  claims: MockArticleClaim[];
};

export const mockArticle: MockArticle = {
  template: "Explainer",
  title: "Why More Labs Are Betting on Speculative Batching",
  dek: "A decoding trick once limited to single requests is being adapted for shared inference queues, and early deployments suggest it can cut latency without new hardware.",
  coverAlt:
    "Abstract grid of small squares in varying shades, representing batched computation lanes",
  sections: [
    {
      heading: "The short version",
      paragraphs: [
        "Speculative decoding lets a small draft model guess several tokens ahead, while a larger model checks the guesses in one pass instead of generating them one at a time. The technique has mostly been used for single user requests. A newer variant, speculative batching, applies the same idea across many requests that are already sharing a GPU batch, and several inference teams say it is cutting response times on production traffic.",
        "The shift matters because most inference costs today come from serving many concurrent users, not from a single long generation. If speculation can be shared across a batch instead of run per request, the savings compound with traffic rather than shrinking under it.",
      ],
    },
    {
      heading: "What changed",
      paragraphs: [
        "Classic speculative decoding pairs one small draft model with one large target model for a single stream of tokens. When a serving system batches dozens of requests together for GPU efficiency, that pairing gets harder to keep, because each request in the batch may accept or reject its draft tokens at a different point, breaking the batch's alignment.",
        "Speculative batching addresses this by letting the scheduler re-pack a batch mid-step: requests that reject their draft tokens fall back to normal decoding for that step, while requests that accept keep advancing, and the scheduler regroups them before the next round. Inference framework vLLM added an experimental version of this batch-aware speculation path, and the open-source serving project TGI has a similar mode under review.",
      ],
    },
    {
      heading: "What the early numbers show",
      paragraphs: [
        "Cloud inference provider Fireworks AI published benchmark notes describing a median latency reduction on chat workloads when batch-aware speculation was enabled against a 13-billion-parameter target model with a 1-billion-parameter draft model. The gains were smaller on code-heavy workloads, where output is less predictable token to token, which is consistent with how speculative decoding has always behaved: it helps more when the next tokens are easier to guess.",
        "A separate account from an engineer at Together AI described similar batch-level gains in a public engineering post, alongside a caveat that the approach adds scheduler complexity and can behave unpredictably under sudden traffic spikes, when many requests reject their drafts at once and the batch effectively reverts to unassisted decoding.",
      ],
    },
    {
      heading: "Why it matters",
      paragraphs: [
        "Most latency work in inference serving has focused on the hardware and kernel level: better attention kernels, quantization, or continuous batching. Speculative batching is notable because it is a scheduling change layered on existing hardware, meaning teams already running vLLM or TGI could gain from it without buying new accelerators.",
        "It also shifts a longstanding tradeoff. Draft models add memory overhead, since a second model has to sit alongside the target model on the same accelerator. Sharing that draft model's guesses across an entire batch, rather than one request, spreads that fixed memory cost over more traffic, which changes the economics of running a draft model in the first place.",
      ],
    },
    {
      heading: "What to watch",
      paragraphs: [
        "The open questions are about consistency under load. Benchmarks so far have used steady, simulated traffic; production traffic arrives in bursts, and the rebalancing step that speculative batching relies on has not been stress-tested publicly at that scale. Anthropic, OpenAI and Google have not disclosed whether their own serving stacks use a comparable technique, so it is unclear how widely the idea has already spread inside frontier labs versus how much of the current interest is coming from open-source infrastructure projects catching up.",
        "Whether draft models get standardized, so that one small model can pair with several different target models, will also shape how quickly this spreads. Right now, each deployment trains or fine-tunes its own draft model pairing, which raises the setup cost for smaller teams considering the approach.",
      ],
    },
  ],
  claims: [
    {
      text: "Inference framework vLLM added an experimental batch-aware speculative decoding path to its scheduler.",
      sourceLabel: "vLLM project changelog",
      sourceUrl: "https://github.com/vllm-project/vllm/releases",
    },
    {
      text: "The open-source serving project TGI has a similar batch-aware speculation mode under review.",
      sourceLabel: "Hugging Face TGI GitHub repository",
      sourceUrl: "https://github.com/huggingface/text-generation-inference",
    },
    {
      text: "Fireworks AI reported a median latency reduction on chat workloads when batch-aware speculation was enabled with a 13B target and 1B draft model.",
      sourceLabel: "Fireworks AI engineering blog",
      sourceUrl: "https://fireworks.ai/blog",
    },
    {
      text: "An engineer at Together AI described similar batch-level latency gains and scheduler complexity in a public engineering post.",
      sourceLabel: "Together AI engineering blog",
      sourceUrl: "https://www.together.ai/blog",
    },
  ],
};
