import datetime as dt

from kartotajs import naming


def test_example_from_user():
    # ROV_037813, sērijas Nr. 123456, datums 02.10.2026 -> 2026-Oktobris/ROV_037813-123456.pdf
    assert naming.file_name("ROV_037813", "123456") == "ROV_037813-123456.pdf"
    assert naming.folder_name(dt.date(2026, 10, 2)) == "2026-Oktobris"


def test_all_months_latvian():
    names = [naming.folder_name(dt.date(2026, m, 1)) for m in range(1, 13)]
    assert names == [
        "2026-Janvāris", "2026-Februāris", "2026-Marts", "2026-Aprīlis", "2026-Maijs",
        "2026-Jūnijs", "2026-Jūlijs", "2026-Augusts", "2026-Septembris", "2026-Oktobris",
        "2026-Novembris", "2026-Decembris",
    ]


def test_validate():
    errors, warnings = naming.validate("ROV_043274", "235126", "2026-08-29")
    assert errors == {} and warnings == []

    errors, warnings = naming.validate("ROV_043274", "1234567", "2026-08-29")
    assert errors == {} and warnings  # nav 6 cipari -> tikai brīdinājums

    errors, _ = naming.validate("ROV_04327", "", "2026-02-30")
    assert set(errors) == {"contract", "serial", "date"}

    errors, _ = naming.validate("ROV_043274", "12/34", "2026-08-29")
    assert "serial" in errors
