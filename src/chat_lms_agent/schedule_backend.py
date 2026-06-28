from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


@dataclass(frozen=True, slots=True)
class ScheduledAction:
    argv: tuple[str, ...]
    env: dict[str, str]


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    job_id: str
    job_name: str
    trigger: dict[str, JsonValue]
    action: ScheduledAction


class TaskSchedulerBackend(Protocol):
    def upsert_job(self, job: ScheduledJob) -> None:
        """Create or update one scheduled task."""
        ...

    def remove_job(self, job_name: str) -> bool:
        """Remove one scheduled task by backend name."""
        ...

    def list_jobs(self) -> list[ScheduledJob]:
        """List jobs known to the backend seam."""
        ...


@dataclass(slots=True)
class FakeBackend:
    jobs: dict[str, ScheduledJob] = field(default_factory=dict)
    calls: list[dict[str, JsonValue]] = field(default_factory=list)

    def upsert_job(self, job: ScheduledJob) -> None:
        """Record an upsert without touching the operating system."""
        self.calls.append({"op": "upsert", "job_name": job.job_name, "job_id": job.job_id})
        self.jobs[job.job_name] = job

    def remove_job(self, job_name: str) -> bool:
        """Record a removal without touching the operating system."""
        self.calls.append({"op": "remove", "job_name": job_name})
        return self.jobs.pop(job_name, None) is not None

    def list_jobs(self) -> list[ScheduledJob]:
        """Return fake jobs in deterministic order."""
        self.calls.append({"op": "list"})
        return [self.jobs[name] for name in sorted(self.jobs)]
