export type JobStatus = {
  status: "running" | "done" | "failed";
  error: string | null;
};

export async function submitJob(cv: File, jd: File): Promise<string> {
  const form = new FormData();
  form.append("cv", cv);
  form.append("jd", jd);
  const res = await fetch("/jobs", { method: "POST", body: form });
  const body = await res.json();
  return body.job_id;
}

export async function getJob(id: string): Promise<JobStatus> {
  const res = await fetch(`/jobs/${id}`);
  return res.json();
}

export async function getCv(id: string): Promise<string> {
  const res = await fetch(`/jobs/${id}/cv`);
  return res.text();
}
