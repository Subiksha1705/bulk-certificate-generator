import os
import tempfile
from pathlib import Path


class StorageSecurityError(Exception):
    """Raised when a storage path attempts to escape the root storage directory."""


class PdfStorage:
    """Thread-safe local filesystem storage for certificate PDF binaries."""

    def __init__(self, root_dir: Path | str = "./storage") -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Resolve path and assert it does not escape the configured root."""
        clean_rel = relative_path.lstrip("/\\")
        target_path = (self.root / clean_rel).resolve()
        try:
            target_path.relative_to(self.root)
        except ValueError as exc:
            raise StorageSecurityError(f"Path traversal detected: '{relative_path}'") from exc
        return target_path

    def save(self, job_id: str, cert_id: str, data: bytes) -> str:
        """
        Atomically write PDF binary to disk.
        Writes to a temporary file in the destination folder first, then atomically replaces.
        Returns the safe relative path, e.g. 'JOB-2026-XXXX/CERT-2026-YYYY.pdf'.
        """
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        final_path = job_dir / f"{cert_id}.pdf"
        rel_path = f"{job_id}/{cert_id}.pdf"

        # Atomic write: write to temp file then replace
        with tempfile.NamedTemporaryFile(dir=job_dir, delete=False) as temp_file:
            temp_file.write(data)
            temp_path = Path(temp_file.name)

        os.replace(temp_path, final_path)
        return rel_path

    def read(self, relative_path: str) -> bytes | None:
        """Read PDF binary from storage. Returns None if file does not exist."""
        path = self._resolve_safe_path(relative_path)
        if not path.is_file():
            return None
        return path.read_bytes()

    def exists(self, relative_path: str) -> bool:
        """Check whether a file exists in storage."""
        try:
            path = self._resolve_safe_path(relative_path)
            return path.is_file()
        except StorageSecurityError:
            return False

    def delete(self, relative_path: str) -> bool:
        """Delete a file from storage if present."""
        try:
            path = self._resolve_safe_path(relative_path)
            if path.is_file():
                path.unlink()
                return True
            return False
        except StorageSecurityError:
            return False
