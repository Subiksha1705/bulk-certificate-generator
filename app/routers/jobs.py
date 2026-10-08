from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.dependencies import get_session_factory, get_storage
from app.models.enums import CertificateStatus, JobStatus
from app.schemas.certificate import CertificateListOut, CertificateOut
from app.schemas.job import JobCreate, JobCreateResponse, JobOut
from app.services import job_service
from app.services.job_processor import process_job
from app.services.storage import PdfStorage
from app.services.zip_export import create_job_zip

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "/",
    response_model=JobCreateResponse,
    summary="Create a bulk certificate generation job",
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job_endpoint(
    payload: JobCreate,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> JobCreateResponse:
    """
    Submit a bulk certificate generation request.
    Returns HTTP 202 for new jobs and HTTP 200 for idempotent re-submissions.
    """
    job, created = job_service.create_job(db, payload)
    if not created:
        response.status_code = status.HTTP_200_OK
    elif job.status != JobStatus.FAILED:
        # Schedule background generation if there is at least one valid recipient
        background_tasks.add_task(process_job, job.job_id, session_factory)

    return JobCreateResponse.from_job_model(job, idempotent_replay=not created)


@router.get(
    "/{job_id}",
    response_model=JobOut,
    summary="Get job details and generation progress",
)
def get_job_endpoint(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobOut:
    """Retrieve the current progress and status of a batch certificate generation job."""
    job = job_service.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return JobOut.from_job_model(job)


@router.get(
    "/{job_id}/certificates",
    response_model=CertificateListOut,
    summary="List certificates for a job",
)
def list_job_certificates_endpoint(
    job_id: str,
    status_filter: CertificateStatus | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CertificateListOut:
    """Retrieve a paginated list of certificates for a job, optionally filtered by status."""
    job = job_service.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    total, certs = job_service.list_certificates(
        db=db,
        job_id=job_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    return CertificateListOut(
        job_id=job_id,
        total=total,
        limit=limit,
        offset=offset,
        certificates=[CertificateOut.from_certificate_model(c) for c in certs],
    )


@router.get(
    "/{job_id}/download-all",
    summary="Download all successful certificates and results CSV as a ZIP archive",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "ZIP archive containing results.csv and all SUCCESS PDFs",
        },
        404: {"description": "Job not found"},
        409: {"description": "No successful certificates available"},
    },
)
def download_all_job_certificates_endpoint(
    job_id: str,
    db: Session = Depends(get_db),
    storage: PdfStorage = Depends(get_storage),
) -> StreamingResponse:
    """Stream a ZIP archive containing all generated certificates and results.csv."""
    job = job_service.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    try:
        spooled_zip = create_job_zip(db=db, job=job, storage=storage)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    def iter_file(file_obj, chunk_size=64 * 1024):
        try:
            while chunk := file_obj.read(chunk_size):
                yield chunk
        finally:
            file_obj.close()

    filename = f"{job.job_id}.zip"
    return StreamingResponse(
        iter_file(spooled_zip),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
