import csv

import pytest

from kartotajs import library
from kartotajs.config import Config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("KARTOTAJS_DATA", str(tmp_path / "data"))
    c = Config(inbox=str(tmp_path / "Ienākošie"), output=str(tmp_path / "Kārtotie"))
    c.ensure_dirs()
    (c.inbox_path / "skenejums1.pdf").write_bytes(b"%PDF-1.4 viens")
    (c.inbox_path / "skenejums2.pdf").write_bytes(b"%PDF-1.4 divi")
    (c.inbox_path / "piezimes.txt").write_text("nav pdf")
    return c


def test_nothing_changes_before_accept(cfg):
    assert library.list_inbox(cfg) == ["skenejums1.pdf", "skenejums2.pdf"]
    info = library.target_for(cfg, "ROV_043274", "235126", "2026-08-29")
    assert info["folder"] == "2026-Augusts"
    assert info["file"] == "ROV_043274-235126.pdf"
    assert list(cfg.output_path.iterdir()) == []


def test_accept_copies_and_moves_original(cfg):
    res = library.accept(cfg, "skenejums1.pdf", "ROV_043274", "235126", "2026-08-29")
    target = cfg.output_path / "2026-Augusts" / "ROV_043274-235126.pdf"
    assert res["target"] == str(target)
    assert target.read_bytes() == b"%PDF-1.4 viens"
    assert not (cfg.inbox_path / "skenejums1.pdf").exists()
    assert (cfg.processed_path / "skenejums1.pdf").exists()
    assert library.list_inbox(cfg) == ["skenejums2.pdf"]

    with cfg.log_path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    assert rows[1][1] == "akceptēts" and rows[1][3] == "ROV_043274"


def test_accept_never_overwrites(cfg):
    library.accept(cfg, "skenejums1.pdf", "ROV_043274", "235126", "2026-08-29")
    with pytest.raises(library.ActionError):
        library.accept(cfg, "skenejums2.pdf", "ROV_043274", "235126", "2026-08-29")
    target = cfg.output_path / "2026-Augusts" / "ROV_043274-235126.pdf"
    assert target.read_bytes() == b"%PDF-1.4 viens"
    assert (cfg.inbox_path / "skenejums2.pdf").exists()


def test_accept_rejects_invalid_fields(cfg):
    with pytest.raises(library.ActionError):
        library.accept(cfg, "skenejums1.pdf", "ROV_123", "235126", "2026-08-29")
    assert (cfg.inbox_path / "skenejums1.pdf").exists()
    assert list(cfg.output_path.iterdir()) == []


def test_undo_restores_everything(cfg):
    library.accept(cfg, "skenejums1.pdf", "ROV_043274", "235126", "2026-08-29")
    res = library.undo(cfg)
    assert res["source"] == "skenejums1.pdf"
    assert (cfg.inbox_path / "skenejums1.pdf").read_bytes() == b"%PDF-1.4 viens"
    assert not (cfg.output_path / "2026-Augusts").exists()
    assert library.last_action(cfg) is None
    with pytest.raises(library.ActionError):
        library.undo(cfg)


def test_undo_refuses_if_saved_file_changed(cfg):
    res = library.accept(cfg, "skenejums1.pdf", "ROV_043274", "235126", "2026-08-29")
    with open(res["target"], "ab") as fh:
        fh.write(b"labots")
    with pytest.raises(library.ActionError):
        library.undo(cfg)


def test_processed_name_clash_gets_suffix(cfg):
    cfg.processed_path.mkdir()
    (cfg.processed_path / "skenejums1.pdf").write_bytes(b"vecs")
    library.accept(cfg, "skenejums1.pdf", "ROV_043274", "235126", "2026-08-29")
    assert (cfg.processed_path / "skenejums1 (2).pdf").read_bytes() == b"%PDF-1.4 viens"
    assert (cfg.processed_path / "skenejums1.pdf").read_bytes() == b"vecs"


def test_path_traversal_blocked(cfg):
    for bad in ("../x.pdf", "/etc/passwd", "", ".hidden.pdf"):
        with pytest.raises(library.ActionError):
            library.inbox_file(cfg, bad)


def test_images_are_listed_and_saved_as_pdf(cfg):
    from PIL import Image

    Image.new("RGB", (400, 300), "white").save(cfg.inbox_path / "foto.jpg")
    (cfg.inbox_path / "dokuments.docx").write_bytes(b"x")
    assert "foto.jpg" in library.list_inbox(cfg)
    assert library.unsupported_in_inbox(cfg) == ["dokuments.docx", "piezimes.txt"]

    res = library.accept(cfg, "foto.jpg", "ROV_043274", "235126", "2026-08-29")
    saved = open(res["target"], "rb").read()
    assert res["target"].endswith("ROV_043274-235126.pdf")
    assert saved.startswith(b"%PDF")
    assert (cfg.processed_path / "foto.jpg").exists()

    library.undo(cfg)
    assert (cfg.inbox_path / "foto.jpg").exists()


def _two_receipt_pdf(path):
    """A4 lapa ar divām "kvītīm": augšā sarkana, apakšā zila."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(0, 0, 595, 421), color=(1, 0, 0), fill=(1, 0, 0))
    page.draw_rect(pymupdf.Rect(0, 421, 595, 842), color=(0, 0, 1), fill=(0, 0, 1))
    doc.save(path)


def test_two_receipts_in_one_file(cfg):
    import io

    from PIL import Image
    import pymupdf

    _two_receipt_pdf(cfg.inbox_path / "divas.pdf")
    units = ["0-0", "0-1"]
    top = {"id": "0-0", "page": 0, "top": 0.0, "bottom": 0.5}
    bottom = {"id": "0-1", "page": 0, "top": 0.5, "bottom": 1.0}

    first = library.accept(cfg, "divas.pdf", "ROV_043452", "214203", "2026-09-27",
                           unit=top, all_units=units)
    # Pirmā kvīts saglabāta, bet oriģināls paliek, jo otrā vēl nav apstrādāta.
    assert not first["finished"]
    assert (cfg.inbox_path / "divas.pdf").exists()
    assert library.done_units(cfg, "divas.pdf") == {"0-0"}
    with pymupdf.open(first["target"]) as doc:
        pix = doc[0].get_pixmap(dpi=20)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    r, g, b = img.getpixel((img.width // 2, img.height // 2))
    assert r > 200 and b < 80  # tikai augšējā (sarkanā) kvīts

    with pytest.raises(library.ActionError):  # to pašu kvīti otrreiz nevar
        library.accept(cfg, "divas.pdf", "ROV_043452", "214204", "2026-09-27",
                       unit=top, all_units=units)

    second = library.accept(cfg, "divas.pdf", "ROV_043396", "127668", "2026-09-19",
                            unit=bottom, all_units=units)
    assert second["finished"]
    assert not (cfg.inbox_path / "divas.pdf").exists()
    assert (cfg.processed_path / "divas.pdf").exists()
    assert (cfg.output_path / "2026-Septembris" / "ROV_043396-127668.pdf").exists()

    # Atsaucot otro: oriģināls atgriežas, pirmā paliek akceptēta.
    library.undo(cfg)
    assert (cfg.inbox_path / "divas.pdf").exists()
    assert library.done_units(cfg, "divas.pdf") == {"0-0"}
    # Atsaucot arī pirmo: viss kā sākumā.
    library.undo(cfg)
    assert library.done_units(cfg, "divas.pdf") == set()
    assert not (cfg.output_path / "2026-Septembris").exists()
