// TODO(design): design references and global.css are pending; unstyled on purpose.
"use client";

import { useState } from "react";
import {
  ApiError,
  postDecision,
  type DecisionKind,
  type ReasonTag,
} from "@/lib/api";
import { ReasonTags } from "./ReasonTags";

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; decision: DecisionKind }
  | { kind: "failed"; message: string };

export function DecisionBar({ cardId }: { cardId: string }) {
  // Editor key lives in component state only: never stored or put in a URL.
  const [editorKey, setEditorKey] = useState("");
  const [tags, setTags] = useState<ReasonTag[]>([]);
  const [note, setNote] = useState("");
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const [renderedAt] = useState(() => Date.now());
  const saving = state.kind === "saving";

  async function submit(decision: DecisionKind) {
    setState({ kind: "saving" });
    try {
      await postDecision(
        cardId,
        {
          decision,
          reason_tags: tags,
          note,
          decision_ms: Math.min(
            Math.max(0, Date.now() - renderedAt),
            3_600_000,
          ),
        },
        editorKey,
      );
      setState({ kind: "saved", decision });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 401
          ? "Wrong or missing editor key."
          : err instanceof ApiError
            ? `Failed (${err.status} ${err.code}): ${err.message}`
            : "Failed: network error.";
      setState({ kind: "failed", message });
    }
  }

  return (
    <form onSubmit={(e) => e.preventDefault()}>
      <label>
        Editor key
        <input
          type="password"
          autoComplete="off"
          value={editorKey}
          onChange={(e) => setEditorKey(e.target.value)}
        />
      </label>
      <ReasonTags selected={tags} onChange={setTags} disabled={saving} />
      <label>
        Note
        <textarea
          maxLength={500}
          value={note}
          disabled={saving}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={saving}
        onClick={() => submit("accepted")}
      >
        Accept
      </button>
      <button
        type="button"
        disabled={saving}
        onClick={() => submit("rejected")}
      >
        Reject
      </button>
      <button type="button" disabled={saving} onClick={() => submit("snoozed")}>
        Snooze
      </button>
      <p role="status">
        {state.kind === "saving" && "Saving..."}
        {state.kind === "saved" && `Saved: ${state.decision}`}
        {state.kind === "failed" && state.message}
      </p>
    </form>
  );
}
