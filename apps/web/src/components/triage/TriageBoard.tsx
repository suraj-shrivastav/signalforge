// TODO(design): design references and global.css are pending; unstyled on purpose.
"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

const EditorKeyContext = createContext("");

export function useEditorKey(): string {
  return useContext(EditorKeyContext);
}

// One key field for the whole page. Memory only: never stored or put in a URL.
export function TriageBoard({ children }: { children: ReactNode }) {
  const [editorKey, setEditorKey] = useState("");
  return (
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
  );
}
