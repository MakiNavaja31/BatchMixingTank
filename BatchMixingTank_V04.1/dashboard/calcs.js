dash.calc('kpis', {
  inputs: ['report', 'events', 'log'],
  title: 'Run totals',
  description: 'Records by status, litres, scrap, cleanings finished, alarms raised and the share of time making good product.',
  fn: (report, events, log) => {
    const of = (s) => report.filter((r) => r.status === s);
    const sum = (rows, f) => rows.reduce((a, r) => a + (Number(r[f]) || 0), 0);
    const last = log[log.length - 1];
    const elapsed = Number(last.t_s);
    return [{
      records: report.length,
      completed: of('COMPLETED').length,
      aborted: of('ABORTED (ALARM)').length,
      skipped: of('SKIPPED').length,
      produced_L: Math.round(sum(report, 'vol_prod') * 100) / 100,
      not_produced_L: sum(of('SKIPPED'), 'vol_order'),
      scrap_L: Number(last.volScrapTotal_L),
      cleanings: events.filter((e) => e.type === 'STATE' && /^T1[34]:/.test(e.detail)).length,
      alarms: events.filter((e) => e.type === 'ALARM').length,
      good_share: sum(of('COMPLETED'), 'process_s') / elapsed,
    }];
  },
});

dash.calc('alarm_counts', {
  inputs: ['events'],
  title: 'Alarms by code',
  description: 'Alarms raised per code 1 to 6, counted from the event log.',
  fn: (events) => [
    [1, 'Overflow'], [2, 'Emergency Stop'], [3, 'Fill deviation'],
    [4, 'Step timeout'], [5, 'Partial batch'], [6, 'Batch not allowed'],
  ].map(([code, name]) => ({
    code, name, count: events.filter((e) => e.type === 'ALARM' && Number(e.code) === code).length,
  })),
});

dash.calc('activity', {
  inputs: ['events', 'log'],
  title: 'Time by state',
  description: 'Seconds in each state, from the state changes in the event log up to the end of the log.',
  fn: (events, log) => {
    const names = ['Stopped', 'Filling_OP', 'Mixing_OP', 'Empty_OP', 'Waiting', 'Cleaning_OP', 'Alarm Stop'];
    const secs = Object.fromEntries(names.map((n) => [n, 0]));
    let state = 'Stopped', t0 = 0;
    for (const e of events) {
      const m = e.type === 'STATE' && /-> (.+?)(?: \(|$)/.exec(e.detail);
      if (!m) continue;
      secs[state] += Number(e.t) - t0;
      state = m[1]; t0 = Number(e.t);
    }
    secs[state] += Number(log[log.length - 1].t_s) - t0;
    return names.map((n) => ({ state: n, seconds: Math.round(secs[n] * 10) / 10 }));
  },
});

dash.calc('ontime', {
  inputs: ['log'],
  title: 'Output on-time',
  description: 'Seconds each valve and the motor were on, as 5 s samples times 5.',
  fn: (log) => ['IN_P1', 'IN_P2', 'IN_P3', 'IN_CLEAN', 'OUT_NORMAL', 'OUT_SCRAP', 'OUT_RECYCLE', 'MOT']
    .map((o) => ({ output: o, seconds: log.filter((r) => Number(r[o]) === 1).length * 5 })),
});

dash.calc('cumul', {
  inputs: ['report'],
  title: 'Cumulative litres produced',
  description: 'Running total of Vol. produced at the OUT time of each completed batch.',
  fn: (report) => {
    let acc = 0;
    return report.filter((r) => r.status === 'COMPLETED')
      .sort((a, b) => (a.OUT < b.OUT ? -1 : 1))
      .map((r) => ({ n: r.n, OUT: r.OUT, produced_cum: (acc = Math.round((acc + Number(r.vol_prod)) * 100) / 100) }));
  },
});

dash.calc('alarmlog', {
  inputs: ['events'],
  title: 'Alarm log',
  description: 'The ALARM entries of the event log.',
  fn: (events) => events.filter((e) => e.type === 'ALARM')
    .map((e) => ({ t: e.t, clock: e.clock, code: e.code, batch: e.batch, state: e.state, detail: e.detail })),
});
