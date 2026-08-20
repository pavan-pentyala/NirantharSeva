/** "2 days" / "2 h" / "40 min" / "Yesterday" — matches the design's
 * monospace age-in-state column (Screen 1, Screen 5). Deliberately coarse:
 * the design never shows seconds or exact clock times here. */
export function relativeTimeSince(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  return `${days} days`;
}
