"""VC_ARG_04 batch mixing tank simulator.

Follows VC_ARG_04 Operation specification v4.0. 100 ms tick.
Volumes are kept as integer centilitres (cL) to avoid float drift.
"""
import random, json, datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import openpyxl

TICK_S = 0.1
TPS = 10                      # ticks per second
CL = 100                      # cL per litre
LIMIT = 101 * CL              # overflow limit (strictly greater)
CLEAN_VOL = 40 * CL
CLEAN_MIX_S = 300
VMIN, VMAX = 40, 100
NOM = {'IN_P1': 10, 'IN_P2': 10, 'IN_P3': 5, 'IN_CLEAN': 10,          # cL per tick
       'OUT_NORMAL': 2, 'OUT_SCRAP': 10, 'OUT_RECYCLE': 10}
INLETS = ['IN_P1', 'IN_P2', 'IN_P3', 'IN_CLEAN']
OUTLETS = ['OUT_NORMAL', 'OUT_SCRAP', 'OUT_RECYCLE']
VALVES = INLETS + OUTLETS
ST_NAME = {0: 'Stopped', 1: 'Filling_OP', 2: 'Mixing_OP', 3: 'Empty_OP', 4: 'Waiting',
           5: 'Cleaning_OP', 9: 'Alarm Stop'}
SUB_NAME = {0: '', 1: 'scrap', 2: 'fill', 3: 'mix', 4: 'drain'}
ALARM_NAME = {1: 'Overflow', 2: 'Emergency Stop', 3: 'Fill deviation', 4: 'Step timeout',
              5: 'Partial batch', 6: 'Batch not allowed'}
REASON = {'PRE_BATCH': 1, 'STOP': 2, 'ALARM': 3}
WINDOW = 15 * TPS


def L(cl):
    return round(cl / CL, 2)


def fmtL(cl):
    return f"{cl / CL:.1f}"


# ---------------------------------------------------------------- master data
def load_recipes(path):
    ws = openpyxl.load_workbook(path, data_only=False)['recipes']
    rec = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        rid = r[1]
        if rid is None:
            continue
        p = r[2:5]; mix = r[5]; appr = r[6]
        problems = []
        if not (isinstance(rid, str) and len(rid) == 4 and rid[0] == 'R' and rid[1:].isdigit()):
            problems.append('Recipe ID format')
        if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in p):
            problems.append('percentages missing or not integer')
        elif sum(p) != 100:
            problems.append('percentages do not add up to 100')
        if not isinstance(mix, int) or not (5 <= mix <= 600):
            problems.append('mixing time missing or outside 5-600 s')
        if appr not in ('YES', 'NO'):
            problems.append('Approved missing or not YES/NO')
        rec[rid] = dict(id=rid, pct=list(p), mix_s=mix, approved=(appr == 'YES'),
                        valid=not problems, problems=problems)
    return rec


def load_orders(path):
    ws = openpyxl.load_workbook(path)['today']
    out = []
    for r in ws.iter_rows(min_row=2, max_col=4, values_only=True):
        if r[1] is None:
            continue
        out.append(dict(n=r[0], batch=r[1], recipe=r[2], vol=r[3]))
    return out


def validate_list(orders, recipes):
    """Spec §4: list rejection rules."""
    errs = []
    seen = set()
    for o in orders:
        if not isinstance(o['batch'], str):
            errs.append(f"{o['batch']}: Batch ID is not text")
        if o['batch'] in seen:
            errs.append(f"{o['batch']}: duplicate Batch ID")
        seen.add(o['batch'])
        if o['recipe'] not in recipes:
            errs.append(f"{o['batch']}: unknown recipe {o['recipe']}")
        elif sum(x for x in recipes[o['recipe']]['pct'] if isinstance(x, int)) != 100:
            errs.append(f"{o['batch']}: recipe percentages not 100")
        if not isinstance(o['vol'], int) or isinstance(o['vol'], bool):
            errs.append(f"{o['batch']}: volume not integer")
    return errs


def plan_doses(vol_l, pct):
    """Spec §4: Prd_1, Prd_2 rounded half up to 0.1 L; Prd_3 remainder;
    if Prd_3 is 0 %, the remainder goes to the last non-zero product. Returns cL."""
    V = Decimal(vol_l)
    q = lambda x: (V * x / 100).quantize(Decimal('0.1'), ROUND_HALF_UP)
    if pct[2] > 0:
        p1, p2 = q(pct[0]), q(pct[1])
        p = [p1, p2, V - p1 - p2]
    else:
        if pct[1] > 0:
            p1 = q(pct[0]); p = [p1, V - p1, Decimal(0)]
        else:
            p = [V, Decimal(0), Decimal(0)]
    return [int(x * CL) for x in p]


def tol_exceeded(dev_cl, plan_cl):
    """Alarm 3: |delivered - planned| > min(5 % of planned, 1.0 L), strictly greater."""
    dev = abs(dev_cl)
    return dev * 100 > plan_cl * 5 or dev > 1 * CL


