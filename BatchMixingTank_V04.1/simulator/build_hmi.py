"""Usage (from the repository root, after run_scenario.py):  python simulator/build_hmi.py

Build the VC_ARG_04 'Batch Mixing Tank' HMI replay page (single self-contained HTML)."""
import json, base64
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
from PIL import Image
import io

D = json.load(open(ROOT / 'outputs' / 'sim_data.json'))
log = D['log']; events = D['events']

# estado snapshot fields (spec §10 names) packed column-wise with a string table
FIELDS = ['t', 'stEtapa', 'stSubLimpieza', 'stProducto', 'stMotivoLimpieza', 'pvNivel_L',
          'stIN_P1', 'stIN_P2', 'stIN_P3', 'stIN_CLEAN', 'stOUT_NORMAL', 'stOUT_SCRAP', 'stOUT_RECYCLE', 'stMOT',
          'stAlarma', 'stAlarmaOrigen', 'stAlarmaTexto', 'stLoteParcial', 'stLoteRechazado', 'stTanqueSucio',
          'stParoSolicitado', 'stReintento', 'stListaCompleta', 'stConfirmaVol', 'stMensaje', 'loteIdx', 'loteTotal',
          'reportRow', 'loteId', 'recetaId', 'ultimaReceta', 'recetaAprobada', 'volOrden_L', 'volLote_L', 'recPct',
          'tMezclaRec_s', 'plan_L', 'dos_L', 'volDescargado_L', 'volScrapLote_L', 'volScrapTotal_L', 'tEtapa_s',
          'kpiLotesOK', 'kpiLotesAbort', 'kpiLotesCancel', 'kpiLimpiezas', 'kpiUltimoCiclo_s', 'volNoProducido_L']
STR = ['stAlarmaTexto', 'stMensaje', 'loteId', 'recetaId', 'ultimaReceta']
strings, sidx = [], {}


def s(v):
    if v not in sidx:
        sidx[v] = len(strings); strings.append(v)
    return sidx[v]


# liquid in the tank (product or cleaning liquid), followed sample by sample so a jump in the replay shows it right
liq = 0
for r in log:
    if r['stEtapa'] == 1:
        liq = 0
    elif r['stEtapa'] == 5 and r['stSubLimpieza'] in (2, 3, 4):
        liq = 1
    r['liq'] = liq
FIELDS.append('liq')

rows = []
for r in log:
    row = []
    for f in FIELDS:
        v = r[f]
        row.append(s(v) if f in STR else v)
    rows.append(row)
ev = [[e['t'], e['type'], e['batch'], e['detail']] for e in events]
pack = dict(fields=FIELDS, str=STR, strings=strings, rows=rows, events=ev, date=log[0]['clock'][:10], time0=log[0]['clock'][-8:])
data_js = 'window.SIM=' + json.dumps(pack, separators=(',', ':')) + ';'
im = Image.open(ROOT / 'inputs' / 'MakiPope.png'); im.thumbnail((400, 140))
buf = io.BytesIO(); im.save(buf, format='PNG', optimize=True)
logo = base64.b64encode(buf.getvalue()).decode()

html = open(HERE / 'hmi_template.html', encoding='utf-8').read()
html = html.replace('/*__DATA__*/', data_js).replace('__LOGO__', 'data:image/png;base64,' + logo)
(ROOT / 'hmi').mkdir(exist_ok=True)
open(ROOT / 'hmi' / 'VC_ARG_04_HMI_Batch_Mixing_Tank.html', 'w', encoding='utf-8').write(html)
print('bytes', len(html), 'frames', len(rows), 'strings', len(strings))
