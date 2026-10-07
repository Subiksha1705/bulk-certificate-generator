from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import CertificateStatus
from app.schemas.certificate import CertificateListOut, CertificateOut
from app.schemas.job import JobCreate, JobCreateResponse, JobOut
from app.services import job_service

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
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """
    Submit a bulk certificate generation request.
    Returns HTTP 202 for new jobs and HTTP 200 for idempotent re-submissions.
    """
    job, created = job_service.create_job(db, payload)
    if not created:
        response.status_code = status.HTTP_200_OK

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
