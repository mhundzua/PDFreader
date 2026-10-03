import pymupdf

from kartotajs.documents import unit_pdf_bytes


def _page_size(data: bytes):
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return doc[0].rect.width, doc[0].rect.height


def test_single_receipt_on_a4_is_trimmed(tmp_path):
    """Viena A5 kvīts, skenēta A4 formātā: tukšā apakšējā puse tiek nogriezta."""
    path = tmp_path / "viena.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(10, 10, 585, 410), color=(0, 0, 0), width=3)
    page.insert_text((60, 100), "ROV_043452", fontsize=30)
    doc.save(path)

    width, height = _page_size(unit_pdf_bytes(path, 0, 0.0, 1.0))
    assert height < 842 * 0.6
    assert width > 595 * 0.9


def test_full_receipt_is_kept_unchanged(tmp_path):
    path = tmp_path / "pilna.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=420)
    page.draw_rect(pymupdf.Rect(5, 5, 590, 415), color=(0, 0, 0), width=3)
    doc.save(path)
    assert unit_pdf_bytes(path, 0, 0.0, 1.0) == path.read_bytes()
