"""Run the VC_ARG_04 scenario (spec v4.1 section 14) and write the report, CSV, tests and dashboard/HMI data.

Usage (from the repository root):  python simulator/run_scenario.py
"""
import sys, csv, json, copy, shutil, datetime as dt
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from sim import *
from scenario import SCENARIO
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

IN = ROOT / 'inputs'
OUT = ROOT / 'outputs'
REC = IN / 'VC_ARG_03_Recipes_Template.xlsx'
ORD = IN / 'VC_ARG_03_Production_Orders_REBALANCED.xlsx'
ORD_SRC = IN / 'VC_ARG_03_Production_Orders_Template.xlsx'
TPL = IN / 'VC_ARG_03_Production_Order_Report_Template.xlsx'
START = dt.datetime(2026, 11, 1, 6, 30, 0)   # simulated clock, CET

recipes = load_recipes(REC)
orders = load_orders(ORD)
sim = Sim(orders, recipes, START, SCENARIO, seed=7)
sim.run()
assert sim.done, 'run did not finish'
rows, events = sim.rows, sim.events


def remarks_text(r):
    rm = list(r['remarks'])
    if len(r['clean_parts']) > 1:
        rm.append('Cleaning ' + ' + '.join(f"{k} {v:.1f} s" for k, v in r['clean_parts']))
    if r['scrap']:
        rm.append(f"Scrap {fmtL(r['scrap'])} L")
    return '; '.join(rm)


# ------------------------------------------------------------------ tests
tests = []


def T(tid, scenario, expect, observed, ok, kind='PASS/FAIL'):
    res = ('PASS' if ok else 'FAIL') if kind == 'PASS/FAIL' else 'OBSERVATION'
    tests.append(dict(id=tid, scenario=scenario, expect=expect, observed=observed, result=res))


def row_of(batch, retry=False):
    return [r for r in rows if r['batch'] == batch and ((r['retry_of'] is not None) == retry)]


def evs(typ=None, contains=None, batch=None):
    return [e for e in events if (typ is None or e['type'] == typ) and (contains is None or contains in e['detail'])
            and (batch is None or e['batch'] == batch)]


# data checks
bad = {k: v['problems'] for k, v in recipes.items() if not v['valid']}
T('D1', 'Recipes: percentages add up to 100, IDs R###, mixing time 5-600 s',
  'Every recipe valid (spec §4)', f"{len(recipes)} recipes, invalid: {bad or 'none'}", not bad)
T('D2', 'Recipes: approved flags', 'Only approved recipes can run',
  'Not approved: ' + ', '.join(k for k, v in recipes.items() if not v['approved']), True, 'OBS')
used = sorted({o['recipe'] for o in orders})
T('D3', 'Orders: recipe IDs exist', 'Unknown recipe rejects the list (§4)',
  f"Recipes used {used}; unknown: {[r for r in used if r not in recipes] or 'none'}",
  all(r in recipes for r in used))
T('D4', 'Orders: Batch IDs text and unique, volumes integer', 'Duplicate ID / non-integer rejects the list (§4)',
  f"List check errors: {validate_list(orders, recipes) or 'none'}", not validate_list(orders, recipes))
src = load_orders(ORD_SRC)
tot = lambda lst: {k: sum(o['vol'] for o in lst if o['batch'].split('.')[0] == k) for k in {o['batch'].split('.')[0] for o in lst}}
groups = {}
for o in orders:
    groups.setdefault(o['batch'].split('.')[0], []).append(o['vol'])
under = [(k, v) for k, v in groups.items() if v[-1] < 40 and len(v) > 1]
T('D5', 'Sub-batch rebalancing at list preparation', 'Order totals unchanged; no multi-batch order ends below 40 L (§4)',
  f"Totals equal: {tot(src) == tot(orders)}; multi-batch orders below 40 L: {under or 'none'}; single batches below 40 L: "
  f"{[o['batch'] for o in orders if o['vol'] < 40]}", tot(src) == tot(orders) and not under)
