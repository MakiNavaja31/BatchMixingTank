# Batch Mixing Tank · VC_ARG_04 v4.1

Vibe Coding Industrial · Digitalización Férriz. A 100 L batch mixing tank, specified, simulated and visualised end to end:

- an operation specification (equipment, state machine, alarms, interface, HMI, report, analytics);
- a Python simulator with a 100 ms tick that runs a full production day with injected faults;
- a filled Production Order Report (Excel), a 5 s process log (CSV) and an automatic test sheet;
- an operator HMI that replays the run (Full HD, 16:9) and an analytics dashboard.

All results are **simulated data**.

## Results of the reference run (01.11.2026, 06:30–19:54 simulated clock)

| Indicator | Value |
|---|---|
| Report records | 60 (56 orders + 4 repeats) |
| Completed / aborted / skipped | 53 / 4 / 3 |
| Litres produced / not produced | 4,645 L / 200 L |
| Scrap generated | 254.04 L |
| Cleanings finished | 25 |
| Alarms raised by code 1–6 | 1 / 2 / 1 / 2 / 1 / 3 |
| Time making good product | 76.5 % |
| Highest level | 101.04 L (limit 101 L + one tick of flow) |
| Test results | 27 PASS, 0 FAIL, 4 OBSERVATION |

## Repository layout

| Folder | Content |
|---|---|
| `spec/` | Operation specification v4.1 (PDF and Markdown), state machine diagram; `archive/` holds v4.0 |
| `prompt/` | Prompt v4.1; `archive/` holds v4.0 |
| `inputs/` | Recipes, production orders (original and REBALANCED), empty report template, HMI logo |
| `simulator/` | Python source: `sim.py` (process and controller), `scenario.py` (faults F1–F10), `run_scenario.py`, `rebalance.py`, `build_hmi.py`, `build_dashboard_standalone.py`, `hmi_template.html` |
| `outputs/` | `VC_ARG_04_Production_Orders_Report.xlsx` (sheets today, Summary, Events, Legend, Test results) and `VC_ARG_04_sim_log_5s.csv` |
| `hmi/` | `VC_ARG_04_HMI_Batch_Mixing_Tank.html`, open it in a browser |
| `dashboard/` | Dashboard page source (`index.html`, `calcs.js`, `charts.js`), its data, and `VC_ARG_04_dashboard_offline.html` to open in a browser |
| `slides/` | Screenshots of the HMI at key moments and of the dashboard, plus `VC_ARG_04_slides.pdf` with all of them |

## Run it yourself

Requires Python 3 (tested with 3.13.18), `openpyxl` (tested 3.1.5) and `Pillow` (tested 12.3.0).

```bash
pip install -r simulator/requirements.txt
python simulator/rebalance.py inputs/VC_ARG_03_Production_Orders_Template.xlsx inputs/VC_ARG_03_Production_Orders_REBALANCED.xlsx
python simulator/run_scenario.py               # report, CSV, test results, dashboard data
python simulator/build_hmi.py                  # HMI page
python simulator/build_dashboard_standalone.py # offline dashboard page
```

The run is deterministic (seed 7): the same inputs give the same report, log and test results.

## Notes

- The HMI and the offline dashboard load the Roboto font from Google Fonts when online; without a connection the browser uses a fallback font.
- `dashboard/vendor/d3.v7.min.js` is d3 v7.9.0 (ISC licence, see `dashboard/vendor/d3.LICENSE.txt`).
- The HMI logo (`inputs/MakiPope.png`) is a drawing credited to © del Maestro IvÁ. Make sure you have the right to publish it before making this repository public.
- Licence: not chosen yet.

Created by Ángel Rodríguez + Claude Opus 5.5 (cc)
