# Data bundled with this package

## `nino34_monthly.csv`

Monthly Niño 3.4 sea surface temperature and anomaly, January 1950 to the
present, from NOAA's Climate Prediction Center ERSSTv5 index file.

| Column | Meaning |
|---|---|
| `year`, `month` | Calendar month |
| `nino34` | Absolute SST over the Niño 3.4 box, °C |
| `nino34_anom` | Anomaly against the 1991–2020 base period, °C |

The model averages this to a DJF seasonal mean, labelled by the year the
December falls in, so the 2015 season means December 2015 to February 2016.

Niño 3.4 is the SST anomaly averaged over 170–120°W, 5°S–5°N. Note the base
period: the anomalies are published against 1991–2020, so over a record starting
in 1950 they carry a cold offset of roughly −0.12 °C. `load_index` corrects for
this by default; see the `baseline` argument.

To refresh it:

```bash
python - <<'PY'
import io, urllib.request, pandas as pd
url = "https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii"
txt = urllib.request.urlopen(url, timeout=60).read().decode()
df = pd.read_csv(io.StringIO(txt), sep=r"\s+")
df.columns = ["year", "month", "nino12", "nino12_anom", "nino3", "nino3_anom",
              "nino4", "nino4_anom", "nino34", "nino34_anom"]
df[["year", "month", "nino34", "nino34_anom"]].to_csv("nino34_monthly.csv", index=False)
PY
```

If you refresh it, also update `CPC_ADVISORY` in `impact_model/climate.py`, which
records the diagnostic discussion the dashboard cites.

## `dmi_son_annual_averages.csv`

September–November mean Dipole Mode Index, 1980–2020, from three independent
observational sea surface temperature products.

| Column | Meaning |
|---|---|
| `Year` | Calendar year of the SON season |
| `DMI_HadISST_SON` | DMI from HadISST |
| `DMI_ERSST_SON` | DMI from NOAA ERSST |
| `DMI_ERA5_SON` | DMI from ERA5 |

The model uses the ERA5 column by default, falling back to HadISST then ERSST if
it is absent. See `impact_model/climate.py`.

The Dipole Mode Index is the difference in SST anomaly between the western
equatorial Indian Ocean (50–70°E, 10°S–10°N) and the south-eastern equatorial
Indian Ocean (90–110°E, 10°S–0°N), after Saji et al. (1999).

## `dmi_son_top_events.csv`

The strongest SON dipole events in the record, used for cross-checking the phase
classification.

---

These files are copied from the parent research repository so that this teaching
package is self-contained and can be zipped, shared or deployed on its own. They
are observations, not model output: everything downstream of them in this
package is modelled.
