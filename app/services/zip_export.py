import csv
import io
import tempfile
import zipfile

from sqlalchemy.orm import Session

from app.models.enums import CertificateStatus
from app.models.job import GenerationJob
from app.services.certificate_service import get_or_regenerate_pdf, slugify_recipient_name
from app.services.storage import PdfStorage

# Disallowed leading characters for CSV injection defense
INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: str | None) -> str:
    """
    Sanitize text cell against CSV formula injection.
    Prefixes cells starting with formula triggers (=, +, -, @, \t, \r) with an apostrophe.
    """
    if value is None:
        return ""
    text = str(value)
    if text.startswith(INJECTION_PREFIXES):
        return f"'{text}"
    return text


def create_job_zip(
    db: Session,
    job: GenerationJob,
    storage: PdfStorage,
) -> tempfile.SpooledTemporaryFile:
    """
    Construct a streaming-ready ZIP archive for a job in a SpooledTemporaryFile.
    Includes results.csv and all SUCCESS PDFs (self-healing missing files).
    Raises ValueError if job has zero SUCCESS certificates.
    """
    certs = sorted(job.certificates, key=lambda c: c.row_number)
    success_certs = [c for c in certs if c.status == CertificateStatus.SUCCESS]

    if not success_certs:
        raise ValueError("No successful certificates available for download")

    spooled_file = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024, mode="w+b")

    with zipfile.ZipFile(spooled_file, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_archive:
        # 1. Generate and attach results.csv
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer, quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(
            [
                "row",
                "name",
                "email",
                "certificate_id",
                "status",
                "failure_type",
                "error_message",
            ]
        )

        for cert in certs:
            csv_writer.writerow(
                [
                    cert.row_number,
                    sanitize_csv_cell(cert.recipient_name),
                    sanitize_csv_cell(cert.recipient_email),
                    cert.certificate_id,
                    cert.status.value,
                    cert.failure_type.value if cert.failure_type else "",
                    sanitize_csv_cell(cert.error_message),
                ]
            )

        zip_archive.writestr("results.csv", csv_buffer.getvalue().encode("utf-8"))

        # 2. Attach each SUCCESS certificate PDF
        for cert in success_certs:
            pdf_bytes = get_or_regenerate_pdf(db=db, cert=cert, storage=storage)
            slug = slugify_recipient_name(cert.recipient_name)
            filename = f"{cert.row_number:04d}_{slug}_{cert.certificate_id}.pdf"
            zip_archive.writestr(filename, pdf_bytes)

    spooled_file.seek(0)
    return spooled_file
