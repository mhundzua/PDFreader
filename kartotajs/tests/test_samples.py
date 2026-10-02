"""Pārbaude ar īstām kvītīm. Kvītis satur personas datus, tāpēc repozitorijā
tās nav: norādiet mapi ar KARTOTAJS_SAMPLES=/ceļš (faili kvits1.pdf ... kvits4.pdf,
un, ja ir, tās pašas kvītis kā attēli kvits1.webp/.jpg ...).

Rokrakstā nolasītajiem laukiem prasām: vai nu pareiza vērtība, vai lauks
atzīmēts kā neskaidrs (lai lietotājs to pārbauda). Pārliecinoši nepareiza
vērtība nav pieļaujama.
"""

import os
from pathlib import Path

import pytest

SAMPLES = os.environ.get("KARTOTAJS_SAMPLES")
EXPECTED = {
    "kvits1.pdf": {"contract": "ROV_043274", "serial": "235126", "date": "2026-08-29"},
    "kvits2.pdf": {"contract": "ROV_043385", "serial": "229604", "date": "2026-09-17"},
    "kvits3.pdf": {"contract": "ROV_040639", "serial": "219044", "date": "2026-07-29"},
    "kvits4.pdf": {"contract": "ROV_035852", "serial": "219596", "date": "2026-04-07"},
}

pytestmark = pytest.mark.skipif(not SAMPLES, reason="KARTOTAJS_SAMPLES nav norādīts")


@pytest.fixture(scope="module")
def engines():
    from kartotajs.ocr import available_engines
    return available_engines()


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_sample(name, engines):
    path = Path(SAMPLES) / name
    if not path.exists():
        pytest.skip(f"{name} nav")
    check(path, EXPECTED[name], engines)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_sample_as_image(name, engines):
    stem = Path(name).stem
    images = [p for p in Path(SAMPLES).glob(f"{stem}.*") if p.suffix.lower() != ".pdf"]
    if not images:
        pytest.skip(f"{stem} attēls nav")
    check(images[0], EXPECTED[name], engines)


def check(path, expected, engines):
    from kartotajs.extract import extract

    fields = extract(path, engines)["fields"]
    assert fields["contract"]["value"] == expected["contract"]
    assert fields["contract"]["confident"]
    for key in ("serial", "date"):
        got = fields[key]
        assert got["value"] == expected[key] or not got["confident"], (key, got["value"])