# dose rounding: brute force over all recipes and volumes
err = []
for rid, rc in recipes.items():
    for v in range(40, 101):
        p = plan_doses(v, rc['pct'])
        if sum(p) != v * CL:
            err.append((rid, v))
        for i in (0, 1):
            exact = Decimal(v) * rc['pct'][i] / 100
            if rc['pct'][2] > 0 and Decimal(p[i]) / CL != exact.quantize(Decimal('0.1'), ROUND_HALF_UP):
                err.append((rid, v, i))
        if any(rc['pct'][i] == 0 and p[i] != 0 for i in range(3)):
            err.append((rid, v, 'zero'))
T('R1', 'Planned doses, all recipes x 40-100 L', 'Prd_1, Prd_2 half up to 0.1 L; Prd_3 remainder; 0 % skipped (§4)',
  f"{len(recipes) * 61} combinations, errors {len(err)}; e.g. R005 45 L -> {[x / CL for x in plan_doses(45, recipes['R005']['pct'])]}",
  not err)
tb = [(10 * CL, 50, False), (10 * CL, 51, True), (30 * CL, 100, False), (30 * CL, 101, True), (11 * CL, 55, False), (11 * CL, 56, True)]
T('R2', 'Alarm 3 tolerance boundary', 'Alarm only when |dev| > min(5 % of plan, 1.0 L)',
  '; '.join(f"plan {p / CL:.0f} L dev {d / CL:.2f} L -> {'alarm' if tol_exceeded(d, p) else 'ok'}" for p, d, _ in tb),
  all(tol_exceeded(d, p) == e for p, d, e in tb))

# scenario checks
r3 = row_of('0003.0')[0]
T('F1', 'Volume discrepancy confirmed (0003.0, order 45 L, typed 50 L)', 'Rule 2: dialog, typed volume used, remark',
  f"vol used {r3['vol_used']} L, produced {fmtL(r3['vol_prod'] or 0)} L; remark: {r3['remarks'][0]}",
  r3['vol_used'] == 50 and r3['vol_prod'] == 50 * CL and 'confirmed by operator' in r3['remarks'][0])
rej = evs('REFUSAL', 'Volume 110 L rejected', '0005.0')
dlg = evs('INFO', 'Volume dialog: ', '0005.0')
canc = evs('INFO', 'nothing starts', '0005.0')
r5 = row_of('0005.0')[0]
T('F2', 'Out-of-range volume, then dialog cancelled (0005.0)', 'Rule 2: 110 L rejected with no dialog; cancel -> nothing starts',
  f"refusals {len(rej)}, dialogs {len(dlg)} ({[e['detail'] for e in dlg]}), cancels {len(canc)}, final vol {r5['vol_used']} L",
  len(rej) == 1 and len(dlg) == 1 and '90' in dlg[0]['detail'] and len(canc) == 1 and r5['vol_used'] == 100
  and r5['status'] == 'COMPLETED')
r9 = row_of('0007.0')[0]; r9r = row_of('0007.0', True)
T('F3', 'IN_P1 +10 % on 0007.0', 'Alarm 3, T15: ABORTED, scrap, cleaning, Stopped; retry appended; T18',
  f"#{r9['n']} {r9['status']} {r9['alarms']}, scrap {fmtL(r9['scrap'])} L, clean {r9['clean_s']:.1f} s; "
  f"retry #{r9r[0]['n'] if r9r else '-'} {r9r[0]['status'] if r9r else '-'}; T15={sim.transitions.get('T15', 0)} T18={sim.transitions.get('T18', 0)}",
  r9['status'] == 'ABORTED (ALARM)' and r9['alarms'] == ['3 – Fill deviation'] and r9['scrap'] > 0 and r9r
  and r9r[0]['status'] == 'COMPLETED' and r9r[0]['remarks'][0] == f"Retry of #{r9['n']}"
  and sim.transitions.get('T15') == 1 and sim.transitions.get('T18') == 1)
