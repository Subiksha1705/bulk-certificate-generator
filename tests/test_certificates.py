import csv
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.zip_export import sanitize_csv_cell


def test_get_certificate_metadata_and_404(client: TestClient):
    """Test GET /api/certificates/{id} returns metadata and 404 on unknown ID."""
    # Create a job with 1 recipient
    payload = {
        "event_name": "API Design Masterclass",
        "event_date": "2026-10-10",
        "organization_name": "API Guild",
        "authorized_signatory": "Lead Architect",
        "recipients": [{"name": "Subiksha Ramesh", "email": "subiksha@example.com"}],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["job_id"]

    # List certificates to get the generated certificate_id
    list_resp = client.get(f"/api/jobs/{job_id}/certificates")
    assert list_resp.status_code == 200
    cert_id = list_resp.json()["certificates"][0]["certificate_id"]

    # Fetch metadata
    meta_resp = client.get(f"/api/certificates/{cert_id}")
    assert meta_resp.status_code == 200
    data = meta_resp.json()
    assert data["certificate_id"] == cert_id
    assert data["recipient_name"] == "Subiksha Ramesh"
    assert data["recipient_email"] == "subiksha@example.com"
    assert data["status"] == "SUCCESS"
    assert data["view_url"] == f"/api/certificates/{cert_id}/view"
    assert data["download_url"] == f"/api/certificates/{cert_id}/download"

    # 404 on unknown ID
    unknown_resp = client.get("/api/certificates/CERT-2026-UNKNOWN1")
    assert unknown_resp.status_code == 404


def test_view_certificate_inline_and_error_states(client: TestClient):
    """Test GET /api/certificates/{id}/view returns inline PDF and appropriate errors."""
    payload = {
        "event_name": "Cloud Security Workshop",
        "event_date": "2026-10-10",
        "organization_name": "Cyber Corp",
        "authorized_signatory": "SecOps Director",
        "recipients": [
            {"name": "Valid Student", "email": "valid@example.com"},
            {"name": "", "email": "invalid_email"},
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    list_resp = client.get(f"/api/jobs/{job_id}/certificates")
    certs = list_resp.json()["certificates"]
    success_cert_id = next(c["certificate_id"] for c in certs if c["status"] == "SUCCESS")
    failed_cert_id = next(c["certificate_id"] for c in certs if c["status"] == "FAILED")

    # 1. Successful view
    view_resp = client.get(f"/api/certificates/{success_cert_id}/view")
    assert view_resp.status_code == 200
    assert view_resp.headers["Content-Type"] == "application/pdf"
    assert view_resp.headers["Content-Disposition"] == "inline"
    assert view_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert view_resp.content.startswith(b"%PDF")

    # 2. 409 Conflict for non-SUCCESS cert
    failed_view = client.get(f"/api/certificates/{failed_cert_id}/view")
    assert failed_view.status_code == 409
    assert "status=FAILED" in failed_view.json()["detail"]

    # 3. 404 Not Found for unknown cert
    not_found_view = client.get("/api/certificates/CERT-2026-NONEXIST/view")
    assert not_found_view.status_code == 404


def test_download_certificate_attachment_and_sanitized_filename(client: TestClient):
    """Test GET /api/certificates/{id}/download returns attachment with sanitized slug."""
    payload = {
        "event_name": "DevOps Summit",
        "event_date": "2026-10-10",
        "organization_name": "DevOps Org",
        "authorized_signatory": "Chief Engineer",
        "recipients": [
            {"name": "Dr. Subiksha P. R. D'Souza-Ramesh", "email": "subiksha@example.com"}
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    list_resp = client.get(f"/api/jobs/{job_id}/certificates")
    cert_id = list_resp.json()["certificates"][0]["certificate_id"]

    download_resp = client.get(f"/api/certificates/{cert_id}/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["Content-Type"] == "application/pdf"
    assert download_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert download_resp.content.startswith(b"%PDF")

    # Verify attachment filename header format
    disp = download_resp.headers["Content-Disposition"]
    assert 'attachment; filename="Certificate_Dr-Subiksha-P-R-D-Souza-Ramesh_' in disp
    assert f"{cert_id}.pdf" in disp


def test_self_healing_regenerates_deleted_pdf(client: TestClient, tmp_path: Path):
    """Delete PDF file from disk; verify download/view still works and recreates identical file."""
    payload = {
        "event_name": "Self-Healing Test",
        "event_date": "2026-10-10",
        "organization_name": "Reliability Inc",
        "authorized_signatory": "Site Reliability Lead",
        "recipients": [{"name": "Resilient Recipient", "email": "resilient@example.com"}],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    list_resp = client.get(f"/api/jobs/{job_id}/certificates")
    cert_id = list_resp.json()["certificates"][0]["certificate_id"]

    # Initial download to get original bytes
    initial_resp = client.get(f"/api/certificates/{cert_id}/download")
    assert initial_resp.status_code == 200
    original_bytes = initial_resp.content

    # Target PDF file on disk
    pdf_file = tmp_path / job_id / f"{cert_id}.pdf"
    assert pdf_file.exists()

    # WIPE the file from disk!
    pdf_file.unlink()
    assert not pdf_file.exists()

    # Request download again -> triggers transparent self-healing
    healed_resp = client.get(f"/api/certificates/{cert_id}/download")
    assert healed_resp.status_code == 200
    assert healed_resp.content.startswith(b"%PDF")

    # File should reappear on disk
    assert pdf_file.exists()

    # Deterministic output: regenerated bytes must match original
    assert healed_resp.content == original_bytes


def test_job_download_all_zip_export(client: TestClient):
    """Verify GET /api/jobs/{job_id}/download-all produces valid ZIP with results.csv and PDFs."""
    payload = {
        "event_name": "Full Stack Workshop",
        "event_date": "2026-10-10",
        "organization_name": "Full Stack Academy",
        "authorized_signatory": "Dean of Studies",
        "recipients": [
            {"name": "Alice Johnson", "email": "alice@example.com"},
            {"name": "Bob Smith", "email": "bob@example.com"},
            {"name": "", "email": "invalid_email"},
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    zip_resp = client.get(f"/api/jobs/{job_id}/download-all")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["Content-Type"] == "application/zip"
    assert f'attachment; filename="{job_id}.zip"' in zip_resp.headers["Content-Disposition"]

    # Inspect ZIP contents
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        namelist = zf.namelist()
        assert "results.csv" in namelist
        assert len(namelist) == 3  # results.csv + 2 SUCCESS PDFs

        # Verify results.csv content
        csv_text = zf.read("results.csv").decode("utf-8")
        reader = list(csv.reader(io.StringIO(csv_text)))
        header = reader[0]
        assert header == [
            "row",
            "name",
            "email",
            "certificate_id",
            "status",
            "failure_type",
            "error_message",
        ]
        assert len(reader) == 4  # header + 3 rows

        # Verify PDF entries
        pdf_names = [name for name in namelist if name.endswith(".pdf")]
        assert len(pdf_names) == 2
        for pdf_name in pdf_names:
            pdf_data = zf.read(pdf_name)
            assert pdf_data.startswith(b"%PDF")


def test_job_download_all_errors_404_and_409(client: TestClient):
    """Verify download-all returns 404 for unknown job and 409 when 0 SUCCESS certificates exist."""
    # 1. 404 on unknown job
    resp_404 = client.get("/api/jobs/JOB-2026-UNKNOWN99/download-all")
    assert resp_404.status_code == 404

    # 2. 409 when job has only invalid recipients (0 SUCCESS)
    payload_invalid = {
        "event_name": "Broken Event",
        "event_date": "2026-10-10",
        "organization_name": "Broken Org",
        "authorized_signatory": "Signer",
        "recipients": [{"name": "", "email": "bad_email"}],
    }
    create_invalid = client.post("/api/jobs/", json=payload_invalid)
    invalid_job_id = create_invalid.json()["job_id"]

    resp_409 = client.get(f"/api/jobs/{invalid_job_id}/download-all")
    assert resp_409.status_code == 409
    assert "No successful certificates available" in resp_409.json()["detail"]


def test_sanitize_csv_cell_injection_defense():
    """Unit test for CSV formula injection protection."""
    assert sanitize_csv_cell("Normal Text") == "Normal Text"
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-2+3") == "'-2+3"
    assert sanitize_csv_cell("@SUM(1,2)") == "'@SUM(1,2)"
    assert sanitize_csv_cell("\tTabbed") == "'\tTabbed"
    assert sanitize_csv_cell("\rCarriage") == "'\rCarriage"
    assert sanitize_csv_cell(None) == ""
