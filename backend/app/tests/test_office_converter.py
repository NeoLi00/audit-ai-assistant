import subprocess
from pathlib import Path

from app.services.parser.libreoffice_converter import convert_office_document


def test_convert_office_document_falls_back_to_textutil_for_docx(tmp_path: Path, monkeypatch):
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"legacy")

    def fake_which(command: str) -> str | None:
        if command in {"soffice", "libreoffice"}:
            return None
        if command == "textutil":
            return "/usr/bin/textutil"
        return None

    def fake_run(args, check, capture_output, text, timeout):
        output = Path(args[args.index("-output") + 1])
        output.write_bytes(b"converted")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.services.parser.libreoffice_converter.shutil.which", fake_which)
    monkeypatch.setattr("app.services.parser.libreoffice_converter.subprocess.run", fake_run)

    converted = convert_office_document(source, "docx")

    assert converted.suffix == ".docx"
    assert converted.read_bytes() == b"converted"