r16 = row_of('0013.0')[0]; r16r = row_of('0013.0', True)
T('F4', 'IN_P3 +20 % on last dose of 100 L (0013.0)', 'Alarm 1 before alarm 3 (overflow precedence); Alarm Stop; Reset; T2 cleaning; retry',
  f"#{r16['n']} {r16['alarms']}; retry {r16r[0]['status'] if r16r else '-'} scrap {fmtL(r16r[0]['scrap']) if r16r else '-'} L",
  r16['alarms'] == ['1 – Overflow'] and r16r and r16r[0]['status'] == 'COMPLETED' and r16r[0]['scrap'] > 100 * CL)
r29 = row_of('0020.0')[0]; r29r = row_of('0020.0', True)
rr = evs('REFUSAL', 'Reset refused', '0020.0')
T('F5', 'IN_P2 no flow (0020.0), repair 60 s', 'Alarm 4 within 15 s; Reset refused while cause present; Reset after repair',
  f"#{r29['n']} {r29['alarms']}; reset refusals {len(rr)}; retry {r29r[0]['status'] if r29r else '-'}",
  r29['alarms'] == ['4 – Step timeout'] and len(rr) == 1 and r29r and r29r[0]['status'] == 'COMPLETED')
a6 = [e for e in evs('ALARM', '4 – Step timeout', '0022.0')]
r31 = row_of('0022.0')
T('F6', 'IN_CLEAN stuck open in drain (pre-batch cleaning of 0022.0)', 'Alarm 4 (deadlock 1 L/s in = 1 L/s out); no report row; event log; note in next record',
  f"alarm events {len(a6)} in state {a6[0]['state'] if a6 else '-'}; rows for 0022.0: {len(r31)} ({r31[0]['status']}); remark: {r31[0]['remarks'][0] if r31[0]['remarks'] else '-'}",
  len(a6) == 1 and 'drain' in a6[0]['state'] and len(r31) == 1 and r31[0]['status'] == 'COMPLETED'
  and not r31[0]['alarms'] and 'interrupted by alarm 4' in r31[0]['remarks'][0])
r39 = row_of('0026.1')[0]; r39r = row_of('0026.1', True)
T('F7', 'Emergency Stop at 50 % of Emptying (0026.1)', 'Alarms 2 + 5, ABORTED; Remarks discharged/left; Reset; left-over to scrap; full retry',
  f"#{r39['n']} {r39['alarms']}; {r39['remarks'][1] if len(r39['remarks']) > 1 else '-'}; retry scrap {fmtL(r39r[0]['scrap']) if r39r else '-'} L",
  r39['alarms'] == ['2 – Emergency Stop', '5 – Partial batch'] and r39r and r39r[0]['status'] == 'COMPLETED'
  and r39r[0]['scrap'] == 50 * CL and r39r[0]['vol_prod'] == 100 * CL)
r36 = row_of('0024.0')
e8 = evs('ALARM', '2 – Emergency Stop', '0024.0')
T('F8', 'Emergency Stop in Waiting (before 0024.0)', 'Alarm 2 from Waiting; no row aborted; Reset -> Stopped, tank dirty -> T2',
  f"alarm events {len(e8)} in {e8[0]['state'] if e8 else '-'}; rows for 0024.0: {len(r36)} {r36[0]['status']} alarms {r36[0]['alarms']}",
  len(e8) == 1 and e8[0]['state'] == 'Waiting' and len(r36) == 1 and r36[0]['status'] == 'COMPLETED' and not r36[0]['alarms'])
r24 = row_of('0017.1')[0]
T('F9', 'Normal Stop during Mixing (0017.1)', 'T11; batch finishes; T9 cleaning; Stopped; cleaning in Remarks of last batch; next Start T1',
  f"#{r24['n']} {r24['status']}; remark: {r24['remarks'][-1] if r24['remarks'] else '-'}; T11={sim.transitions.get('T11', 0)} T9={sim.transitions.get('T9', 0)}",
  r24['status'] == 'COMPLETED' and 'Final cleaning after Normal Stop' in r24['remarks'][-1]
  and sim.transitions.get('T11') == 1 and sim.transitions.get('T9') == 1
  and any(s.get('code') == 'T1' and rows[s['row']]['batch'] == '0018.0' for s in sim.start_log))
