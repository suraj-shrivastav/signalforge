// TODO(design): design references and global.css are pending; unstyled on purpose.
"use client";

import {
  createContext,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";

const EditorKeyContext = createContext("");

type DecisionClock = { since: () => number; markDecided: () => void };

const LastDecisionContext = createContext<DecisionClock>({
  since: () => 0,
  markDecided: () => {},
});

// Time of the last saved decision (or board mount), shared by all cards.
export function useDecisionClock(): DecisionClock {
  return useContext(LastDecisionContext);
}

export function useEditorKey(): string {
  return useContext(EditorKeyContext);
}

// One key field for the whole page. Memory only: never stored or put in a URL.
export function TriageBoard({ children }: { children: ReactNode }) {
  const [editorKey, setEditorKey] = useState("");
  const [mountedAt] = useState(() => Date.now());
  const lastDecisionAt = useRef(mountedAt);
  const [clock] = useState<DecisionClock>(() => ({
    since: () => lastDecisionAt.current,
    markDecided: () => {
      lastDecisionAt.current = Date.now();
    },
  }));
  return (
    <LastDecisionContext.Provider value={clock}>
      <EditorKeyContext.Provider value={editorKey}>
        <label>
          Editor key
          <input
            type="password"
            autoComplete="off"
            value={editorKey}
            onChange={(e) => setEditorKey(e.target.value)}
          />
        </label>
        {children}
      </EditorKeyContext.Provider>
    </LastDecisionContext.Provider>
  );
}
