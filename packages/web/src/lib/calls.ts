/**
 * Calls-surface helpers (Spec V9).
 */

/**
 * Format a call's whole-second duration as ``m:ss`` (e.g. 125 → "2:05"). A
 * ``null`` duration — a live or crashed call with no recorded end — returns
 * ``null`` so the caller can fall back to a generic label.
 */
export function formatCallDuration(seconds: number | null): string | null {
  if (seconds == null) return null;
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const secs = String(safe % 60).padStart(2, "0");
  return `${minutes}:${secs}`;
}
