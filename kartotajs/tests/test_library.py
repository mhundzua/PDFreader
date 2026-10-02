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