r44 = row_of('0029.0')[0]
st44 = [s for s in sim.start_log if s['row'] == r44['n'] - 1]
T('F10', 'Normal Stop during pre-batch cleaning (0029.0)', 'T12; cleaning finishes; Stopped; batch stays pending; next Start fills (T1)',
  f"starts for #{r44['n']}: {[s.get('code') for s in st44]}; cleaning {r44['clean_s']:.1f} s; status {r44['status']}",
  sim.transitions.get('T12') == 1 and [s.get('code') for s in st44] == ['T4', 'T1'] and r44['status'] == 'COMPLETED'
  and r44['clean_s'] > 0)
sk = [r for r in rows if r['status'] == 'SKIPPED']
sr = [e for e in evs('REFUSAL', 'alarm 6 active')]
T('A6', 'Alarm 6: 0011.0, 0011.1 (R002 not approved), 0028.0 (20 L)', 'Start refused; Cancel batch -> SKIPPED, blanks, no repeat (§9, rule 11)',
  f"SKIPPED {[r['batch'] for r in sk]}; start refusals {len(sr)}; not produced {L(sim.not_produced)} L",
  [r['batch'] for r in sk] == ['0011.0', '0011.1', '0028.0'] and len(sr) == 3
  and all(r['IN'] is None and r['OUT'] is None and r['vol_prod'] is None and r['clean_s'] == 0 for r in sk)
  and not any(r['retry_of'] and rows[r['retry_of'] - 1]['status'] == 'SKIPPED' for r in rows) and sim.not_produced == 200 * CL)
lc = evs('REFUSAL', 'LIST COMPLETE')
T('E1', 'End of list', 'Rule 10: Start refused; Normal Stop -> final cleaning -> Stopped',
  f"refusals {len(lc)}; T10={sim.transitions.get('T10', 0)}; final state {ST_NAME[sim.st]}; level {fmtL(sim.level)} L",
  len(lc) == 1 and sim.transitions.get('T10') == 1 and sim.st == 0 and sim.level == 0 and not sim.tank_dirty)
# coverage and invariants
missing = [f"T{i}" for i in range(1, 21) if not sim.transitions.get(f"T{i}")]
T('C1', 'Transition coverage', 'T1-T20 each exercised at least once', f"{dict(sorted(sim.transitions.items(), key=lambda x: int(x[0][1:])))}; missing {missing or 'none'}", not missing)
codes = {}
for e in evs('ALARM'):
    c = int(e['detail'].split(' ')[0]); codes[c] = codes.get(c, 0) + 1
T('C2', 'Alarm coverage (event log)', 'Codes 1-6 each raised at least once', f"{dict(sorted(codes.items()))}", all(codes.get(c) for c in range(1, 7)))
T('C3', 'Output matrix, checked every 100 ms tick', 'Valves and motor match §8 for state/sub-step', f"{sim.t} ticks, violations {sim.output_violations}", sim.output_violations == 0)
fac = {v: 1.0 for v in INLETS}
for f in SCENARIO['faults'].values():
    if f['kind'] == 'flow':
        fac[f'IN_P{f["product"]}'] = max(fac[f'IN_P{f["product"]}'], f['factor'])
max_tick = max(round(NOM[v] * fac[v]) for v in INLETS)   # largest inflow in one tick in this run
T('C4', 'Overflow bound', 'Level never above 101 L by more than one tick of flow', f"max level {sim.max_level / CL:.2f} L; bound {(LIMIT + max_tick) / CL:.2f} L", sim.max_level <= LIMIT + max_tick)
bad_starts = [s for s in sim.start_log if (s.get('code') == 'T3' and s['last'] != s['recipe']) or
              (s.get('code') == 'T4' and s['last'] == s['recipe']) or (s.get('code') in ('T1', 'T18') and s['dirty']) or
              (s.get('code') == 'T2' and not s['dirty'])]
T('C5', 'Cleaning criterion at every Start', 'Rule 5: clean when recipe differs or last recipe unknown; T1 only with clean tank',
  f"{len(sim.start_log)} starts; codes {sorted({s.get('code') for s in sim.start_log})}; violations {len(bad_starts)}", not bad_starts)
