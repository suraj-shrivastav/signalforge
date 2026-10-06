"use client";
import { useState } from "react";
import { ApiError, fetchEditorDraft, type EditorDraft } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ArticlePreview } from "./ArticlePreview";
import { useEditorKey } from "./TriageBoard";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "none" }
  | { kind: "loaded"; draft: EditorDraft }
  | { kind: "failed"; message: string };

// Loaded on demand: most queued cards have no draft yet, so no request per card.
export function DraftPanel({ cardId }: { cardId: string }) {
  const editorKey = useEditorKey();
  const [state, setState] = useState<State>({ kind: "idle" });

  async function load() {
    setState({ kind: "loading" });
    try {
      const draft = await fetchEditorDraft(cardId, editorKey);
      setState(draft ? { kind: "loaded", draft } : { kind: "none" });
    } catch (err) {
      setState({
        kind: "failed",
        message:
          err instanceof ApiError && err.status === 401
            ? "Enter a valid editor key to view the draft."
            : "Could not load the draft.",
      });
    }
  }

  if (state.kind === "loaded") return <ArticlePreview draft={state.draft} />;
  return (
    <div>
      <Button onClick={load} disabled={!editorKey || state.kind === "loading"}>
        {state.kind === "loading" ? "Loading draft" : "Show draft"}
      </Button>
      {state.kind === "none" && (
        <p className="mt-2 text-small text-muted">
          No draft for this card yet.
        </p>
      )}
      {state.kind === "failed" && (
        <p role="alert" className="mt-2 text-small text-ink">
          {state.message}
        </p>
      )}
    </div>
  );
}
