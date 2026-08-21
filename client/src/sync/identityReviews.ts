import { listIdentityReviews } from "../api/client";
import { db } from "../db/schema";

/** Fetches the current pending queue and writes it wholesale into Dexie —
 * the server always returns the full current set, not a diff (same shape
 * as P5.2's dashboard_overdue_cache), so this clears and rewrites rather
 * than patching. Called on mount and again after every decide() — ADR-013:
 * decisions POST directly, then refetch, never optimistically update the
 * cache, since a stale queue here is exactly the risk the ADR exists to
 * avoid. */
export async function refreshIdentityReviews(): Promise<void> {
  const reviews = await listIdentityReviews();
  await db.transaction("rw", db.identity_review_cache, async () => {
    await db.identity_review_cache.clear();
    await db.identity_review_cache.bulkPut(reviews);
  });
}