T('C6', 'Scrap reconciliation', 'Sum of scrap per row = litres through OUT_SCRAP',
  f"rows {fmtL(sum(r['scrap'] for r in rows))} L; total {fmtL(sim.scrap_total)} L", sum(r['scrap'] for r in rows) == sim.scrap_total)
ends = sim.transitions.get('T13', 0) + sim.transitions.get('T14', 0)
T('C7', 'Cleanings finished', 'Counted at the end of the drain step', f"counter {sim.kpi['cleanings']}; T13+T14 {ends}", sim.kpi['cleanings'] == ends)
badv = [r['n'] for r in rows if r['status'] == 'COMPLETED' and r['vol_prod'] != r['vol_used'] * CL]
T('C8', 'Produced volume of COMPLETED rows', 'Sum of delivered doses equals batch volume (no deviation injected)', f"mismatches {badv or 'none'}", not badv)
badp = []
for r in rows:
    if r['status'] != 'COMPLETED':
        continue
    rc = recipes[r['recipe']]; p = plan_doses(r['vol_used'], rc['pct'])
    exp_s = sum(p[i] / NOM[f'IN_P{i+1}'] for i in range(3)) / TPS + rc['mix_s'] + r['vol_used'] / 0.2
    got = (r['OUT'] - r['IN']).total_seconds()
    if abs(got - exp_s) > 0.11:
        badp.append((r['n'], got, exp_s))
T('C9', 'Process time = OUT - IN', 'Fill + mix + empty at nominal rates (§3)', f"rows checked {sum(1 for r in rows if r['status'] == 'COMPLETED')}, mismatches {badp or 'none'}", not badp)
T('O1', 'Fill deviation within tolerance', 'Written in Remarks when it occurs (§12)',
  'Not observed: time-based dosing at nominal flow delivers exact doses; only injected faults deviate', True, 'OBS')
T('O2', 'Cleaning liquid through OUT_SCRAP', 'Scrap = litres drained through OUT_SCRAP (§13)',
  f"After F6, 40.0 L of cleaning liquid went to scrap in the next pre-batch cleaning and is counted as scrap", True, 'OBS')
T('O3', 'Alarm 3 retry starts with T18 from a clean tank', 'T18: Start -> Filling_OP', 'Rule 5 (last recipe unknown) does not force a second cleaning because the tank is clean', True, 'OBS')

# ------------------------------------------------------------------ report workbook
wb = openpyxl.load_workbook(TPL)
ws = wb['today']
for i, r in enumerate(rows):
    x = i + 2
    ws.cell(x, 1).value = r['n']; ws.cell(x, 2).value = r['batch']; ws.cell(x, 3).value = r['recipe']
    ws.cell(x, 4).value = r['vol_order']
    ws.cell(x, 5).value = round(r['vol_prod'] / CL, 2) if r['vol_prod'] is not None else None
    ws.cell(x, 6).value = r['IN']; ws.cell(x, 7).value = r['OUT']
    ws.cell(x, 9).value = round(r['clean_s'], 1) if r['clean_s'] else None
    ws.cell(x, 10).value = r['status']
    ws.cell(x, 11).value = '; '.join(r['alarms']) or None
    ws.cell(x, 12).value = remarks_text(r) or None
for x in range(len(rows) + 2, 202):          # clear the unused row numbers
    ws.cell(x, 1).value = None

# Events: extend beyond the template rows, copying row 2 style
ev = wb['Events']
st2 = [copy.copy(ev.cell(2, c)._style) for c in range(1, 7)]
for i, e in enumerate(events):
    x = i + 2
    vals = [e['t'], e['clock'], e['type'], e['batch'], e['state'], e['detail']]
    for c, v in enumerate(vals, 1):
        cell = ev.cell(x, c); cell.value = v; cell._style = copy.copy(st2[c - 1])
    ev.cell(x, 2).number_format = 'dd.mm.yyyy hh:mm:ss'

