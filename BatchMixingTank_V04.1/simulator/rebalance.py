"""Spec v4.1 section 4: rebalance short last sub-batches into a REBALANCED copy of the order list.

Usage: python simulator/rebalance.py inputs/VC_ARG_03_Production_Orders_Template.xlsx inputs/VC_ARG_03_Production_Orders_REBALANCED.xlsx
"""
import sys, openpyxl
from collections import OrderedDict
src, dst = sys.argv[1], sys.argv[2]
MIN = 40
wb = openpyxl.load_workbook(src)
ws = wb['today']
rows = [r for r in range(2, ws.max_row+1) if ws.cell(r,2).value]
groups = OrderedDict()
for r in rows:
    groups.setdefault(str(ws.cell(r,2).value).split('.')[0], []).append(r)
changes = []
for order, rs in groups.items():
    if len(rs) < 2: continue
    last = rs[-1]; v = ws.cell(last,4).value
    if v >= MIN: continue
    short = MIN - v
    donor = None
    for cand in reversed(rs[:-1]):          # immediately preceding first, then the one before
        if ws.cell(cand,4).value - short >= MIN:
            donor = cand; break
    if donor is None:
        changes.append((order, 'NO DONOR, unchanged')); continue
    before = [ws.cell(x,4).value for x in rs]
    ws.cell(donor,4).value -= short
    ws.cell(last,4).value = MIN
    after = [ws.cell(x,4).value for x in rs]
    assert sum(before) == sum(after)
    changes.append((order, f'{before} -> {after}'))
# header per project rule
r = wb['Rules']
r['A1'] = 'VC_ARG_04 · Rules'
nxt = r.max_row + 1
r.cell(nxt,1).value = ('REBALANCED (spec VC_ARG_04 §4): when the last sub-batch of an order is below 40 L, '
    'the shortfall is taken from the preceding sub-batch; order totals unchanged. Changed: ' +
    '; '.join(f'{o} {c}' for o,c in changes))
wb.save(dst)
for c in changes: print(*c)
