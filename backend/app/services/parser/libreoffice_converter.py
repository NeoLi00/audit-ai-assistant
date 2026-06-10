import shutil
import subprocess
import tempfile
from pathlib import Path


def convert_office_document(path: Path, target_ext: str) -> Path:
    target_ext = target_ext.lstrip(".").lower()
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice not installed; cannot convert legacy Office documents")
    out_dir = Path(tempfile.mkdtemp(prefix="audit-doc-convert-"))
    completed = subprocess.run(
        [soffice, "--headless", "--convert-to", target_ext, "--outdir", str(out_dir), str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"LibreOffice conversion failed: {detail}")
    candidates = sorted(out_dir.glob(f"*.{target_ext}"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"LibreOffice conversion finished but .{target_ext} output was not found: {detail}")
    return candidates[0]


def convert_doc_to_pdf(path: Path) -> Path:
    return convert_office_document(path, "pdf")


def convert_doc_to_docx(path: Path) -> Path:
    return convert_office_document(path, "docx")