# Summary: VC_ARG_04 header, run values, v4 rows
sm = wb['Summary']
sm['A1'] = 'VC_ARG_04 · Summary (simulated data)'
lab = {sm.cell(x, 1).value: x for x in range(1, sm.max_row + 1) if sm.cell(x, 1).value}
sm.cell(lab['Cleanings completed (from the run)'], 2).value = sim.kpi['cleanings']
sm.cell(lab['Scrap generated (L) (from the run)'], 2).value = round(sim.scrap_total / CL, 2)
sm.cell(lab['Duration (h:mm:ss)'], 2).number_format = '[h]:mm:ss'
for k in ('First IN', 'Last OUT'):
    sm.cell(lab[k], 2).number_format = 'dd.mm.yyyy hh:mm:ss'
stop_clean = sum(float(rm.split('Normal Stop ')[1].split(' s')[0]) for r in rows for rm in r['remarks'] if rm.startswith('Final cleaning after Normal Stop'))
extra = [
    ('Batches SKIPPED', '=COUNTIF(today!J2:J201,"SKIPPED")', 'Cancelled after alarm 6'),
    ('Alarm 6 Batch not allowed (rows)', '=COUNTIF(today!K2:K201,"*6 –*")', ''),
    ('Litres not produced (L)', '=SUMIF(today!J2:J201,"SKIPPED",today!D2:D201)', 'Vol. order of SKIPPED rows'),
    ('Partial batches', '=COUNTIF(today!K2:K201,"*5 –*")', 'Rows with alarm 5'),
    ('Total cleaning time incl. Normal Stop cleanings (s)', round(sum(r['clean_s'] for r in rows) + stop_clean, 1),
     'Column I plus cleanings after Normal Stop (from the run)'),
]
for c in range(1, 7):
    extra.append((f"Alarm {c} {ALARM_NAME[c]} raised (event log)", codes.get(c, 0), 'From the run; includes alarms without a row'))
x0 = sm.max_row + 2
sm.cell(x0 - 1, 1).value = 'VC_ARG_04 additions'; sm.cell(x0 - 1, 1).font = Font(bold=True)
for i, (a, b, c) in enumerate(extra):
    sm.cell(x0 + i, 1).value = a; sm.cell(x0 + i, 2).value = b; sm.cell(x0 + i, 3).value = c
    for k in (1, 2, 3):
        sm.cell(x0 + i, k)._style = copy.copy(sm.cell(4, k)._style)

# Legend: v4 wording
lg = wb['Legend']
lg['A1'] = 'VC_ARG_04 · Legend'
for x in range(1, lg.max_row + 1):
    if lg.cell(x, 1).value == 'STATUS':
        lg.cell(x, 2).value = 'PENDING, RUNNING, COMPLETED, ABORTED (ALARM), SKIPPED (cancelled after alarm 6)'
    if lg.cell(x, 1).value == 'Remarks':
        lg.cell(x, 2).value += ', cancellation reason, cleaning breakdown'
        rx = x
lg.insert_rows(rx)
lg.cell(rx, 1).value = '6 – Batch not allowed'
lg.cell(rx, 2).value = 'Pending batch volume outside 40-100 L or recipe not approved / not valid; Start refused; cleared by Cancel batch (warning)'
for k in (1, 2):
    lg.cell(rx, k)._style = copy.copy(lg.cell(rx - 1, k)._style)

# Test results sheet
ts = wb.create_sheet('Test results')
hdr = ['ID', 'Scenario', 'Specification expectation', 'Observed (from the run)', 'Result']
hfill = PatternFill('solid', fgColor='D9E1F2')
for c, h in enumerate(hdr, 1):
    cell = ts.cell(1, c); cell.value = h; cell.font = Font(bold=True); cell.fill = hfill
    cell.alignment = Alignment(wrap_text=True, vertical='top')
for i, t in enumerate(tests):
    for c, k in enumerate(['id', 'scenario', 'expect', 'observed', 'result'], 1):
        cell = ts.cell(i + 2, c); cell.value = t[k]; cell.alignment = Alignment(wrap_text=True, vertical='top')
    rc = ts.cell(i + 2, 5)
    rc.font = Font(bold=True, color={'PASS': '1B7F3B', 'FAIL': 'C00000'}.get(t['result'], '7F6000'))
