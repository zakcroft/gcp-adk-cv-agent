import { useState } from "react";
import { getCv, getJob, submitJob } from "./api";

type Phase = "idle" | "running" | "done" | "failed";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function App({ pollMs = 2000 }: { pollMs?: number }) {
  const [cv, setCv] = useState<File | null>(null);
  const [jd, setJd] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [downloaded, setDownloaded] = useState(false);

  async function improve() {
    if (!cv || !jd) return;
    setPhase("running");
    setError("");
    setResult("");
    setDownloaded(false);
    const id = await submitJob(cv, jd);
    while (true) {
      const s = await getJob(id);
      if (s.status === "done") {
        setResult(await getCv(id));
        setPhase("done");
        return;
      }
      if (s.status === "failed") {
        setError(s.error ?? "Something went wrong.");
        setPhase("failed");
        return;
      }
      await sleep(pollMs);
    }
  }

  function download() {
    const blob = new Blob([result], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "improved_cv.md";
    a.click();
    URL.revokeObjectURL(url);
    setDownloaded(true);
  }

  function rerun() {
    // Rerunning throws away the current draft. If it hasn't been
    // downloaded yet, check the user is willing to lose it first.
    if (!downloaded) {
      const discardAnyway = window.confirm(
        "Rerunning will discard this draft. Continue without downloading?",
      );
      if (!discardAnyway) return;
    }

    setPhase("idle");
    setResult("");
    setDownloaded(false);
  }

  const running = phase === "running";

  return (
    <div className="app">
      <header className="masthead">
        <h1 className="brand">CV Improver</h1>
        <p className="tagline">Tailor your CV to a role — without inventing anything.</p>
      </header>

      {(phase === "idle" || running) && (
        <section className="panel">
          <div className="fields">
            <label className="field">
              <span className="field-label">Your CV</span>
              <input
                className="field-input"
                type="file"
                disabled={running}
                onChange={(e) => setCv(e.target.files?.[0] ?? null)}
              />
              <span className={cv ? "field-pick chosen" : "field-pick"}>
                {cv ? cv.name : "Choose a text file…"}
              </span>
            </label>

            <label className="field">
              <span className="field-label">Job description</span>
              <input
                className="field-input"
                type="file"
                disabled={running}
                onChange={(e) => setJd(e.target.files?.[0] ?? null)}
              />
              <span className={jd ? "field-pick chosen" : "field-pick"}>
                {jd ? jd.name : "Choose a text file…"}
              </span>
            </label>
          </div>

          <button className="btn btn-primary" onClick={improve} disabled={!cv || !jd || running}>
            {running ? "Working…" : "Improve my CV"}
          </button>

          {running && (
            <div className="working">
              <span className="dots">
                <i />
                <i />
                <i />
              </span>
              Improving your CV — this takes a couple of minutes…
            </div>
          )}
        </section>
      )}

      {phase === "failed" && (
        <section className="panel">
          <p className="notice error" role="alert">
            {error}
          </p>
          <button className="btn btn-ghost" onClick={() => setPhase("idle")}>
            Try again
          </button>
        </section>
      )}

      {phase === "done" && (
        <section className="result">
          <article className="sheet">
            <pre>{result}</pre>
          </article>
          <div className="actions">
            <button className="btn btn-accent" onClick={download}>
              Download
            </button>
            <button className="btn btn-ghost" onClick={rerun}>
              Rerun
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
