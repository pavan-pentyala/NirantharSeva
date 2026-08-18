import { useEffect, useState } from "react";
import { login } from "../api/client";
import { db } from "../db/schema";
import { getLastSyncAt } from "../db/meta";
import { createOp, startAutoFlush } from "../sync/engine";

// Fixed entity for this throwaway harness — no UI for picking an entity,
// the point is to exercise the sync engine, not to be a real screen.
const ENTITY_ID = "00000000-0000-0000-0000-000000000001";

export default function ToyPage() {
  const [ready, setReady] = useState(false);
  const [input, setInput] = useState("");
  const [cachedValue, setCachedValue] = useState<number | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [online, setOnline] = useState(navigator.onLine);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);

  useEffect(() => {
    let stop: (() => void) | undefined;
    (async () => {
      // Dev-only auto-login (asha_a/dev — server/app/seed.py's D4 fixture).
      // Real auth UI is out of scope until the real screens land in Phase 4.
      await login("asha_a", "dev");
      stop = startAutoFlush();
      setReady(true);
    })();
    return () => stop?.();
  }, []);

  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  // Reads only from the local cache (handoff §8) — polling it is a stand-in
  // for a live query, kept deliberately simple for a throwaway harness.
  useEffect(() => {
    const timer = setInterval(() => {
      void (async () => {
        const cached = await db.toy_cache.get(ENTITY_ID);
        setCachedValue(cached ? cached.value : null);
        const pending = await db.outbox.where("status").anyOf("pending", "inflight").count();
        setPendingCount(pending);
        setLastSyncAt(await getLastSyncAt());
      })();
    }, 500);
    return () => clearInterval(timer);
  }, []);

  async function handleSave() {
    const n = Number(input);
    if (Number.isNaN(n)) return;
    await createOp(ENTITY_ID, n);
    setInput("");
  }

  return (
    <section style={{ marginTop: "2rem", borderTop: "1px solid #ccc", paddingTop: "1rem" }}>
      <h2>Sync engine harness</h2>
      <p data-testid="status-line">
        <span data-testid="online-state">{online ? "online" : "offline"}</span> ·{" "}
        <span data-testid="pending-count">{pendingCount}</span> pending ·{" "}
        {lastSyncAt ? `last sync ${new Date(lastSyncAt).toLocaleTimeString()}` : "never synced"}
      </p>
      <p data-testid="cached-value">
        cached value: {cachedValue === null ? "(none yet)" : cachedValue}
      </p>
      <input
        data-testid="value-input"
        type="number"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        disabled={!ready}
        placeholder="value"
      />
      <button data-testid="save-button" onClick={handleSave} disabled={!ready}>
        Save
      </button>
    </section>
  );
}