for c, w in zip('ABCDE', (6, 40, 55, 90, 14)):
    ts.column_dimensions[c].width = w
ts.freeze_panes = 'A2'

OUT.mkdir(exist_ok=True)
REPORT = OUT / 'VC_ARG_04_Production_Orders_Report.xlsx'
wb.save(REPORT)

# ------------------------------------------------------------------ CSV 5 s
cols = ['t_s', 'clock', 'stEtapa', 'state', 'stSubLimpieza', 'stProducto', 'pvNivel_L',
        'IN_P1', 'IN_P2', 'IN_P3', 'IN_CLEAN', 'OUT_NORMAL', 'OUT_SCRAP', 'OUT_RECYCLE', 'MOT',
        'stAlarma', 'loteIdx', 'reportRow', 'loteId', 'volScrapTotal_L']
with open(OUT / 'VC_ARG_04_sim_log_5s.csv', 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\n'); w.writerow(cols)
    for s in sim.log5:
        w.writerow([s['t'], s['clock'], s['stEtapa'], s['state'], s['stSubLimpieza'], s['stProducto'], s['pvNivel_L'],
                    s['stIN_P1'], s['stIN_P2'], s['stIN_P3'], s['stIN_CLEAN'], s['stOUT_NORMAL'], s['stOUT_SCRAP'],
                    s['stOUT_RECYCLE'], s['stMOT'], s['stAlarma'], s['loteIdx'], s['reportRow'], s['loteId'], s['volScrapTotal_L']])

# ------------------------------------------------------------------ data for dashboard / HMI
iso = lambda d: d.strftime('%Y-%m-%dT%H:%M:%S') if d else None
data = dict(
    start=iso(START), end=iso(sim.clock()),
    rows=[dict(n=r['n'], batch=r['batch'], recipe=r['recipe'], vol_order=r['vol_order'],
               vol_prod=round(r['vol_prod'] / CL, 2) if r['vol_prod'] is not None else None,
               IN=iso(r['IN']), OUT=iso(r['OUT']),
               process_s=round((r['OUT'] - r['IN']).total_seconds(), 1) if r['IN'] and r['OUT'] else None,
               clean_s=round(r['clean_s'], 1) if r['clean_s'] else None, status=r['status'],
               alarms='; '.join(r['alarms']), remarks=remarks_text(r), scrap=round(r['scrap'] / CL, 2),
               vol_used=r['vol_used']) for r in rows],
    events=[dict(t=e['t'], clock=iso(e['clock']), type=e['type'], batch=e['batch'], state=e['state'], detail=e['detail'])
            for e in events],
    log=sim.log5,
    kpi=dict(completed=sim.kpi['ok'], aborted=sim.kpi['abort'], skipped=sim.kpi['cancel'], cleanings=sim.kpi['cleanings'],
             scrap_L=round(sim.scrap_total / CL, 2), not_produced_L=round(sim.not_produced / CL, 2),
             produced_L=round(sum(r['vol_prod'] for r in rows if r['vol_prod']) / CL, 2),
             alarms=codes, max_level=sim.max_level / CL),
    tests=tests, transitions=sim.transitions)
json.dump(data, open(OUT / 'sim_data.json', 'w'), default=str)
# dashboard datasets
DASH = ROOT / 'dashboard' / 'data'
DASH.mkdir(parents=True, exist_ok=True)
for e in data['events']:
    e['code'] = int(e['detail'].split(' ')[0]) if e['type'] == 'ALARM' else None
json.dump(data['rows'], open(DASH / 'VC_ARG_04_report_rows.json', 'w'))
json.dump(data['events'], open(DASH / 'VC_ARG_04_events.json', 'w'))
shutil.copy(OUT / 'VC_ARG_04_sim_log_5s.csv', DASH / 'VC_ARG_04_sim_log_5s.csv')


print('rows', len(rows), 'events', len(events), 'log5', len(sim.log5), 'end', sim.clock())
print('kpi', data['kpi'])
for t in tests:
    print(t['id'], t['result'], '|', t['observed'][:150])
