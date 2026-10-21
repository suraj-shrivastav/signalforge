"use client";
import { useState } from "react";
import {
  ApiError,
  CLAIM_STATUSES,
  fetchDraftList,
  fetchEditorDraft,
  type DraftSummary,
  type EditorDraft,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ArticlePreview } from "@/components/triage/ArticlePreview";
import { ReviewPanel } from "@/components/drafts/ReviewPanel";

type ListState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; drafts: DraftSummary[] }
  | { kind: "failed"; message: string };

function failureMessage(err: unknown, what: string): string {
  return err instanceof ApiError && err.status === 401
    ? "Enter a valid editor key."
    : `Could not load ${what}.`;
}

function counts(summary: DraftSummary): string {
  const parts = CLAIM_STATUSES.flatMap((s) =>
    summary.claim_counts[s] ? [`${summary.claim_counts[s]} ${s}`] : [],
  );
  return parts.length ? parts.join(", ") : "no claims";
}

// Key lives in memory only, like the triage board: never stored or put in a URL.
export function DraftsBoard() {
  const [editorKey, setEditorKey] = useState("");
  const [list, setList] = useState<ListState>({ kind: "idle" });
  const [open, setOpen] = useState<EditorDraft | null>(null);
  const [openError, setOpenError] = useState("");

  async function loadList() {
    setList({ kind: "loading" });
    setOpen(null);
    try {
      setList({ kind: "loaded", drafts: await fetchDraftList(editorKey) });
    } catch (err) {
      setList({ kind: "failed", message: failureMessage(err, "drafts") });
    }
  }

  async function openDraft(cardId: string) {
    setOpenError("");
    try {
      const draft = await fetchEditorDraft(cardId, editorKey);
      if (draft) setOpen(draft);
      else setOpenError("That draft no longer exists.");
    } catch (err) {
      setOpenError(failureMessage(err, "the draft"));
    }
  }

  return (
    <div>
      <div className="mb-6 flex max-w-md items-end gap-3">
        <Input
          label="Editor key"
          type="password"
          autoComplete="off"
          value={editorKey}
          onChange={(e) => setEditorKey(e.target.value)}
        />
        <Button
          onClick={loadList}
          disabled={!editorKey || list.kind === "loading"}
        >
          {list.kind === "loading" ? "Loading" : "Load drafts"}
        </Button>
      </div>
      {list.kind === "failed" && (
        <p role="alert" className="mb-4 text-small text-ink">
          {list.message}
        </p>
      )}
      {list.kind === "loaded" && list.drafts.length === 0 && (
        <Card className="p-6">
          <p className="text-ink">
            No drafts yet. Accept a card in triage, then run research and draft.
          </p>
        </Card>
      )}
      {list.kind === "loaded" && list.drafts.length > 0 && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <ul className="space-y-3 md:col-span-1">
            {list.drafts.map((d) => (
              <li key={d.card_id}>
                <button
                  type="button"
                  onClick={() => openDraft(d.card_id)}
                  aria-current={open?.card_id === d.card_id || undefined}
                  className="w-full text-left"
                >
                  <Card className="p-4">
                    <p className="text-small font-medium text-ink">
                      {d.title || d.signal_title}
                    </p>
                    <p className="text-caption text-muted">
                      {d.status.replaceAll("_", " ")} · {counts(d)}
                    </p>
                  </Card>
                </button>
              </li>
            ))}
          </ul>
          <div className="md:col-span-2">
            {openError && (
              <p role="alert" className="mb-4 text-small text-ink">
                {openError}
              </p>
            )}
            {open ? (
              <Card className="p-6">
                <ArticlePreview draft={open} />
                <ReviewPanel
                  draft={open}
                  editorKey={editorKey}
                  onUpdated={setOpen}
                />
              </Card>
            ) : (
              <p className="text-small text-muted">Pick a draft to read it.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
