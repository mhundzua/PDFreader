# Kvīšu kārtotājs

Lokāls rīks skenētu ROVICO servisa līguma kvīšu kārtošanai uz Mac (arī M1).
Viss notiek uz jūsu datora: nav maksas servisu, internets nav vajadzīgs
(izņemot pirmo instalēšanu).

## Ko tas dara

1. Ņem failus no mapes **Ienākošie**: PDF vai attēlus (JPG, PNG, iPhone HEIC).
   - Vienā skenējumā var būt **vairākas kvītis**, piemēram, divas uz skenera stikla
     viena virs otras. Rīks tās atrod un rāda rindā kā atsevišķas kvītis
     ("Scan.pdf · 1/2", "Scan.pdf · 2/2"). Kvītīm nav jābūt taisni novietotām,
     tikai nedrīkst pārklāties un iziet ārpus stikla.
   - Daudzlapu PDF: katra lapa tiek apstrādāta atsevišķi.
2. Ar OCR nolasa **līguma Nr.** (`ROV_` + 6 cipari), **alkometra sērijas Nr.**
   un pieņemšanas **datumu** (lauks "DATUMS:" augšā labajā stūrī).
3. Parāda tos rediģējamos laukos blakus kvīts priekšskatījumam. Pie katra lauka
   redzams palielināts izgriezums no kvīts, lai varētu ātri salīdzināt.
4. Parāda gala nosaukumu, piemēram, `ROV_043274-235126.pdf` mapē `2026-Augusts`.
5. **Tikai pēc pogas "Akceptēt"** kvīts tiek saglabāta mēneša mapē kā atsevišķs PDF.
   Kad visas kvītis no skenējuma ir akceptētas, oriģināls tiek pārvietots uz
   `Ienākošie/Apstrādāti`.

Ja sērijas numuram priekšā ir burti (piem. `SNL 127668`), tie tiek izlaisti:
`ROV_043396-127668.pdf`.

Skenējiet ar **300 dpi**: rokraksts tiek nolasīts precīzāk nekā ar 150 dpi.

### Drošība

- Kamēr nav nospiests "Akceptēt", diskā nekas netiek mainīts.
- **Dzelteni** lauki ir tie, par kuriem rīks nav pārliecināts (rokraksts, sērijas Nr.
  nav 6 cipari, gads nav salasāms). "Akceptēt" kļūst aktīva tikai tad, kad tie ir
  izlaboti vai apstiprināti ar "Pareizi ✓".
- Esošs fails nekad netiek pārrakstīts. Ja tāds jau ir, rīks apstājas un brīdina.
- **↶ Atsaukt** atgriež pēdējo akceptēšanu: dzēš kopiju un atliek kvīti atpakaļ rindā.
  To var darīt vairākas reizes pēc kārtas.
- Katra akceptēšana un atsaukšana tiek ierakstīta `Kārtotie/žurnāls.csv`
  (atveras ar Excel vai Numbers).
- Serveris pieejams tikai no šī datora (`127.0.0.1`).

## Uzstādīšana (vienreiz)

1. Vajadzīgs Python 3.9 līdz 3.12. Ja tā nav, terminālī:
   ```bash
   brew install python@3.12
   ```
   (Homebrew: https://brew.sh)
2. Lejupielādējiet šo repozitoriju un atveriet mapi `kartotajs`.
3. Pirmo reizi: ar peles labo pogu uz `Start.command`, tad **Open** (macOS prasīs
   apstiprinājumu, jo fails nav no App Store). Pirmā palaišana instalē
   bibliotēkas, un tas aizņem dažas minūtes.

## Lietošana

1. Dubultklikšķis uz `Start.command`. Atveras termināļa logs un pārlūks ar rīku.
2. Ielieciet skenētos PDF failus mapē `~/Documents/Ienākošie`.
3. Pārbaudiet laukus, izlabojiet dzeltenos un spiediet **Akceptēt** (vai Enter).
4. **Izlaist** atstāj kvīti rindā neskartu un pāriet uz nākamo.
5. Lai beigtu darbu, aizveriet termināļa logu.

Mapes var mainīt pogā **Iestatījumi**. Noklusējums:

| | Mape |
|---|---|
| Ienākošās kvītis | `~/Documents/Ienākošie` |
| Apstrādātie oriģināli | `~/Documents/Ienākošie/Apstrādāti` |
| Sakārtotās kvītis | `~/Documents/Kārtotie/<gads>-<Mēnesis>/` |
| Žurnāls | `~/Documents/Kārtotie/žurnāls.csv` |

## Kā tiek nolasīti lauki

Kvīts veidlapa vienmēr ir viena un tā pati, tāpēc rīks vispirms atrod drukātās
etiķetes ("LĪGUMA Nr.:", "DATUMS:", "ALKOMETRA SĒRIJAS NR.:" u.c.) un pēc tām
aprēķina, kur katrs lauks atrodas tieši šajā skenējumā. Pēc tam:

- Izgriež lauka apgabalu un nolasa to vairākos veidos: oriģinālu un tikai zilo
  tinti (tā tiek noņemtas līnijas, drukātais teksts un otrās puses caurspīdums).
- Rokrakstam raksturīgās sajaukšanas tiek labotas: `d`→2, `g`→9, `h`→4, `o`→0 u.c.
- Visu variantu rezultāti tiek apvienoti balsojumā. Ja varianti nesakrīt, lauks
  ir dzeltens.
- Citi datumi uz kvīts (pie paraksta, kalibrēšanas uzlīmē, apakšā) tiek ignorēti.

OCR dzinēji (abi bezmaksas, lokāli):

- **Apple Vision**, iebūvēts macOS. Uz Mac tiek izmantots automātiski.
- **RapidOCR** (PaddleOCR modeļi), darbojas uz jebkura datora.

Uz Mac tiek izmantoti abi, un to rezultāti tiek apvienoti.

Ar četrām parauga kvītīm (tikai RapidOCR, bez Apple Vision) līguma Nr. tika
nolasīts pareizi visās četrās. Rokrakstā rakstītajiem laukiem bija pareizi 4 no 8.
Visos pārējos gadījumos kļūda bija vienā ciparā, un visi šie lauki bija atzīmēti
dzelteni, tātad neviens nepareizs lauks netika uzdots par pareizu.

### Paraugi rokraksta uzlabošanai

Pēc katras akceptēšanas rīks lokāli saglabā apstiprinātā sērijas Nr. un datuma
izgriezumu kopā ar pareizo vērtību (macOS: `~/Library/Application Support/Kartotajs/paraugi`).
Tajos nav vārdu vai tālruņu. Kad būs sakrājušies daži desmiti, no tiem var
apmācīt ciparu atpazinēju, kas pielāgots jūsu darbinieku rokrakstiem.

## Izstrādātājiem

```bash
cd kartotajs
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests
# ar īstām kvītīm (repozitorijā tās nav personas datu dēļ):
KARTOTAJS_SAMPLES=/ceļš/uz/kvitim .venv/bin/python -m pytest tests
.venv/bin/python -m kartotajs --no-browser   # http://127.0.0.1:8765
```

| Fails | Saturs |
|---|---|
| `kartotajs/extract.py` | etiķešu atrašana, izgriezumi, balsojums |
| `kartotajs/parsing.py` | līguma Nr., sērijas Nr. un datuma atpazīšana tekstā |
| `kartotajs/ocr.py` | Apple Vision un RapidOCR |
| `kartotajs/library.py` | akceptēšana, atsaukšana, žurnāls |
| `kartotajs/naming.py` | nosaukumi, latviešu mēneši, validācija |
| `kartotajs/server.py`, `static/` | saskarne |
