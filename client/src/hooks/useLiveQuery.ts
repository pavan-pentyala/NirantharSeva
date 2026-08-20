import { liveQuery } from "dexie";
import { useEffect, useState } from "react";

/** Equivalent to dexie-react-hooks' useLiveQuery, hand-rolled on top of
 * Dexie core's own liveQuery() — already part of the `dexie` dependency
 * already in package.json, so this needed no new package. Subscribes to
 * whichever Dexie tables `querier` reads and re-runs it whenever one of
 * them changes, instead of polling on a timer (what the Phase 1 toy
 * harness did — acceptable for one value, not for five screens each
 * reading multiple tables). */
export function useLiveQuery<T>(querier: () => Promise<T> | T, deps: unknown[] = []): T | undefined {
  const [value, setValue] = useState<T | undefined>(undefined);

  useEffect(() => {
    const subscription = liveQuery(querier).subscribe({
      next: setValue,
      error: (err: unknown) => console.error("useLiveQuery", err),
    });
    return () => subscription.unsubscribe();
    // deps intentionally drives re-subscription, same contract as useEffect's own array.
  }, deps);

  return value;
}
