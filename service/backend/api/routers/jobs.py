"""Job submission, status, and result endpoints."""

from __future__ import annotations

import uuid
import asyncio

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_job_manager
from api.schemas import JobCreate, JobCreateResponse, JobStatusResponse
from api.services import JobManager, make_vllm_client
from api.settings import Settings, get_settings
from shared.youtube import extract_video_id
from worker.steps import collect, filter_comments, load_filter_config, make_gemini_client, summarize

router = APIRouter(prefix="/jobs", tags=["jobs"])


_arq_pool: ArqRedis | None = None
_direct_meta: dict[str, dict] = {}
_direct_result: dict[str, dict] = {}


def _set_direct_status(job_id: str, status_value: str, progress: float = 0.0, error: dict | None = None) -> None:
    _direct_meta[job_id] = {
        "status": status_value,
        "progress": float(progress),
        "error": error,
    }


async def _run_direct_pipeline(job_id: str, video_url: str, settings: Settings) -> None:
    try:
        gemini_client = make_gemini_client(settings.GCP_PROJECT, settings.GCP_LOCATION)
        gemini_model, gemini_gen_config = load_filter_config(settings.FILTER_CONFIG_PATH)
        backend = settings.INFERENCE_BACKEND.lower()
        vllm_client = make_vllm_client(settings.VLLM_BASE_URL, settings.VLLM_API_KEY) if backend == "vllm" else None

        _set_direct_status(job_id, "collecting", 0.1)
        record = await collect(
            video_url,
            settings.COLLECT_MAX_REGULAR,
            settings.COLLECT_MAX_TIMESTAMP,
        )

        _set_direct_status(job_id, "filtering", 0.4)
        record = await filter_comments(record, gemini_client, gemini_model, gemini_gen_config)

        _set_direct_status(job_id, "summarizing", 0.75)
        result = await summarize(
            record,
            vllm_client,
            settings.VLLM_MODEL_NAME,
            inference_backend=backend,
            local_model_path=settings.LOCAL_MODEL_PATH,
        )
        _direct_result[job_id] = result
        _set_direct_status(job_id, "done", 1.0)
    except Exception as e:  # noqa: BLE001
        _set_direct_status(
            job_id,
            "failed",
            1.0,
            {"code": "direct_pipeline_error", "message": str(e)},
        )


async def _get_arq(settings: Settings) -> ArqRedis:
    """Lazily build the arq Redis pool from REDIS_URL."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return _arq_pool


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    payload: JobCreate,
    settings: Settings = Depends(get_settings),
    jm: JobManager = Depends(get_job_manager),
) -> JobCreateResponse:
    video_id = extract_video_id(str(payload.url))
    if not video_id:
        raise HTTPException(status_code=400, detail="Could not parse YouTube video ID from URL.")

    if settings.DIRECT_MODE:
        job_id = f"direct-{uuid.uuid4().hex}"
        _set_direct_status(job_id, "queued", 0.0)
        asyncio.create_task(_run_direct_pipeline(job_id, str(payload.url), settings))
        return JobCreateResponse(job_id=job_id, cached=False)

    cached = await jm.lookup_cache(video_id)
    if cached:
        cached_job_id, cached_payload = cached
        return JobCreateResponse(job_id=cached_job_id, cached=True, result=cached_payload)

    job_id = uuid.uuid4().hex
    await jm.create(job_id)

    arq = await _get_arq(settings)
    await arq.enqueue_job("run_pipeline", job_id=job_id, video_url=str(payload.url))

    return JobCreateResponse(job_id=job_id, cached=False)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_status(
    job_id: str,
    jm: JobManager = Depends(get_job_manager),
) -> JobStatusResponse:
    if job_id.startswith("direct-"):
        meta = _direct_meta.get(job_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return JobStatusResponse(
            job_id=job_id,
            status=meta["status"],
            progress=meta.get("progress", 0.0),
            error=meta.get("error"),
        )

    meta = await jm.get_status(job_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatusResponse(
        job_id=job_id,
        status=meta["status"],
        progress=meta.get("progress", 0.0),
        error=meta.get("error"),
    )


@router.get("/{job_id}/result")
async def get_result(
    job_id: str,
    jm: JobManager = Depends(get_job_manager),
) -> dict:
    if job_id.startswith("direct-"):
        result = _direct_result.get(job_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Result not found or not ready.")
        return result

    result = await jm.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found or not ready.")
    return result
