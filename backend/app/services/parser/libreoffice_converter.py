import shutil
import subprocess
import tempfile
from pathlib import Path


def convert_doc_to_docx(path: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice not installed; cannot convert .doc to .docx")
    out_dir = Path(tempfile.mkdtemp(prefix="audit-doc-convert-"))
    subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(path)],
        check=True,
        capture_output=True,
    )
    converted = out_dir / f"{path.stem}.docx"
    if not converted.exists():
        raise RuntimeError("LibreOffice conversion finished but docx output was not found")
    return converted
