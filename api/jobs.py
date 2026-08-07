"""In-memory job store for Phase 1. One process; jobs are lost on restart.
Swap for Redis/DB at productionization without changing this interface."""

import uuid
from dataclasses import dataclass


@dataclass
class Job:
    id: str
    status: str = "running"  # "running" | "done" | "failed"
    cv: str | None = None
    error: str | None = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self) -> Job:
        job = Job(id=uuid.uuid4().hex)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def mark_done(self, job_id: str, cv: str) -> None:
        job = self._jobs[job_id]
        job.status, job.cv = "done", cv

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self._jobs[job_id]
        job.status, job.error = "failed", error
