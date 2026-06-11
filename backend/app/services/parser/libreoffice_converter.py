import shutil
import subprocess
import tempfile
from pathlib import Path


def convert_office_document(path: Path, target_ext: str) -> Path:
    target_ext = target_ext.lstrip(".").lower()
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    out_dir = Path(tempfile.mkdtemp(prefix="audit-doc-convert-"))
    if not soffice:
        return _convert_with_textutil(path, target_ext, out_dir)
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


def _convert_with_textutil(path: Path, target_ext: str, out_dir: Path) -> Path:
    textutil = shutil.which("textutil")
    if not textutil or target_ext not in {"doc", "docx", "html", "odt", "rtf", "txt", "wordml"}:
        raise RuntimeError("LibreOffice not installed; cannot convert legacy Office documents")
    output = out_dir / f"{path.stem}.{target_ext}"
    completed = subprocess.run(
        [textutil, "-convert", target_ext, "-output", str(output), str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"textutil conversion failed: {detail}")
    if not output.exists():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"textutil conversion finished but .{target_ext} output was not found: {detail}")
    return output


def convert_doc_to_pdf(path: Path) -> Path:
    return convert_office_document(path, "pdf")


def convert_doc_to_docx(path: Path) -> Path:
    return convert_office_document(path, "docx")
