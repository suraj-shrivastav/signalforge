export const COOKIE_NAME = "sf_editor_session";
export const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

function base64UrlEncode(bytes: ArrayBuffer): string {
  const binary = Array.from(new Uint8Array(bytes), (byte) =>
    String.fromCharCode(byte),
  ).join("");
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function base64UrlDecode(value: string): ArrayBuffer | null {
  try {
    const padded = value
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(value.length / 4) * 4, "=");
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength,
    ) as ArrayBuffer;
  } catch {
    return null;
  }
}

async function importHmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

/** Returns the configured cookie secret, falling back to EDITOR_UI_PASSWORD. */
export function getCookieSecret(): string | undefined {
  return process.env.EDITOR_COOKIE_SECRET ?? process.env.EDITOR_UI_PASSWORD;
}

export async function signSession(
  secret: string,
  issuedAtMs: number,
): Promise<string> {
  const key = await importHmacKey(secret);
  const message = new TextEncoder().encode(String(issuedAtMs));
  const signature = await crypto.subtle.sign("HMAC", key, message);
  return `${issuedAtMs}.${base64UrlEncode(signature)}`;
}

export async function verifySession(
  secret: string,
  cookieValue: string,
  nowMs: number,
  maxAgeMs: number,
): Promise<boolean> {
  const parts = cookieValue.split(".");
  if (parts.length !== 2) return false;
  const [issuedAtStr, signatureB64] = parts;
  if (!/^\d+$/.test(issuedAtStr)) return false;
  const issuedAtMs = Number(issuedAtStr);
  if (!Number.isSafeInteger(issuedAtMs)) return false;
  if (nowMs - issuedAtMs > maxAgeMs) return false;
  const signature = base64UrlDecode(signatureB64);
  if (!signature) return false;
  const key = await importHmacKey(secret);
  const message = new TextEncoder().encode(issuedAtStr);
  return crypto.subtle.verify("HMAC", key, signature, message);
}
