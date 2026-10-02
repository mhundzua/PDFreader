import datetime as dt

from kartotajs import parsing

TODAY = dt.date(2026, 10, 2)


def test_contract_from_ocr_variants():
    assert parsing.find_contract("LiGUMANr.: R0V_043274") == "ROV_043274"
    assert parsing.find_contract("ROV_ 040639") == "ROV_040639"
    assert parsing.find_contract("ROV 035852") == "ROV_035852"
    assert parsing.find_contract("ROV_O43385") == "ROV_043385"
    assert parsing.find_contract("ROV_04327") is None
    assert parsing.find_contract("ROV_0432745") is None


def test_serial_handwriting_lookalikes():
    assert parsing.find_serial("235126") == "235126"
    assert parsing.find_serial("digohh") == "219044"  # rokrakstā '2' izskatās pēc 'd'
    assert parsing.find_serial("2 19596") == "219596"
    assert parsing.find_serial("12345678") == "12345678"  # nav 6, bet derīgs
    assert parsing.find_serial("ab") is None


def test_date_formats():
    assert parsing.find_date("29.08.26", TODAY) == dt.date(2026, 8, 29)
    assert parsing.find_date("02.10.2026.", TODAY) == dt.date(2026, 10, 2)
    assert parsing.find_date("02.10.26.", TODAY) == dt.date(2026, 10, 2)
    assert parsing.find_date("17 09 2026", TODAY) == dt.date(2026, 9, 17)
    assert parsing.find_date("29.07.d6", TODAY) == dt.date(2026, 7, 29)
    assert parsing.find_date("31.02.26", TODAY) is None
    assert parsing.find_date("DATUMS:", TODAY) is None


def test_day_month_fallback_uses_latest_past_year():
    assert parsing.find_day_month("04.04.0086", TODAY) == dt.date(2026, 4, 4)
    assert parsing.find_day_month("14.12.Bod", TODAY) == dt.date(2025, 12, 14)


def test_ascii_upper():
    assert parsing.ascii_upper("LĪGUMA Nr.:") == "LIGUMANR"
    assert parsing.ascii_upper("ALKOMETRA SĒRIJAS NR.:") == "ALKOMETRASERIJASNR"


def test_fuzzy_labels():
    assert parsing.label_length("LICUMANR043452", "LIGUMANR") == 8  # 'Ī' nolasīts kā 'ic'
    assert parsing.label_length("LIGUMANR", "LIGUMANR") == 8
    assert parsing.label_length("KONTAKTTALRUNIS", "LIGUMANR") == 0
    assert parsing.label_length("CEMA", "CENA") == 0  # īsām etiķetēm kļūdas nepieļaujam


def test_serial_with_letter_prefix():
    assert parsing.find_serial("SNL 127668") == "SNL127668"
    assert parsing.find_serial("NR.: 235126") == "235126"
