import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";

import type { AnalysisReport, ErrorEnvelope, Health } from "./api/types";

const MAX_FILE_BYTES = 5 * 1024 * 1024; // convenience mirror of the server limit

const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

type BackendStatus =
  | { state: "checking" }
  | { state: "ready"; version: string }
  | { state: "unreachable" };

type Phase =
  | { state: "idle" }
  | { state: "analyzing" }
  | { state: "report"; report: AnalysisReport }
  | { state: "error"; message: string };

export default function App() {
  const [backend, setBackend] = useState<BackendStatus>({ state: "checking" });
  const [phase, setPhase] = useState<Phase>({ state: "idle" });
  const [file, setFile] = useState<File | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  const alertRef = useRef<HTMLParagraphElement>(null);

  // /api/health on load: the status line stays from the Day 1 shell.
  useEffect(() => {
    const controller = new AbortController();
    async function checkHealth(): Promise<void> {
      try {
        const response = await fetch("/api/health", { signal: controller.signal });
        if (!response.ok) {
          setBackend({ state: "unreachable" });
          return;
        }
        const health = (await response.json()) as Health;
        setBackend({ state: "ready", version: health.version });
      } catch {
        if (!controller.signal.aborted) {
          setBackend({ state: "unreachable" });
        }
      }
    }
    void checkHealth();
    return () => {
      controller.abort();
    };
  }, []);

  // Elapsed timer while analyzing (SPEC §2: indeterminate state, no fake progress).
  const analyzing = phase.state === "analyzing";
  useEffect(() => {
    if (!analyzing) {
      return;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 250);
    return () => {
      window.clearInterval(timer);
    };
  }, [analyzing]);

  // Move focus to the result or the error after submit (SPEC §2 accessibility).
  useEffect(() => {
    if (phase.state === "report") {
      resultHeadingRef.current?.focus();
    } else if (phase.state === "error") {
      alertRef.current?.focus();
    }
  }, [phase]);

  function pickFile(next: File | null): void {
    setFile(next);
    if (phase.state !== "idle") {
      setPhase({ state: "idle" });
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    const dropped = event.dataTransfer.files[0];
    if (dropped !== undefined) {
      pickFile(dropped);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (file === null) {
      setPhase({
        state: "error",
        message: "Choose a PDF or DOCX file first.",
      });
      return;
    }
    // Convenience checks only: the server decides, and the same problems are
    // handled there too when the client check cannot hoodwink-proof the file.
    if (file.size > MAX_FILE_BYTES) {
      setPhase({
        state: "error",
        message: "That file is larger than the 5 MB limit. Try a smaller file.",
      });
      return;
    }
    if (!/\.(pdf|docx)$/i.test(file.name)) {
      setPhase({
        state: "error",
        message: "That does not look like a PDF or DOCX file.",
      });
      return;
    }

    setElapsedMs(0);
    setPhase({ state: "analyzing" });
    const controller = new AbortController();
    try {
      const form = new FormData();
      form.append("resume", file);
      const response = await fetch("/api/analyze", {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      if (!response.ok) {
        const fallback = `The server could not process the file (status ${response.status}). Try again.`;
        try {
          const body = (await response.json()) as Partial<ErrorEnvelope>;
          const serverMessage = body.message;
          setPhase({
            state: "error",
            message:
              typeof serverMessage === "string" && serverMessage
                ? serverMessage
                : fallback,
          });
        } catch {
          setPhase({ state: "error", message: fallback });
        }
        return;
      }
      const report = (await response.json()) as AnalysisReport;
      setPhase({ state: "report", report });
    } catch {
      setPhase({
        state: "error",
        message:
          "Backend not reachable. Start it with `uv run ats` and try again. Nothing was sent anywhere.",
      });
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">ats-scanner</h1>
      <p className="mt-1">
        Compares a resume against a job description on your machine and shows the
        evidence.
      </p>
      <p className="mt-2 text-sm" role="status">
        {backend.state === "checking" && "Checking backend…"}
        {backend.state === "ready" && `Backend version ${backend.version}`}
        {backend.state === "unreachable" &&
          "Backend not reachable. Start it with `uv run ats` and reload."}
      </p>

      <form onSubmit={(event) => void submit(event)} className="mt-6">
        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={onDrop}
          className="rounded border border-dashed border-gray-400 p-6"
        >
          <label htmlFor="resume-file" className="block font-medium">
            Resume: one PDF or DOCX file
          </label>
          <input
            id="resume-file"
            name="resume"
            type="file"
            accept={ACCEPT}
            className="mt-2 block cursor-pointer"
            onChange={(event) => pickFile(event.target.files?.[0] ?? null)}
          />
          <p className="mt-2 text-sm">You can also drop the file here.</p>
        </div>

        <p className="mt-2 text-sm">
          Maximum size: 5 MB. {file !== null && `${file.name}, ${Math.ceil(file.size / 1024)} KB`}
        </p>
        <p className="mt-1 text-sm">
          Your resume is processed on this computer and is not saved.
        </p>

        <button
          type="submit"
          disabled={analyzing}
          className="mt-4 rounded border px-4 py-2 font-medium disabled:opacity-50"
        >
          Analyze locally
        </button>
      </form>

      <p
        ref={alertRef}
        role="alert"
        tabIndex={-1}
        className={
          phase.state === "error"
            ? "mt-4 rounded border p-3 text-sm focus:outline-2"
            : "hidden"
        }
      >
        {phase.state === "error" ? phase.message : ""}
      </p>
      {analyzing && (
        <p className="mt-4 text-sm" aria-live="polite">
          Analyzing locally… {Math.floor(elapsedMs / 1000)} s
        </p>
      )}

      {phase.state === "report" && (
        <section className="mt-8">
          <h2
            ref={resultHeadingRef}
            tabIndex={-1}
            className="focus:outline-2"
          >
            What the ATS sees
          </h2>
          <p className="mt-1 text-sm italic">
            Plain-text extraction, the way many parsers read a file. Real systems
            differ.
          </p>
          <p className="mt-2 text-sm">
            {phase.report.meta.filename} · {phase.report.meta.page_count}{" "}
            {phase.report.meta.page_count === 1 ? "page" : "pages"} ·{" "}
            {phase.report.meta.method} ·{" "}
            {phase.report.extracted_text.char_count.toLocaleString()} characters ·{" "}
            {phase.report.meta.duration_ms} ms
          </p>
          {/* column_text is intentionally not rendered yet (Day 3 shows both orders). */}
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded border p-4 font-mono text-xs">
            {phase.report.extracted_text.pages
              .map((page) => `Page ${page.page_number}\n${page.row_text}`)
              .join("\n\n")}
          </pre>
        </section>
      )}
    </main>
  );
}
