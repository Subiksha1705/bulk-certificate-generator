#!/usr/bin/env python3
"""
Live end-to-end verification script for Phase 6.
Tests job submission, retrieval, view, download, ZIP export, and disk wipe self-healing.
"""

import io
import shutil
import sys
import zipfile
from pathlib import Path

# Ensure app is in Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def run_phase6_live_demo():
    print("=" * 60)
    print("   LIVE PHASE 6 VERIFICATION & SELF-HEALING TEST")
    print("=" * 60)

    client = TestClient(app)
    settings = get_settings()
    storage_path = Path(settings.STORAGE_DIR)

    # 1. Submit a batch job
    print("\n[1] Submitting bulk certificate job (POST /api/jobs/)...")
    payload = {
        "event_name": "Full-Stack AI Engineering Workshop",
        "event_date": "2026-10-15",
        "organization_name": "TechCraft Innovations",
        "authorized_signatory": "Dr. Aris Thorne",
        "recipients": [
            {"name": "Subiksha Ramesh", "email": "subiksha@example.com"},
            {"name": "Aarav Sharma", "email": "aarav@example.com"},
            {"name": "", "email": "invalid.email@"},  # Invalid intake
        ],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202, f"Expected 202, got {resp.status_code}"
    job_data = resp.json()
    job_id = job_data["job_id"]
    print(f"    -> Job created: {job_id} (status: {job_data['status']})")

    # 2. Check Job status
    print(f"\n[2] Checking job progress (GET /api/jobs/{job_id})...")
    get_resp = client.get(f"/api/jobs/{job_id}")
    job_info = get_resp.json()
    print(f"    -> Status: {job_info['status']}")
    print(f"    -> Total: {job_info['total']} | Processed: {job_info['processed']}")
    print(f"    -> Successful: {job_info['successful']} | Failed: {job_info['failed']}")
    print(f"    -> Progress: {job_info['progress_percentage']}%")

    # 3. List certificates
    print(f"\n[3] Listing certificates (GET /api/jobs/{job_id}/certificates)...")
    list_resp = client.get(f"/api/jobs/{job_id}/certificates")
    certs = list_resp.json()["certificates"]
    for c in certs:
        name_str = c["recipient_name"] or "[No Name]"
        print(
            f"    - Cert ID: {c['certificate_id']} | Row {c['row_number']} | "
            f"{name_str} -> {c['status']}"
        )

    success_certs = [c for c in certs if c["status"] == "SUCCESS"]
    test_cert = success_certs[0]
    cert_id = test_cert["certificate_id"]

    # 4. Test View Endpoint (inline PDF)
    print(f"\n[4] Testing inline view (GET /api/certificates/{cert_id}/view)...")
    view_resp = client.get(f"/api/certificates/{cert_id}/view")
    assert view_resp.status_code == 200
    assert view_resp.headers["Content-Type"] == "application/pdf"
    assert view_resp.headers["Content-Disposition"] == "inline"
    assert view_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert view_resp.content.startswith(b"%PDF")
    print(f"    -> Received {len(view_resp.content):,} bytes of valid PDF (%PDF header verified)")

    # 5. Test Download Endpoint (attachment)
    print(f"\n[5] Testing attachment download (GET /api/certificates/{cert_id}/download)...")
    down_resp = client.get(f"/api/certificates/{cert_id}/download")
    assert down_resp.status_code == 200
    print(f"    -> Content-Disposition: {down_resp.headers['Content-Disposition']}")
    original_pdf_bytes = down_resp.content

    # 6. Test ZIP Export Endpoint (download-all)
    print(f"\n[6] Testing ZIP batch download (GET /api/jobs/{job_id}/download-all)...")
    zip_resp = client.get(f"/api/jobs/{job_id}/download-all")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["Content-Type"] == "application/zip"
    print(f"    -> Content-Disposition: {zip_resp.headers['Content-Disposition']}")

    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        print(f"    -> Archive entries ({len(zf.namelist())} total):")
        for name in zf.namelist():
            size = zf.getinfo(name).file_size
            print(f"       * {name} ({size:,} bytes)")

        csv_content = zf.read("results.csv").decode("utf-8")
        print(f"\n    -> Preview results.csv:\n{csv_content.strip()}")

    # 7. Test Self-Healing (Disk Wipe Test)
    print("\n[7] Testing Self-Healing Storage (Simulating disk wipe)...")
    target_job_dir = storage_path / job_id
    print(f"    -> Current storage files: {[f.name for f in target_job_dir.glob('*.pdf')]}")

    # Wipe the job directory!
    print("    -> Deleting all files from storage directory...")
    shutil.rmtree(target_job_dir)
    assert not target_job_dir.exists()
    print("    -> Storage directory is now completely EMPTY.")

    # Request the certificate again!
    print("    -> Requesting GET /api/certificates/{cert_id}/download again...")
    healed_resp = client.get(f"/api/certificates/{cert_id}/download")
    assert healed_resp.status_code == 200
    assert healed_resp.content.startswith(b"%PDF")
    assert healed_resp.content == original_pdf_bytes, "Regenerated PDF differs from original!"
    print("    -> SELF-HEALING SUCCESS: File was transparently regenerated on-demand!")
    print(f"    -> Re-created on disk: {[f.name for f in target_job_dir.glob('*.pdf')]}")

    print("\n" + "=" * 60)
    print("   ALL PHASE 6 RETRIEVAL & SELF-HEALING CHECKS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_phase6_live_demo()