def batch_allowed(o, recipes):
    """Spec rule 3 / alarm 6. Returns reason text or None."""
    v = o['vol']
    if v < VMIN:
        return f"Volume {v} L below minimum {VMIN} L"
    if v > VMAX:
        return f"Volume {v} L above maximum {VMAX} L"
    r = recipes[o['recipe']]
    if not r['valid']:
        return f"Recipe {r['id']} not valid"
    if not r['approved']:
        return f"Recipe {r['id']} not approved"
    return None


# ---------------------------------------------------------------- simulator
class Sim:
    def __init__(self, orders, recipes, start_clock, scenario, seed=7):
        self.orders, self.recipes = orders, recipes
        self.t = 0
        self.t0 = start_clock
        self.rng = random.Random(seed)
        self.sc = scenario
        # plant
        self.level = 0
        self.cmd = {v: False for v in VALVES}; self.mot = False
        self.flow_factor = {v: 1.0 for v in VALVES}
        self.stuck_open = set()
        # controller
        self.st = 0; self.sub = 0; self.prod = 0
        self.tank_dirty = False; self.last_recipe = None
        self.stop_req = False; self.retry_row = None; self.clean_reason = None
        self.alarm = 0; self.alarm_origin = 0; self.alarm_text = ''
        self.alarm5 = False; self.alarm6 = False; self.alarm_cause = None
        self.msg = ''
        self.confirm = None          # pending volume awaiting confirmation
        self.next_order = 0
        self.checked_row = None; self.pending_since = None
        self.active_row = None       # row of the running batch (or batch being prepared)
        self.cur_vol = None; self.plan = [0, 0, 0]; self.dos = [0, 0, 0]
        self.step_t0 = 0; self.step_lvl0 = 0; self.win_t0 = 0; self.win_lvl0 = 0
        self.step_exp_ticks = 0; self.step_rate = 0; self.dose_ticks = 0; self.step_n = 0; self.win_n0 = 0
        self.clean_t0 = None; self.clean_n = 0; self.discharged = 0
        self.scrap_total = 0; self.scrap_batch = 0
        self.kpi = dict(ok=0, abort=0, cancel=0, cleanings=0)
        self.last_cycle_s = 0.0; self.not_produced = 0
        self.pending_clean_note = []   # notes for the next record
        # report rows
        self.rows = []
        for i, o in enumerate(orders):
            self.rows.append(dict(n=i + 1, batch=o['batch'], recipe=o['recipe'], vol_order=o['vol'],
                                  vol_prod=None, IN=None, OUT=None, clean_s=0.0, clean_parts=[],
                                  status='PENDING', alarms=[], remarks=[], scrap=0, retry_of=None,
                                  vol_used=None, order_idx=i))
        # logs
        self.events = []; self.log5 = []; self.hmi = []
        self.max_level = 0
        self.output_violations = 0
        self.transitions = {}
        # operator
        self.op_next = None; self.op_action = None
        self.op_mem = dict(tried_start=set(), end_tried=False, end_stopped=False,
                           script_pos={}, waiting_repair=False)
        self.faults_armed = {}; self.fault_log = []
        self.done = False
        self.list_rejected = None
        self.start_log = []

    # ------------------------------------------------------------ helpers
    def clock(self, t=None):
        t = self.t if t is None else t
        return self.t0 + dt.timedelta(seconds=t / TPS)

    def ev(self, typ, detail, batch=None):
        if batch is None:
            r = self.active_row if self.active_row is not None else self.pending_row()
            batch = self.rows[r]['batch'] if r is not None else ''
        self.events.append(dict(t=round(self.t / TPS, 1), clock=self.clock(), type=typ, batch=batch,
                                state=ST_NAME[self.st] + (f"/{SUB_NAME[self.sub]}" if self.st == 5 and self.sub else ''),
                                detail=detail))

    def trans(self, code, new_state, detail=''):
        if code in ('T1', 'T2', 'T3', 'T4', 'T18') and self.start_log and 'code' not in self.start_log[-1]:
            self.start_log[-1]['code'] = code
        old = self.st
        self.st = new_state
        self.transitions[code] = self.transitions.get(code, 0) + 1
        self.ev('STATE', f"{code}: {ST_NAME[old]} -> {ST_NAME[new_state]}" + (f" ({detail})" if detail else ''))

    def pending_row(self):
        if self.retry_row is not None:
            return self.retry_row
        if self.next_order < len(self.orders):
            return self.next_order
        return None

    def all_off(self):
        for v in VALVES:
            self.cmd[v] = False
        self.mot = False

    def outputs(self):
        return {**{v: self.cmd[v] for v in VALVES}, 'MOT': self.mot}

    def start_step(self, rate, exp_ticks):
        self.step_n = 0                              # ticks of process time in this step
        self.step_t0 = self.t; self.step_lvl0 = self.level
        self.win_n0 = 0; self.win_lvl0 = self.level
        self.step_rate = rate; self.step_exp_ticks = exp_ticks

    # ------------------------------------------------------------ alarms
    def raise_emergency(self, code, origin, text):
        """T16. Alarms 1, 2, 4."""
        prev = self.st
        prev_sub = self.sub
        self.all_off()
        row = self.active_row
        self.alarm = code; self.alarm_origin = origin; self.alarm_text = text
        self.ev('ALARM', f"{code} – {ALARM_NAME[code]}: {text}")
        self.stop_req = False            # an alarm cancels a pending Normal Stop
        if prev in (1, 2, 3) and row is not None:
            r = self.rows[row]
            r['status'] = 'ABORTED (ALARM)'; r['OUT'] = self.clock()
            r['alarms'].append(f"{code} – {ALARM_NAME[code]}")
            r['remarks'].append(f"Alarm {code}: {text}")
            if prev == 3 and self.discharged > 0:
                self.alarm5 = True
                r['alarms'].append("5 – Partial batch")
                r['remarks'].append(f"Partial batch: {fmtL(self.discharged)} L discharged, {fmtL(self.level)} L left in the tank")
                self.ev('ALARM', f"5 – Partial batch (cause alarm {code}): {fmtL(self.discharged)} L discharged, {fmtL(self.level)} L left")
            self.kpi['abort'] += 1
            self.make_retry(row)
            self.active_row = None
        elif prev == 5 and self.clean_reason == 'PRE_BATCH':
            # cleaning interrupted: batch stays pending; note goes to the next record
            pr = self.pending_row()
            if pr is not None:
                self.rows[pr]['status'] = 'PENDING'
                self.rows[pr]['remarks'].append(
                    f"Pre-batch cleaning interrupted by alarm {code} at {self.clock():%H:%M:%S} ({SUB_NAME[prev_sub]} step)")
            self.active_row = None
        elif prev == 5:
            pr = self.retry_row if self.retry_row is not None else self.pending_row()
            if pr is not None:
                self.rows[pr]['remarks'].append(
                    f"{self.clean_reason} cleaning interrupted by alarm {code} at {self.clock():%H:%M:%S}")
        self.trans('T16', 9, f"alarm {code}")
        self.sub = 0; self.prod = 0; self.clean_t0 = None

    def make_retry(self, row):
        src = self.rows[row]
        n = len(self.rows) + 1
        if src['retry_of'] is None:
            self.next_order += 1                     # the order is now carried by its repeat row
        self.rows.append(dict(n=n, batch=src['batch'], recipe=src['recipe'], vol_order=src['vol_order'],
                              vol_prod=None, IN=None, OUT=None, clean_s=0.0, clean_parts=[],
                              status='PENDING', alarms=[], remarks=[f"Retry of #{src['n']}"], scrap=0,
                              retry_of=src['n'], vol_used=src['vol_used'], order_idx=src['order_idx']))
        self.retry_row = n - 1

    def cause_present(self):
        if self.alarm == 1:
            return self.level > LIMIT and any(self.cmd[v] or v in self.stuck_open for v in INLETS)
        if self.alarm == 4:
            return any(f['active'] and f['kind'] in ('noflow', 'stuck_open') for f in self.faults_armed.values())
        return False

    # ------------------------------------------------------------ commands
    def command(self, name, **kw):
        self.ev('CMD', name + (f" vol={kw['vol']}" if 'vol' in kw else ''))
        getattr(self, 'c_' + name)(**kw)

    def refuse(self, why):
        self.msg = why
        self.ev('REFUSAL', why)

    def c_cmdMarcha(self, vol):
        if self.list_rejected:
            return self.refuse('Start refused: order list rejected')
        if self.st == 9:
            return self.refuse('Start refused: Alarm Stop active')
        if self.st not in (0, 4):
            return self.refuse(f'Start refused: state {ST_NAME[self.st]}')
        pr = self.pending_row()
        if pr is None:
            return self.refuse('Start refused: LIST COMPLETE')
        if self.alarm6:
            return self.refuse('Start refused: alarm 6 active, use Cancel batch')
        if self.confirm is not None:
            return self.refuse('Start refused: volume dialog open')
        row = self.rows[pr]
        if row['retry_of'] is not None:              # repeat keeps the interrupted volume
            return self.begin(pr, row['vol_used'])
        if not isinstance(vol, int) or not (VMIN <= vol <= VMAX):
            return self.refuse(f'Volume {vol} L rejected: integer 40-100 L required')
        if vol != row['vol_order']:
            self.confirm = vol
            self.ev('INFO', f"Volume dialog: order {row['vol_order']} L, entered {vol} L")
            return
        self.begin(pr, vol)

    def c_cmdConfirmaVol(self):
        if self.confirm is None:
            return self.refuse('Confirm refused: no dialog')
        vol = self.confirm; self.confirm = None
        pr = self.pending_row(); row = self.rows[pr]
        row['remarks'].append(f"Volume order {row['vol_order']} L, entered {vol} L, confirmed by operator")
        self.begin(pr, vol)

    def c_cmdCancelaVol(self):
        if self.confirm is None:
            return self.refuse('Cancel refused: no dialog')
        self.confirm = None
        self.ev('INFO', 'Volume dialog cancelled: nothing starts')

    def c_cmdParo(self):
        if self.st in (1, 2, 3):
            if self.stop_req:
                return self.refuse('Normal Stop already requested')
            self.stop_req = True
            self.transitions['T11'] = self.transitions.get('T11', 0) + 1
            self.ev('STATE', 'T11: Normal Stop requested, batch finishes first')
        elif self.st == 4:
            self.begin_cleaning('STOP', 'T10')
        elif self.st == 5 and self.clean_reason == 'PRE_BATCH':
            if self.stop_req:
                return self.refuse('Normal Stop already requested')
            self.stop_req = True
            self.transitions['T12'] = self.transitions.get('T12', 0) + 1
            self.ev('STATE', 'T12: Normal Stop requested during pre-batch cleaning')
        else:
            self.refuse(f'Normal Stop refused: state {ST_NAME[self.st]}')

    def c_cmdParoEmerg(self):
        if self.st in (1, 2, 3, 4, 5):
            self.raise_emergency(2, 2, 'Emergency Stop pressed by operator')
        else:
            self.refuse(f'Emergency Stop refused: state {ST_NAME[self.st]}')

    def c_cmdRearme(self):
        if self.st != 9:
            return self.refuse('Reset refused: not in Alarm Stop')
        if self.cause_present():
            return self.refuse(f'Reset refused: cause of alarm {self.alarm} still present')
        self.ev('INFO', f'Alarm {self.alarm} reset')
        self.alarm = 0; self.alarm_origin = 0; self.alarm_text = ''; self.alarm5 = False
        self.tank_dirty = True; self.last_recipe = None
        self.trans('T17', 0, 'tank dirty, last recipe unknown')
        self.checked_row = None

    def c_cmdCancelaLote(self):
        if not self.alarm6:
            return self.refuse('Cancel batch refused: alarm 6 not active')
        pr = self.pending_row(); r = self.rows[pr]
        r['status'] = 'SKIPPED'
        r['remarks'].append(f"{self.alarm_text}; ordered {r['vol_order']} L; Cancelled by operator")
        self.not_produced += r['vol_order'] * CL
        self.kpi['cancel'] += 1
        self.alarm6 = False; self.alarm = 0; self.alarm_text = ''
        self.transitions['T20'] = self.transitions.get('T20', 0) + 1
        self.ev('STATE', f"T20: batch {r['batch']} SKIPPED, alarm 6 cleared")
        self.next_order += 1
        self.checked_row = None

    # ------------------------------------------------------------ batch flow
    def begin(self, pr, vol):
        row = self.rows[pr]
        ack3 = self.alarm == 3
        if ack3:
            self.ev('INFO', 'Alarm 3 acknowledged by Start')
            self.alarm = 0; self.alarm_text = ''
        self.active_row = pr
        row['status'] = 'RUNNING'; row['vol_used'] = vol
        rec = self.recipes[row['recipe']]
        self.cur_vol = vol; self.plan = plan_doses(vol, rec['pct']); self.dos = [0, 0, 0]
        self.scrap_batch = 0; self.discharged = 0; self.msg = ''
        self.start_log.append(dict(t=self.t, row=pr, recipe=row['recipe'], last=self.last_recipe,
                                   dirty=self.tank_dirty, state=self.st, ack3=ack3))
        if self.st == 0:
            if not self.tank_dirty:
                self.begin_filling('T18' if ack3 else 'T1')
            else:
                self.begin_cleaning('PRE_BATCH', 'T2')
        else:  # Waiting
            if self.last_recipe is not None and self.last_recipe == row['recipe']:
                self.begin_filling('T3')
            else:
                self.begin_cleaning('PRE_BATCH', 'T4')

    def begin_filling(self, code):
        r = self.rows[self.active_row]
        r['IN'] = self.clock()
        self.trans(code, 1, f"batch {r['batch']} {r['recipe']} {self.cur_vol} L")
        self.prod = 0
        self.next_product()

    def next_product(self):
        p = self.prod + 1
        while p <= 3 and self.plan[p - 1] == 0:
            p += 1                                    # 0 % products are skipped
        if p > 3:
            self.cmd_off_inlets()
            self.prod = 0
            rec = self.recipes[self.rows[self.active_row]['recipe']]
            self.trans('T6', 2, f"mixing {rec['mix_s']} s")
            self.mot = True
            self.start_step(0, rec['mix_s'] * TPS)
            return
        if self.prod:
            self.transitions['T5'] = self.transitions.get('T5', 0) + 1
            self.ev('STATE', f"T5: next product Prd_{p}")
        self.prod = p
        v = f'IN_P{p}'
        self.cmd_off_inlets(); self.cmd[v] = True
        self.dose_ticks = self.plan[p - 1] // NOM[v]
        self.dose_lvl0 = self.level
        self.start_step(NOM[v], self.dose_ticks)
        self.ev('STEP', f"Dosing Prd_{p}: plan {fmtL(self.plan[p-1])} L, {self.dose_ticks / TPS:.1f} s")

    def cmd_off_inlets(self):
        for v in INLETS:
            self.cmd[v] = False

    def end_dose(self):
        p = self.prod; v = f'IN_P{p}'
        self.cmd[v] = False
        delivered = self.level - self.dose_lvl0
        self.dos[p - 1] = delivered
        plan = self.plan[p - 1]
        dev = abs(delivered - plan)
        # tolerance min(5 % of planned, 1.0 L); strictly greater triggers alarm 3
        exceeded = tol_exceeded(dev, plan)
        row = self.rows[self.active_row]
        self.ev('STEP', f"Prd_{p} delivered {fmtL(delivered)} L (plan {fmtL(plan)} L, dev {fmtL(delivered - plan)} L)")
        if exceeded:
            self.alarm3(p, delivered, plan)
            return
        if dev:
            row['remarks'].append(f"Fill deviation Prd_{p} {(delivered - plan) / CL:+.2f} L within tolerance")
        self.next_product()

    def alarm3(self, p, delivered, plan):
        r = self.rows[self.active_row]
        txt = f"Prd_{p} delivered {fmtL(delivered)} L, planned {fmtL(plan)} L"
        self.alarm = 3; self.alarm_origin = 1; self.alarm_text = txt
        self.ev('ALARM', f"3 – Fill deviation: {txt}")
        r['status'] = 'ABORTED (ALARM)'; r['OUT'] = self.clock()
        r['alarms'].append('3 – Fill deviation'); r['remarks'].append(f"Alarm 3: {txt}")
        self.kpi['abort'] += 1
        self.stop_req = False
        self.cmd_off_inlets()
        self.aborted_row = self.active_row
        self.last_recipe = None                      # rule 5: last recipe unknown after an alarm
        self.make_retry(self.active_row)
        self.begin_cleaning('ALARM', 'T15', row_for=self.aborted_row)
        self.active_row = None

    def begin_cleaning(self, reason, code, row_for=None):
        self.clean_reason = reason
        self.clean_row = row_for if row_for is not None else (self.active_row if reason == 'PRE_BATCH' else None)
        self.clean_t0 = self.t; self.clean_n = 0
        self.trans(code, 5, reason)
        self.prod = 0
        self.all_off()
        if self.level > 0:
            self.set_sub(1)
        else:
            self.set_sub(2)

    def set_sub(self, s):
        self.sub = s
        self.all_off()
        if s == 1:
            self.cmd['OUT_SCRAP'] = True
            self.start_step(-NOM['OUT_SCRAP'], -(-self.level // NOM['OUT_SCRAP']))
        elif s == 2:
            self.cmd['IN_CLEAN'] = True; self.mot = True
            self.start_step(NOM['IN_CLEAN'], max(1, (CLEAN_VOL - self.level) // NOM['IN_CLEAN']))
        elif s == 3:
            self.mot = True
            self.start_step(0, CLEAN_MIX_S * TPS)
        elif s == 4:
            self.cmd['OUT_RECYCLE'] = True
            self.start_step(-NOM['OUT_RECYCLE'], -(-self.level // NOM['OUT_RECYCLE']))
        self.ev('STEP', f"Cleaning sub-step {s} {SUB_NAME[s]}")

    def end_cleaning(self):
        dur = self.clean_n / TPS
        self.all_off(); self.sub = 0
        self.tank_dirty = False
        self.kpi['cleanings'] += 1
        reason = self.clean_reason
        if reason == 'PRE_BATCH':
            r = self.rows[self.active_row]
            r['clean_s'] += dur; r['clean_parts'].append(('pre-batch', dur))
            if self.stop_req:
                self.stop_req = False
                r['status'] = 'PENDING'
                self.active_row = None
                self.trans('T14', 0, 'pre-batch cleaning finished, Normal Stop, batch stays pending')
                self.checked_row = None
            else:
                self.trans('T13', 1, f"cleaning {dur:.1f} s")
                r['IN'] = self.clock()
                self.prod = 0
                self.next_product()
        elif reason == 'ALARM':
            r = self.rows[self.clean_row]
            r['clean_s'] += dur; r['clean_parts'].append(('post-alarm', dur))
            self.active_row = None
            self.trans('T14', 0, 'post-alarm cleaning finished')
            self.checked_row = None
        else:  # STOP
            last = self.last_completed_row
            if last is not None:
                self.rows[last]['remarks'].append(f"Final cleaning after Normal Stop {dur:.1f} s")
            self.active_row = None
            self.stop_req = False
            self.trans('T14', 0, 'stop cleaning finished')
            self.checked_row = None
        self.clean_reason = None; self.clean_t0 = None

    def complete_batch(self):
        r = self.rows[self.active_row]
        r['status'] = 'COMPLETED'; r['OUT'] = self.clock()
        r['vol_prod'] = sum(self.dos)
        if r['vol_prod'] != r['vol_order'] * CL:
            r['remarks'].append(f"Produced {fmtL(r['vol_prod'])} L vs order {r['vol_order']} L")
        self.tank_dirty = True; self.last_recipe = r['recipe']
        self.kpi['ok'] += 1
        self.last_cycle_s = (r['OUT'] - r['IN']).total_seconds()
        self.last_completed_row = self.active_row
        if r['retry_of'] is not None:
            self.retry_row = None
        else:
            self.next_order += 1
        if self.stop_req:
            self.trans('T9', 5, 'level 0, Normal Stop pending')
            self.active_row = None
            self.clean_reason = 'STOP'; self.clean_t0 = self.t; self.clean_n = 0; self.clean_row = None
            self.set_sub(2)
        else:
            self.trans('T8', 4, f"batch {r['batch']} COMPLETED")
            self.active_row = None
            self.checked_row = None

    # ------------------------------------------------------------ pending check (rule 3, T19)
    def check_pending(self):
        if self.st not in (0, 4):
            return
        pr = self.pending_row()
        if pr == self.checked_row:
            return
        self.checked_row = pr
        self.pending_since = self.t
        if pr is None:
            self.ev('INFO', 'LIST COMPLETE')
            return
        r = self.rows[pr]
        self.ev('INFO', f"Pending batch {r['batch']} {r['recipe']} {r['vol_order']} L")
        if r['retry_of'] is not None:
            return                                   # a repeat is not checked again
        why = batch_allowed(self.orders[r['order_idx']], self.recipes)
        if why:
            self.alarm6 = True; self.alarm = 6; self.alarm_origin = 1; self.alarm_text = why
            r['alarms'] = ['6 – Batch not allowed']
            self.transitions['T19'] = self.transitions.get('T19', 0) + 1
            self.ev('ALARM', f"6 – Batch not allowed: {why}")
            self.ev('STATE', 'T19: alarm 6 raised, state unchanged')

    # ------------------------------------------------------------ process tick
    def plant(self):
        inflow = 0
        for v in INLETS:
            if self.cmd[v] or v in self.stuck_open:
                inflow += round(NOM[v] * self.flow_factor[v])
        outflow = 0
        for v in OUTLETS:
            if self.cmd[v]:
                outflow += round(NOM[v] * self.flow_factor[v])
        lvl0 = self.level
        self.level = max(0, self.level + inflow - outflow)
        removed = lvl0 + inflow - self.level
        if self.cmd['OUT_SCRAP']:
            self.scrap_total += removed; self.scrap_batch += removed
            row = self.clean_row if self.clean_reason == 'ALARM' else self.active_row
            if row is not None:
                self.rows[row]['scrap'] += removed
        if self.cmd['OUT_NORMAL']:
            self.discharged += removed
        self.max_level = max(self.max_level, self.level)
        self.step_n += 1
        if self.st == 5:
            self.clean_n += 1

    def monitor(self):
        """Alarm 4 progress monitor and step timeout."""
        active = (self.st == 1 and self.prod) or self.st == 3 or (self.st == 5 and self.sub in (1, 2, 4))
        if not active:
            return False
        el = self.step_n
        if el > 1.5 * self.step_exp_ticks + 10 * TPS:
            self.raise_emergency(4, 1, f"step timeout after {el / TPS:.1f} s (expected {self.step_exp_ticks / TPS:.1f} s)")
            return True
        if self.step_n - self.win_n0 >= WINDOW:
            exp = self.step_rate * WINDOW
            moved = self.level - self.win_lvl0
            if moved * (1 if exp > 0 else -1) < 0.2 * abs(exp):
                self.raise_emergency(4, 1, f"no progress: {fmtL(moved)} L in 15 s, expected {fmtL(exp)} L")
                return True
            self.win_n0 = self.step_n; self.win_lvl0 = self.level
        return False

    def control(self):
        if self.st == 1:
            if self.step_n >= self.dose_ticks:
                self.end_dose()
        elif self.st == 2:
            if self.step_n >= self.step_exp_ticks:
                self.mot = False
                self.trans('T7', 3)
                self.cmd['OUT_NORMAL'] = True
                self.start_step(-NOM['OUT_NORMAL'], -(-self.level // NOM['OUT_NORMAL']))
        elif self.st == 3:
            if self.level == 0:
                self.cmd['OUT_NORMAL'] = False
                self.complete_batch()
        elif self.st == 5:
            if self.sub == 1 and self.level == 0:
                self.set_sub(2)
            elif self.sub == 2 and self.level >= CLEAN_VOL:
                self.set_sub(3)
            elif self.sub == 3 and self.step_n >= self.step_exp_ticks:
                self.set_sub(4)
            elif self.sub == 4 and self.level == 0:
                self.end_cleaning()

    def check_outputs(self):
        o = self.outputs()
        exp = {k: False for k in o}
        if self.st == 1 and self.prod:
            exp[f'IN_P{self.prod}'] = True
        elif self.st == 2:
            exp['MOT'] = True
        elif self.st == 3:
            exp['OUT_NORMAL'] = True
        elif self.st == 5:
            if self.sub == 1: exp['OUT_SCRAP'] = True
            if self.sub == 2: exp['IN_CLEAN'] = True; exp['MOT'] = True
            if self.sub == 3: exp['MOT'] = True
            if self.sub == 4: exp['OUT_RECYCLE'] = True
        if o != exp:
            self.output_violations += 1

    def tick(self):
        self.t += 1
        # 1 operator / fault commands scheduled for this tick
        self.faults()
        self.operator()
        # 2 plant
        self.plant()
        # 3 overflow (alarm 1), priority over 3
        if self.st in (1, 5) and self.level > LIMIT and any(self.cmd[v] or v in self.stuck_open for v in INLETS):
            self.raise_emergency(1, 1, f"level {self.level / CL:.2f} L above 101 L with inlet open")
        elif not self.monitor():
            self.control()
        self.check_pending()
        self.check_outputs()
        if self.t % (5 * TPS) == 0:
            self.sample()

    # ------------------------------------------------------------ faults
    def faults(self):
        for fid, f in self.sc['faults'].items():
            st = self.faults_armed.get(fid)
            pr = self.pending_row()
            if st is None:
                # arm 0.5 s after the target batch becomes pending
                if pr is not None and self.rows[pr]['batch'] == f['batch'] and self.rows[pr]['retry_of'] is None \
                        and self.pending_since is not None and self.checked_row == pr \
                        and self.t - self.pending_since >= 5:
                    self.faults_armed[fid] = dict(active=False, fired=False, kind=f['kind'], row=pr, t_arm=self.t)
                    self.ev('FAULT', f"{fid} armed: {f['desc']}")
                continue
            if st['fired'] and not st['active']:
                continue
            k = f['kind']; row = st['row']
            if k == 'flow':
                if not st['active'] and self.active_row == row and self.st == 1 and self.prod == f['product']:
                    self.flow_factor[f'IN_P{f["product"]}'] = f['factor']; st['active'] = st['fired'] = True
                    self.ev('FAULT', f"{fid} active: IN_P{f['product']} flow x{f['factor']}")
                elif st['active'] and self.st in (9, 5, 0):
                    self.flow_factor[f'IN_P{f["product"]}'] = 1.0; st['active'] = False
                    self.ev('FAULT', f"{fid} cleared")
            elif k == 'noflow':
                if not st['active'] and not st['fired'] and self.active_row == row and self.st == 1 and self.prod == f['product']:
                    self.flow_factor[f'IN_P{f["product"]}'] = 0.0; st['active'] = st['fired'] = True
                    self.ev('FAULT', f"{fid} active: IN_P{f['product']} no flow")
                elif st['active'] and self.st == 9:
                    st.setdefault('t_alarm', self.t)
                    if self.t - st['t_alarm'] >= f['repair_s'] * TPS:
                        self.flow_factor[f'IN_P{f["product"]}'] = 1.0; st['active'] = False
                        self.ev('FAULT', f"{fid} repaired after {f['repair_s']} s")
            elif k == 'stuck_open':
                if not st['active'] and not st['fired'] and self.st == 5 and self.clean_reason == 'PRE_BATCH' \
                        and self.sub == f['substep'] and self.pending_row() == row:
                    self.stuck_open.add(f['valve']); st['active'] = st['fired'] = True
                    self.ev('FAULT', f"{fid} active: {f['valve']} stuck open")
                elif st['active'] and self.st == 9:
                    self.stuck_open.discard(f['valve']); st['active'] = False
                    self.ev('FAULT', f"{fid} cleared: {f['valve']} closes when Alarm Stop removes power")
            elif k == 'estop_empty':
                if not st['fired'] and self.active_row == row and self.st == 3 and \
                        self.discharged >= f['frac'] * self.cur_vol * CL:
                    st['fired'] = True
                    self.ev('FAULT', f"{fid} injected: operator Emergency Stop at {fmtL(self.discharged)} L discharged")
                    self.command('cmdParoEmerg')
            elif k == 'estop_waiting':
                if not st['fired'] and self.st == 4:
                    st['fired'] = True
                    self.ev('FAULT', f"{fid} injected: operator Emergency Stop in Waiting")
                    self.command('cmdParoEmerg')
            elif k == 'stop_mixing':
                if not st['fired'] and self.active_row == row and self.st == 2 and \
                        self.step_n >= f['frac'] * self.step_exp_ticks:
                    st['fired'] = True
                    self.ev('FAULT', f"{fid} injected: operator Normal Stop during Mixing")
                    self.command('cmdParo')
            elif k == 'stop_preclean':
                if not st['fired'] and self.active_row == row and self.st == 5 and self.sub == f['substep'] and \
                        self.step_n >= f['frac'] * self.step_exp_ticks:
                    st['fired'] = True
                    self.ev('FAULT', f"{fid} injected: operator Normal Stop during pre-batch cleaning")
                    self.command('cmdParo')

    # ------------------------------------------------------------ operator
    def reaction(self):
        return round(self.rng.uniform(3, 8) * TPS)

    def operator(self):
        if self.op_next is not None:
            if self.t >= self.op_next:
                act = self.op_action
                self.op_next = None; self.op_action = None
                self.op_execute(act)
            return
        act = self.op_decide()
        if act:
            self.op_next = self.t + self.reaction(); self.op_action = act

    def op_decide(self):
        m = self.op_mem
        if self.st == 9:
            if m['waiting_repair'] and self.cause_present():
                return None
            return ('reset',)
        if self.confirm is not None:
            return ('dialog',)
        if self.st not in (0, 4):
            return None
        pr = self.pending_row()
        if pr is None:
            if self.st == 0 and m['end_stopped']:
                self.done = True; return None
            if not m['end_tried']:
                return ('start_end',)
            if self.st == 4 and not m['end_stopped']:
                return ('stop_end',)
            return None
        if self.alarm6:
            if pr not in m['tried_start']:
                return ('start_refused', pr)
            return ('cancel', pr)
        return ('start', pr)

    def op_execute(self, act):
        m = self.op_mem
        k = act[0]
        if k == 'reset':
            self.command('cmdRearme')
            if self.st == 9:
                m['waiting_repair'] = True
            else:
                m['waiting_repair'] = False
        elif k == 'dialog':
            ans = self.dialog_answer
            self.command('cmdConfirmaVol' if ans == 'confirm' else 'cmdCancelaVol')
        elif k == 'start_end':
            m['end_tried'] = True
            self.command('cmdMarcha', vol=100)
        elif k == 'stop_end':
            m['end_stopped'] = True
            self.command('cmdParo')
        elif k in ('start_refused', 'cancel', 'start'):
            pr = self.pending_row()
            if pr != act[1] or self.st not in (0, 4):
                return
            r = self.rows[pr]
            if k == 'start_refused':
                m['tried_start'].add(pr)
                self.command('cmdMarcha', vol=r['vol_order'])
            elif k == 'cancel':
                self.command('cmdCancelaLote')
            else:
                script = self.sc['typed'].get(r['batch']) if r['retry_of'] is None else None
                pos = m['script_pos'].get(pr, 0)
                if script and pos < len(script):
                    vol, ans = script[pos]
                    m['script_pos'][pr] = pos + 1
                    self.dialog_answer = ans
                else:
                    vol = r['vol_order'] if r['retry_of'] is None else r['vol_used']
                    self.dialog_answer = 'confirm'
                self.command('cmdMarcha', vol=vol)

    # ------------------------------------------------------------ sampling
    def snapshot(self):
        pr = self.active_row if self.active_row is not None else self.pending_row()
        r = self.rows[pr] if pr is not None else None
        rec = self.recipes[r['recipe']] if r else None
        return dict(t=round(self.t / TPS, 1), clock=self.clock().strftime('%d.%m.%Y %H:%M:%S'),
                    stEtapa=self.st, state=ST_NAME[self.st], stSubLimpieza=self.sub, stProducto=self.prod,
                    stMotivoLimpieza=REASON.get(self.clean_reason, 0) if self.st == 5 else 0,
                    pvNivel_L=L(self.level), **{('st' + k): int(v) for k, v in self.outputs().items()},
                    stAlarma=self.alarm if not self.alarm6 else 6, stAlarmaOrigen=self.alarm_origin,
                    stAlarmaTexto=self.alarm_text, stLoteParcial=int(self.alarm5), stLoteRechazado=int(self.alarm6),
                    stTanqueSucio=int(self.tank_dirty), stParoSolicitado=int(self.stop_req),
                    stReintento=int(self.retry_row is not None), stListaCompleta=int(self.pending_row() is None),
                    stConfirmaVol=int(self.confirm is not None), stMensaje=self.msg,
                    loteIdx=(r['order_idx'] + 1) if r else 0, loteTotal=len(self.orders),
                    reportRow=r['n'] if r else 0, loteId=r['batch'] if r else '', recetaId=r['recipe'] if r else '',
                    ultimaReceta=self.last_recipe or '', recetaAprobada=int(rec['approved']) if rec else 0,
                    volOrden_L=r['vol_order'] if r else 0,
                    volLote_L=(self.cur_vol if self.active_row is not None else (r['vol_used'] or r['vol_order'])) if r else 0,
                    recPct=rec['pct'] if rec else [0, 0, 0], tMezclaRec_s=rec['mix_s'] if rec else 0,
                    plan_L=[L(x) for x in self.plan] if self.active_row is not None else [0, 0, 0],
                    dos_L=[L(x) for x in self.dos] if self.active_row is not None else [0, 0, 0],
                    volDescargado_L=L(self.discharged), volScrapLote_L=L(self.scrap_batch),
                    volScrapTotal_L=L(self.scrap_total), tEtapa_s=round(self.step_n / TPS, 1),
                    kpiLotesOK=self.kpi['ok'], kpiLotesAbort=self.kpi['abort'], kpiLotesCancel=self.kpi['cancel'],
                    kpiLimpiezas=self.kpi['cleanings'], kpiUltimoCiclo_s=self.last_cycle_s,
                    volNoProducido_L=L(self.not_produced))

    def sample(self):
        s = self.snapshot()
        self.log5.append(s)

    # ------------------------------------------------------------ run
    def run(self, max_hours=24):
        errs = validate_list(self.orders, self.recipes)
        if errs:
            self.list_rejected = errs
            for e in errs:
                self.ev('REFUSAL', 'List rejected: ' + e, batch='')
            return
        self.ev('INFO', f"Order list loaded: {len(self.orders)} batches", batch='')
        self.last_completed_row = None
        self.check_pending()
        self.sample()
        while not self.done and self.t < max_hours * 3600 * TPS:
            self.tick()
        self.sample()
