from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_storage
from app.models.enums import CertificateStatus
from app.schemas.certificate import CertificateOut
from app.services import certificate_service
from app.services.storage import PdfStorage

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.get(
    "/{certificate_id}",
    response_model=CertificateOut,
    summary="Get certificate metadata",
)
def get_certificate_metadata_endpoint(
    certificate_id: str,
    db: Session = Depends(get_db),
) -> CertificateOut:
    """Retrieve metadata and download/view links for a specific certificate."""
    cert = certificate_service.get_certificate_by_id(db, certificate_id)
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found",
        )
    return CertificateOut.from_certificate_model(cert)


@router.get(
    "/{certificate_id}/view",
    summary="View certificate PDF inline in browser",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Certificate PDF rendered inline",
        },
        404: {"description": "Certificate not found"},
        409: {"description": "Certificate is not in SUCCESS state"},
    },
)
def view_certificate_endpoint(
    certificate_id: str,
    db: Session = Depends(get_db),
    storage: PdfStorage = Depends(get_storage),
) -> Response:
    """Display the certificate PDF inline in browser."""
    cert = certificate_service.get_certificate_by_id(db, certificate_id)
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found",
        )

    if cert.status != CertificateStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Certificate is not available (status={cert.status.value})",
        )

    pdf_bytes = certificate_service.get_or_regenerate_pdf(db=db, cert=cert, storage=storage)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{certificate_id}/download",
    summary="Download certificate PDF attachment",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Certificate PDF file attachment",
        },
        404: {"description": "Certificate not found"},
        409: {"description": "Certificate is not in SUCCESS state"},
    },
)
def download_certificate_endpoint(
    certificate_id: str,
    db: Session = Depends(get_db),
    storage: PdfStorage = Depends(get_storage),
) -> Response:
    """Download the certificate PDF file with sanitized attachment filename."""
    cert = certificate_service.get_certificate_by_id(db, certificate_id)
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found",
        )

    if cert.status != CertificateStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Certificate is not available (status={cert.status.value})",
        )

    pdf_bytes = certificate_service.get_or_regenerate_pdf(db=db, cert=cert, storage=storage)
    slug = certificate_service.slugify_recipient_name(cert.recipient_name)
    filename = f"Certificate_{slug}_{cert.certificate_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
