import { useEffect, useState } from "react";

type Health = {
  version: string;
};

type Status =
  | { state: "loading" }
  | { state: "ready"; version: string }
  | { state: "unreachable" };

export default function App() {
  const [status, setStatus] = useState<Status>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth(): Promise<void> {
      try {
        const response = await fetch("/api/health", { signal: controller.signal });
        if (!response.ok) {
          setStatus({ state: "unreachable" });
          return;
        }
        const health = (await response.json()) as Health;
        setStatus({ state: "ready", version: health.version });
      } catch {
        if (controller.signal.aborted) {
          return;
        }
        setStatus({ state: "unreachable" });
      }
    }

    void checkHealth();
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">ats-scanner</h1>
      <p className="mt-2">
        Compares a resume against a job description on your machine and shows the evidence.
      </p>
      <p className="mt-4 text-sm" role="status">
        {status.state === "loading" && "Checking backend…"}
        {status.state === "ready" && `Backend version ${status.version}`}
        {status.state === "unreachable" &&
          "Backend not reachable. Start it with `uv run ats` and reload."}
      </p>
    </main>
  );
}
