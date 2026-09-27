"use client";

import { useRef, useState } from "react";
import {
  ApiError,
  postDecision,
  type DecisionKind,
  type ReasonTag,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ReasonTags } from "./ReasonTags";
import { decisionElapsedMs } from "@/lib/decisionTiming";
import { useEditorKey, useDecisionClock } from "./TriageBoard";

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; decision: DecisionKind }
  | { kind: "failed"; message: string };

export function DecisionBar({
  cardId,
  labelledBy,
}: {
  cardId: string;
  labelledBy: string;
}) {
  const editorKey = useEditorKey();
  const inFlight = useRef(false);
  const [tags, setTags] = useState<ReasonTag[]>([]);
  const [note, setNote] = useState("");
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const clock = useDecisionClock();
  const saving = state.kind === "saving";

  async function submit(decision: DecisionKind) {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ kind: "saving" });
    try {
      await postDecision(
        cardId,
        {
          decision,
          reason_tags: tags,
          note,
          decision_ms: decisionElapsedMs(Date.now(), clock.since()),
        },
        editorKey,
      );
      clock.markDecided();
      setState({ kind: "saved", decision });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 401
          ? "Wrong or missing editor key."
          : err instanceof ApiError
            ? `Failed (${err.status} ${err.code}): ${err.message}`
            : "Failed: network error.";
      setState({ kind: "failed", message });
    } finally {
      inFlight.current = false;
    }
  }

  return (
    <form
      aria-labelledby={labelledBy}
      onSubmit={(e) => e.preventDefault()}
      className="space-y-4"
    >
      <ReasonTags selected={tags} onChange={setTags} disabled={saving} />
      <label className="block">
        <span className="mb-1 block text-small font-medium text-ink">Note</span>
        <textarea
          maxLength={500}
          value={note}
          disabled={saving}
          onChange={(e) => setNote(e.target.value)}
          className="w-full rounded-control border border-line bg-surface px-3 py-2 text-small text-ink"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="primary"
          disabled={saving}
          onClick={() => submit("accepted")}
        >
          Accept
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={saving}
          onClick={() => submit("rejected")}
        >
          Reject
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={saving}
          onClick={() => submit("snoozed")}
        >
          Snooze
        </Button>
      </div>
      <p role="status" className="text-small text-muted">
        {state.kind === "saving" && "Saving..."}
        {state.kind === "saved" && `Saved: ${state.decision}`}
        {state.kind === "failed" && state.message}
      </p>
    </form>
  );
}
