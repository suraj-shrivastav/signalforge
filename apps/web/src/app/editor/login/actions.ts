"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import {
  COOKIE_NAME,
  THIRTY_DAYS_MS,
  getCookieSecret,
  signSession,
} from "@/lib/editorAuth";

const DEFAULT_NEXT = "/editor/signals";

function resolveNext(next: FormDataEntryValue | null): string {
  if (typeof next !== "string" || !next.startsWith("/editor/")) {
    return DEFAULT_NEXT;
  }
  return next;
}

export async function login(formData: FormData): Promise<never> {
  const password = process.env.EDITOR_UI_PASSWORD;
  if (!password) {
    throw new Error("EDITOR_UI_PASSWORD is not set");
  }

  const submitted = formData.get("password");
  const next = resolveNext(formData.get("next"));

  if (typeof submitted !== "string" || submitted !== password) {
    const loginUrl = `/editor/login?next=${encodeURIComponent(next)}&error=1`;
    redirect(loginUrl);
  }

  const secret = getCookieSecret();
  if (!secret) {
    throw new Error("EDITOR_UI_PASSWORD is not set");
  }

  const cookieValue = await signSession(secret, Date.now());
  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, cookieValue, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: THIRTY_DAYS_MS / 1000,
    path: "/",
  });

  redirect(next);
}

export async function logout(): Promise<never> {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
  redirect("/editor/login");
}
