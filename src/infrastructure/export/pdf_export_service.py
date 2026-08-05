from collections.abc import Iterable


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MAX_CHARS_PER_LINE = 42
MAX_LINES_PER_PAGE = 44


def build_text_pdf(title: str, lines: Iterable[str]) -> bytes:
    """Build a small, valid PDF using a standard Simplified Chinese CID font."""
    wrapped_lines = [title, "", *_wrap_lines(lines)]
    pages = [
        wrapped_lines[index:index + MAX_LINES_PER_PAGE]
        for index in range(0, len(wrapped_lines), MAX_LINES_PER_PAGE)
    ] or [[title]]

    page_ids = [5 + index * 2 for index in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Count {len(page_ids)} /Kids "
            f"[{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] >>"
        ).encode("ascii"),
        3: (
            b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
            b"/Encoding /UniGB-UCS2-H /DescendantFonts [4 0 R] >>"
        ),
        4: (
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> >>"
        ),
    }

    for index, page_lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        content = _content_stream(page_lines)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"\nendstream"
        )

    return _serialize_pdf(objects)


def _wrap_lines(lines: Iterable[str]) -> list[str]:
    wrapped: list[str] = []
    for value in lines:
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        for logical_line in text.split("\n"):
            if not logical_line:
                wrapped.append("")
                continue
            wrapped.extend(
                logical_line[index:index + MAX_CHARS_PER_LINE]
                for index in range(0, len(logical_line), MAX_CHARS_PER_LINE)
            )
    return wrapped


def _content_stream(lines: list[str]) -> bytes:
    commands = [b"BT", b"/F1 12 Tf", b"50 795 Td", b"16 TL"]
    for line in lines:
        encoded = line.encode("utf-16-be").hex().upper().encode("ascii")
        commands.append(b"<" + encoded + b"> Tj")
        commands.append(b"T*")
    commands.append(b"ET")
    return b"\n".join(commands)


def _serialize_pdf(objects: dict[int, bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max(objects) + 1)
    for object_id in sorted(objects):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)
