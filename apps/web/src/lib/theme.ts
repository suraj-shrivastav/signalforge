export type Theme = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "signalforge-theme";

export function readStoredTheme(storage: Pick<Storage, "getItem">): Theme {
  try {
    const value = storage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(
  stored: Theme,
  prefersDark: boolean,
): "light" | "dark" {
  if (stored === "system") return prefersDark ? "dark" : "light";
  return stored;
}

export function applyTheme(doc: Document, theme: Theme): void {
  if (theme === "system") doc.documentElement.removeAttribute("data-theme");
  else doc.documentElement.setAttribute("data-theme", theme);
}

// Constant string, no user input. Runs before first paint.
export const THEME_INIT_SCRIPT = `try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}`;
