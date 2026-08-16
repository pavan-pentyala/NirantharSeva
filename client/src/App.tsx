import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
  clock_mode: string;
  server_time: string;
  run_id: string | null;
};

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return res.json();
      })
      .then(setHealth)
      .catch((err) => setError(String(err)));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>NirantharSeva</h1>
      {error && <p style={{ color: "crimson" }}>API error: {error}</p>}
      {!error && !health && <p>Checking API…</p>}
      {health && (
        <ul>
          <li>status: {health.status}</li>
          <li>clock mode: {health.clock_mode}</li>
          <li>server time: {health.server_time}</li>
        </ul>
      )}
    </main>
  );
}
