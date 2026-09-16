from io import BytesIO
from pathlib import Path
import shutil
import subprocess

import pytest

from infrastructure.file.document_parse_service import parse_func


pytestmark = pytest.mark.skipif(
    shutil.which("libreoffice") is None,
    reason="Document format integration tests run in the backend image",
)


def _parsed_text(path: Path) -> str:
    elements = parse_func(BytesIO(path.read_bytes()), path.name)
    return "\n".join(str(element) for element in elements)


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("sample.txt", "TXT verification token", "TXT verification token"),
        ("sample.md", "# Markdown verification token", "Markdown verification token"),
    ],
)
def test_parse_plain_text_formats(
    tmp_path: Path,
    filename: str,
    content: str,
    expected: str,
) -> None:
    source = tmp_path / filename
    source.write_text(content, encoding="utf-8")

    assert expected in _parsed_text(source)


def test_parse_docx(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    source = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_heading("DOCX verification token", level=1)
    document.save(source)

    assert "DOCX verification token" in _parsed_text(source)


def test_parse_legacy_doc_with_libreoffice(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    libreoffice = shutil.which("libreoffice")
    if libreoffice is None:
        pytest.skip("LibreOffice is installed in the backend image")

    docx_source = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph("DOC verification token")
    document.save(docx_source)

    subprocess.run(
        [
            libreoffice,
            "--headless",
            "--convert-to",
            "doc:MS Word 97",
            "--outdir",
            str(tmp_path),
            str(docx_source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )

    assert "DOC verification token" in _parsed_text(tmp_path / "sample.doc")
