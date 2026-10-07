from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CertificateStatus, FailureType
from app.models.job import utcnow

if TYPE_CHECKING:
    from app.models.job import GenerationJob


class Certificate(Base):
    """Represents an individual certificate within a bulk generation job."""

    __tablename__ = "certificates"

    certificate_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("generation_jobs.job_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, native_enum=False, length=20),
        nullable=False,
        default=CertificateStatus.PENDING,
    )
    failure_type: Mapped[FailureType | None] = mapped_column(
        Enum(FailureType, native_enum=False, length=20),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    job: Mapped["GenerationJob"] = relationship(
        "GenerationJob",
        back_populates="certificates",
    )

    __table_args__ = (Index("ix_certificates_job_id_status", "job_id", "status"),)
