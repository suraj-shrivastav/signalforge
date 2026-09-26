const MAX_MS = 3_600_000;

// Time spent on this decision: since the board mounted or the last saved decision.
export function decisionElapsedMs(now: number, since: number): number {
  return Math.min(Math.max(0, now - since), MAX_MS);
}
