import { describe, expect, it } from "vitest";
import { signSession, verifySession, THIRTY_DAYS_MS } from "./editorAuth";

describe("signSession / verifySession", () => {
  it("accepts a session it just signed", async () => {
    const value = await signSession("secret", 1_000);
    await expect(
      verifySession("secret", value, 1_000, THIRTY_DAYS_MS),
    ).resolves.toBe(true);
  });

  it("rejects a tampered timestamp", async () => {
    const value = await signSession("secret", 1_000);
    const [, sig] = value.split(".");
    await expect(
      verifySession("secret", `999.${sig}`, 1_000, THIRTY_DAYS_MS),
    ).resolves.toBe(false);
  });

  it("rejects a session signed with a different secret", async () => {
    const value = await signSession("secret-a", 1_000);
    await expect(
      verifySession("secret-b", value, 1_000, THIRTY_DAYS_MS),
    ).resolves.toBe(false);
  });

  it("rejects an expired session", async () => {
    const value = await signSession("secret", 1_000);
    await expect(
      verifySession(
        "secret",
        value,
        1_000 + THIRTY_DAYS_MS + 1,
        THIRTY_DAYS_MS,
      ),
    ).resolves.toBe(false);
  });

  it("rejects a malformed cookie value", async () => {
    await expect(
      verifySession("secret", "not-a-valid-cookie", 1_000, THIRTY_DAYS_MS),
    ).resolves.toBe(false);
  });
});
