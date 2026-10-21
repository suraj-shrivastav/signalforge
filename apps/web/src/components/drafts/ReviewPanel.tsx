"use client";
import { useState } from "react";
import {
  fetchEditorDraft,
  postDraftAction,
  publishDraft,
  type DraftFlag,
  type EditorDraft,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";

type Props = {
  draft: EditorDraft;
  editorKey: string;
  onUpdated: (draft: EditorDraft) => void;
};

// Deliberately plain: edit or delete each flagged sentence, then decide.
export function ReviewPanel({ draft, editorKey, onUpdated }: Props) {
  const [note, setNote] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [error, setError] = useState("");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const flags = draft.draft?.flags ?? [];
  const decided =
    draft.review_status === "approved" || draft.review_status === "rejected";

  async function send(
    action: "sentence" | "review",
    payload: Record<string, unknown>,
  ) {
    setError("");
    try {
      onUpdated(
        await postDraftAction(draft.card_id, action, payload, editorKey),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    }
  }

  async function publish() {
    setError("");
    try {
      await publishDraft(draft.card_id, analysis, editorKey);
      const fresh = await fetchEditorDraft(draft.card_id, editorKey);
      if (fresh) onUpdated(fresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    }
  }

  function editSentence(flag: DraftFlag, replacement: string | null) {
    return send("sentence", {
      section: flag.section,
      paragraph: flag.paragraph,
      text: flag.text,
      replacement,
    });
  }

  return (
    <section
      aria-label="Editor review"
      className="mt-8 border-t border-line pt-4"
    >
      <h2>Review</h2>
      <p className="text-small text-muted">
        Status: {draft.review_status}
        {draft.review_note ? ` (${draft.review_note})` : ""}
      </p>
      {flags.length > 0 && !decided && (
        <ul className="space-y-4">
          {flags.map((flag) => {
            const id = `${flag.section}:${flag.paragraph}:${flag.text}`;
            return (
              <li key={id}>
                <p className="text-caption text-muted">
                  {flag.kind}: {flag.detail}
                </p>
                <textarea
                  aria-label={`Edit sentence: ${flag.text}`}
                  className="w-full border border-line bg-surface p-2 text-small text-ink"
                  value={edits[id] ?? flag.text}
                  onChange={(e) => setEdits({ ...edits, [id]: e.target.value })}
                />
                <Button
                  onClick={() => editSentence(flag, edits[id] ?? flag.text)}
                >
                  Save edit
                </Button>{" "}
                <Button onClick={() => editSentence(flag, null)}>Delete</Button>
              </li>
            );
          })}
        </ul>
      )}
      {!decided && (
        <div className="mt-4 space-y-2">
          <textarea
            aria-label="Review note"
            placeholder="Note (optional)"
            className="w-full border border-line bg-surface p-2 text-small text-ink"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Button
            onClick={() => send("review", { decision: "approved", note })}
            disabled={flags.length > 0 || draft.status !== "drafted"}
          >
            Approve
          </Button>{" "}
          <Button onClick={() => send("review", { decision: "revise", note })}>
            Request revision
          </Button>{" "}
          <Button
            onClick={() => send("review", { decision: "rejected", note })}
          >
            Reject
          </Button>
        </div>
      )}
      {draft.review_status === "approved" && !draft.published_slug && (
        <div className="mt-4 space-y-2">
          <textarea
            aria-label="Editor analysis"
            placeholder="Editor's analysis shown with the article (optional)"
            className="w-full border border-line bg-surface p-2 text-small text-ink"
            value={analysis}
            onChange={(e) => setAnalysis(e.target.value)}
          />
          <Button onClick={publish}>Publish</Button>
        </div>
      )}
      {draft.published_slug && (
        <p className="mt-4 text-small">
          Published:{" "}
          <a href={`/articles/${draft.published_slug}`} className="underline">
            /articles/{draft.published_slug}
          </a>
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-small text-ink">
          {error}
        </p>
      )}
    </section>
  );
}
