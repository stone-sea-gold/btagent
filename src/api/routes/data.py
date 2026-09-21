"""Data coverage and sync API routes.

Coverage answers "how fresh is the local data?"; sync starts the pipeline that
makes it fresher. Sync runs in the background because it takes minutes — the
request returns a job id and the UI polls it.
"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.core.sync_jobs import manager
from src.exceptions import DataSourceError
from src.tools.data_tools import check_data_coverage

router = APIRouter()


class SyncRequest(BaseModel):
    index: str = ""
    codes: str = ""
    years: int = settings.years_sync_default
    source: str = ""


@router.get("/coverage")
def check_coverage_endpoint():
    """Latest dates held by the warehouse and by the backtest dataset."""
    result = check_data_coverage()
    return json.loads(result) if isinstance(result, str) else result


@router.post("/sync")
def start_sync(req: SyncRequest):
    """Start a background sync (then re-export); poll ``/sync/{job_id}``."""
    requested = [code.strip() for code in req.codes.split(",") if code.strip()]
    try:
        job = manager.start(
            index=req.index,
            codes=requested,
            years=req.years,
            source=req.source,
        )
    except DataSourceError as exc:
        # A running job is a conflict; an unknown source is a bad request.
        status = 409 if exc.details.get("job_id") else 400
        raise HTTPException(status_code=status, detail=exc.message) from exc
    return job.snapshot()


# Declared before ``/sync/{job_id}`` so "latest" is not read as a job id.
@router.get("/sync/latest")
def latest_sync():
    """The newest job, so a reloaded page can resume polling."""
    job = manager.latest()
    return job.snapshot() if job else {"status": "none"}


@router.get("/sync/{job_id}")
def sync_status(job_id: str):
    """Progress of one job."""
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"未知任务 {job_id}")
    return job.snapshot()
