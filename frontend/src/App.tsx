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
    if (
      !downloaded &&
      !window.confirm("Rerunning will discard this draft. Download it first?")
    ) {
      return;
    }
    setPhase("idle");
    setResult("");
    setDownloaded(false);
  }

  return (
    <main>
      <h1>CV Improver</h1>

      <label>
        Your CV
        <input type="file" onChange={(e) => setCv(e.target.files?.[0] ?? null)} />
      </label>
      <label>
        Job description
        <input type="file" onChange={(e) => setJd(e.target.files?.[0] ?? null)} />
      </label>

      <button onClick={improve} disabled={!cv || !jd || phase === "running"}>
        Improve my CV
      </button>

      {phase === "running" && <p>Improving your CV — this takes a couple of minutes…</p>}
      {phase === "failed" && <p role="alert">{error}</p>}
      {phase === "done" && (
        <>
          <pre>{result}</pre>
          <button onClick={download}>Download</button>
          <button onClick={rerun}>Rerun</button>
        </>
      )}
    </main>
  );
}
