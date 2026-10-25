"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";
import {
  THEME_STORAGE_KEY,
  applyTheme,
  readStoredTheme,
  type Theme,
} from "@/lib/theme";

const NEXT: Record<Theme, Theme> = {
  light: "dark",
  dark: "system",
  system: "light",
};

const LABEL: Record<Theme, string> = {
  light: "Theme: light. Switch to dark",
  dark: "Theme: dark. Switch to system",
  system: "Theme: system. Switch to light",
};

function initialTheme(): Theme {
  if (typeof window === "undefined") return "system";
  try {
    return readStoredTheme(window.localStorage);
  } catch {
    return "system";
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  function onClick() {
    const next = NEXT[theme];
    setTheme(next);
    applyTheme(document, next);
    try {
      if (next === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
      else window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // storage blocked: choice applies for this session only
    }
  }

  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={LABEL[theme]}
      className="inline-flex items-center justify-center rounded-control p-2.5 text-ink transition-colors hover:bg-sunken"
    >
      <Icon aria-hidden="true" className="size-5" />
    </button>
  );
}
