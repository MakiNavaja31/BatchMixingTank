(() => {
  // theme variables for series and states (style only)
  const C = dash.colors;
  for (const el of document.querySelectorAll('.vc')) {
    C.forEach((c, i) => el.style.setProperty('--c' + i, c));
    el.style.setProperty('--st-0', 'var(--cds-chart-muted)');
    [1, 2, 3, 4, 5].forEach((s, i) => el.style.setProperty('--st-' + s, C[i]));
    el.style.setProperty('--st-9', 'var(--cds-chart-status-critical)');
  }
  const ST_NAMES = { 0: 'Stopped', 1: 'Filling_OP', 2: 'Mixing_OP', 3: 'Empty_OP', 4: 'Waiting', 5: 'Cleaning_OP', 9: 'Alarm Stop' };
  const ST_NUM = Object.fromEntries(Object.entries(ST_NAMES).map(([k, v]) => [v, k]));
  const OVERFLOW_L = 101;
  const F = { int: d3.format(','), l1: d3.format(',.1f'), l2: d3.format(',.2f'), pct: d3.format('.1%'), h1: d3.format(',.2f'),
    hm: d3.utcFormat('%H:%M'), hms: d3.utcFormat('%H:%M:%S'), day: d3.utcFormat('%d.%m.%Y %H:%M') };
  const pLog = (s) => { const [d, t] = String(s).split(' '); const [dd, mm, yy] = d.split('.'); return new Date(`${yy}-${mm}-${dd}T${t}Z`); };
  const pIso = (s) => (s ? new Date(String(s) + 'Z') : null);

  // a status other than ok: the dash (or a failure line) comes back
  const notOk = (el, ...ids) => {
    const st = ids.map((id) => dash.data(id).status);
    if (st.every((s) => s === 'ok')) return false;
    el.replaceChildren();
    if (st.includes('error')) {
      const line = document.createElement('div');
      line.style.cssText = 'display:flex;align-items:center;justify-content:center;gap:.5rem;min-height:inherit;color:var(--color-fg-muted);font-size:var(--cds-font-size-caption)';
      const dot = document.createElement('i');
      dot.style.cssText = 'width:.375rem;height:.375rem;border-radius:50%;background:var(--color-bad)';
      line.append(dot, 'Failed to load');
      el.append(line);
    } else el.textContent = '—';
    return true;
  };
  const tipFor = (el) => { const t = document.createElement('div'); t.className = 'tip'; t.hidden = true; el.append(t); return t; };
  const showTip = (el, tip, x, y, lines) => {
    tip.replaceChildren();
    lines.forEach(([k, v, color], i) => {
      const row = document.createElement('div');
      if (i === 0) { row.className = 'k'; row.textContent = k; }
      else {
        if (color) { const s = document.createElement('i'); s.className = 'sw'; s.style.cssText = `background:${color};width:.6rem;height:.6rem;margin-right:.35rem`; row.append(s); }
        row.append(`${k}: `); const b = document.createElement('b'); b.textContent = v; row.append(b);
      }
      tip.append(row);
    });
    tip.hidden = false;
    const w = el.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.max(0, Math.min(w - tw, x + 12)) + 'px';
    tip.style.top = Math.max(0, y - th - 8) + 'px';
  };
  const textW = (svg, s) => { const t = svg.append('text').attr('class', 'lbl').text(s); const w = t.node().getComputedTextLength(); t.remove(); return w; };
  const cleanAxis = (g) => g.attr('font-size', null).attr('font-family', null);

  // ---------------- headline numbers
  const kp = () => dash.data('kpis');
  const tiles = [['k-completed', 'completed', F.int], ['k-aborted', 'aborted', F.int], ['k-skipped', 'skipped', F.int],
    ['k-produced', 'produced_L', F.l1], ['k-notprod', 'not_produced_L', F.l1], ['k-scrap', 'scrap_L', F.l2],
    ['k-clean', 'cleanings', F.int], ['k-alarms', 'alarms', F.int], ['k-good', 'good_share', F.pct],
    ['k-completed2', 'completed', F.int], ['k-aborted2', 'aborted', F.int], ['k-skipped2', 'skipped', F.int], ['k-good2', 'good_share', F.pct]];
  for (const [name, field, fmt] of tiles) {
    dash.draw(name, (el) => { const d = kp(); el.textContent = d.status === 'ok' ? fmt(d.data[0][field]) : '—'; });
  }
  dash.draw('run-start', (el) => { const d = dash.data('log'); el.textContent = d.status === 'ok' ? F.day(pLog(d.data[0].clock)) : '—'; });
  dash.draw('run-end', (el) => { const d = dash.data('log'); el.textContent = d.status === 'ok' ? F.hm(pLog(d.data[d.data.length - 1].clock)) : '—'; });

  // ---------------- tank level with state strip and alarm markers
  dash.draw('level', (el) => {
    if (notOk(el, 'log', 'events')) return;
    el.replaceChildren();
    const rows = dash.data('log').data.map((r) => ({ d: pLog(r.clock), lvl: Number(r.pvNivel_L), st: Number(r.stEtapa), al: Number(r.stAlarma), id: r.loteId }));
    const alarms = dash.data('events').data.filter((e) => e.type === 'ALARM').map((e) => ({ d: pIso(e.clock), code: Number(e.code), detail: e.detail, batch: e.batch }));
    const W = el.clientWidth || 800, H = 360;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const m = { t: 30, r: 12, b: 46, l: textW(svg, '100 L') + 12 };
    const stripH = 14;
    const x = d3.scaleUtc(d3.extent(rows, (r) => r.d), [m.l, W - m.r]);
    const y = d3.scaleLinear([0, 105], [H - m.b - stripH - 8, m.t]);
    const nt = Math.max(2, Math.floor((W - m.l) / 80));
    svg.append('g').attr('transform', `translate(0,${H - m.b})`).call((g) => cleanAxis(g.call(d3.axisBottom(x).ticks(nt).tickFormat(F.hm))));
    svg.append('g').attr('transform', `translate(${m.l},0)`).call((g) => cleanAxis(g.call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat((v) => v + ' L'))).call((g) => g.select('.domain').remove()));
    // overflow limit
    svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(OVERFLOW_L)).attr('y2', y(OVERFLOW_L))
      .style('stroke', 'var(--cds-chart-status-critical)').attr('stroke-dasharray', '4 3');
    svg.append('text').attr('class', 'lbl').attr('x', W - m.r).attr('y', y(OVERFLOW_L) - 4).attr('text-anchor', 'end').text(`Overflow limit ${OVERFLOW_L} L`);
    // level line
    svg.append('path').datum(rows).attr('fill', 'none').style('stroke', C[0]).attr('stroke-width', 1.5).attr('stroke-linejoin', 'round')
      .attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.lvl)));
    // state strip
    const segs = [];
    rows.forEach((r, i) => { if (!segs.length || segs[segs.length - 1].st !== r.st) segs.push({ st: r.st, a: r.d, b: r.d }); segs[segs.length - 1].b = rows[i + 1] ? rows[i + 1].d : r.d; });
    const sy = H - m.b - stripH;
    svg.append('g').selectAll('rect').data(segs).join('rect').attr('x', (s) => x(s.a)).attr('y', sy)
      .attr('width', (s) => Math.max(0.5, x(s.b) - x(s.a))).attr('height', stripH).style('fill', (s) => `var(--st-${s.st})`);
    // alarm markers, stacked when close
    let lastX = -99, stack = 0;
    const mk = svg.append('g');
    alarms.forEach((a) => {
      const ax = x(a.d); stack = ax - lastX < 16 ? stack + 1 : 0; lastX = ax;
      const cy = 10 + stack * 15;
      mk.append('line').attr('x1', ax).attr('x2', ax).attr('y1', cy + 6).attr('y2', sy).style('stroke', 'var(--cds-chart-status-critical)').attr('stroke-width', 1).attr('opacity', 0.6);
      mk.append('circle').attr('cx', ax).attr('cy', cy).attr('r', 7).style('fill', 'var(--color-panel)').style('stroke', 'var(--cds-chart-status-critical)');
      mk.append('text').attr('x', ax).attr('y', cy + 3.5).attr('text-anchor', 'middle').attr('font-size', 10).style('fill', 'var(--color-fg)').text(a.code);
    });
    // hover
    const tip = tipFor(el);
    const dot = svg.append('circle').attr('r', 4).style('fill', C[0]).attr('opacity', 0);
    const bis = d3.bisector((r) => r.d).center;
    svg.append('rect').attr('x', m.l).attr('y', 0).attr('width', W - m.l - m.r).attr('height', H - m.b).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [px, py] = d3.pointer(ev);
        const r = rows[bis(rows, x.invert(px))];
        dot.attr('cx', x(r.d)).attr('cy', y(r.lvl)).attr('opacity', 1);
        const near = alarms.filter((a) => Math.abs(x(a.d) - px) < 6);
        const lines = [[F.hms(r.d)], ['Level', F.l2(r.lvl) + ' L', C[0]], ['State', ST_NAMES[r.st]], ['Batch', r.id || '–']];
        near.forEach((a) => lines.push([`Alarm ${a.code}`, a.batch || '–']));
        showTip(el, tip, (px / W) * el.clientWidth, (py / H) * el.clientHeight, lines);
      })
      .on('mouseleave', () => { tip.hidden = true; dot.attr('opacity', 0); });
  });

  // ---------------- horizontal bar helper
  const hbars = (el, rows, label, value, fmtv, color, tipLines) => {
    el.replaceChildren();
    const W = el.clientWidth || 400, bh = 22, gap = 8, H = rows.length * (bh + gap) + 24;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const lw = d3.max(rows, (r) => textW(svg, label(r))) + 10;
    const vw = d3.max(rows, (r) => textW(svg, fmtv(value(r)))) + 8;
    const x = d3.scaleLinear([0, d3.max(rows, value) || 1], [lw, W - vw]);
    const tip = tipFor(el);
    const g = svg.selectAll('g.b').data(rows).join('g').attr('transform', (r, i) => `translate(0,${i * (bh + gap) + 4})`);
    g.append('text').attr('class', 'lbl').attr('x', lw - 8).attr('y', bh / 2 + 4).attr('text-anchor', 'end').text(label);
    g.append('rect').attr('x', lw).attr('height', bh).attr('rx', 3).attr('width', (r) => Math.max(0, x(value(r)) - lw)).style('fill', color);
    g.append('text').attr('class', 'lbl').attr('x', (r) => x(value(r)) + 4).attr('y', bh / 2 + 4).text((r) => fmtv(value(r)));
    g.append('rect').attr('x', 0).attr('width', W).attr('height', bh).attr('fill', 'transparent')
      .on('mousemove', (ev, r) => { const [px, py] = d3.pointer(ev, el); showTip(el, tip, px, py, tipLines(r)); })
      .on('mouseleave', () => { tip.hidden = true; });
  };
  dash.draw('activity', (el) => {
    if (notOk(el, 'activity')) return;
    hbars(el, dash.data('activity').data, (r) => r.state, (r) => r.seconds / 3600, (v) => F.h1(v) + ' h',
      (r) => `var(--st-${ST_NUM[r.state]})`, (r) => [[r.state], ['Hours', F.h1(r.seconds / 3600)], ['Seconds', F.l1(r.seconds)]]);
  });
  dash.draw('alarmbars', (el) => {
    if (notOk(el, 'alarm_counts')) return;
    hbars(el, dash.data('alarm_counts').data, (r) => `${r.code} – ${r.name}`, (r) => r.count, F.int,
      () => 'var(--cds-chart-status-critical)', (r) => [[`Alarm ${r.code}`], [r.name, F.int(r.count)]]);
  });
  dash.draw('ontime', (el) => {
    if (notOk(el, 'ontime')) return;
    hbars(el, dash.data('ontime').data, (r) => r.output, (r) => r.seconds / 3600, (v) => F.h1(v) + ' h',
      () => C[0], (r) => [[r.output], ['On-time', F.h1(r.seconds / 3600) + ' h'], ['Seconds', F.int(r.seconds)]]);
  });

  // ---------------- cumulative produced and scrap
  dash.draw('cumul', (el) => {
    if (notOk(el, 'cumul', 'log')) return;
    el.replaceChildren();
    const log = dash.data('log').data;
    const t0 = pLog(log[0].clock), t1 = pLog(log[log.length - 1].clock);
    const prod = [{ d: t0, v: 0 }, ...dash.data('cumul').data.map((r) => ({ d: pIso(r.OUT), v: Number(r.produced_cum) }))];
    prod.push({ d: t1, v: prod[prod.length - 1].v });
    const scrap = log.map((r) => ({ d: pLog(r.clock), v: Number(r.volScrapTotal_L) }));
    const W = el.clientWidth || 500, H = 300;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const ymax = d3.max(prod, (p) => p.v);
    const endw = Math.max(textW(svg, F.int(ymax) + ' L'), textW(svg, F.l1(scrap[scrap.length - 1].v) + ' L'));
    const m = { t: 12, r: endw + 10, b: 26, l: textW(svg, F.int(ymax)) + 12 };
    const x = d3.scaleUtc([t0, t1], [m.l, W - m.r]);
    const y = d3.scaleLinear([0, ymax * 1.05], [H - m.b, m.t]);
    svg.append('g').attr('transform', `translate(0,${H - m.b})`).call((g) => cleanAxis(g.call(d3.axisBottom(x).ticks(Math.max(2, Math.floor((W - m.l) / 80))).tickFormat(F.hm))));
    svg.append('g').attr('transform', `translate(${m.l},0)`).call((g) => cleanAxis(g.call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat(F.int))).call((g) => g.select('.domain').remove()));
    const ln = d3.line().curve(d3.curveStepAfter).x((p) => x(p.d)).y((p) => y(p.v));
    [[prod, C[0]], [scrap, C[1]]].forEach(([s, c]) => svg.append('path').datum(s).attr('fill', 'none').style('stroke', c)
      .attr('stroke-width', 2).attr('stroke-linejoin', 'round').attr('stroke-linecap', 'round').attr('d', ln));
    const lp = prod[prod.length - 1], ls = scrap[scrap.length - 1];
    let yp = y(lp.v) + 4, ys = y(ls.v) + 4; if (Math.abs(yp - ys) < 14) ys = yp + 14;
    svg.append('text').attr('class', 'lbl').attr('x', W - m.r + 6).attr('y', yp).text(F.int(lp.v) + ' L');
    svg.append('text').attr('class', 'lbl').attr('x', W - m.r + 6).attr('y', ys).text(F.l1(ls.v) + ' L');
    const tip = tipFor(el);
    const bp = d3.bisector((p) => p.d).right, bs = d3.bisector((p) => p.d).center;
    svg.append('rect').attr('x', m.l).attr('y', 0).attr('width', W - m.l - m.r).attr('height', H - m.b).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [px, py] = d3.pointer(ev); const d = x.invert(px);
        const p = prod[Math.max(0, bp(prod, d) - 1)], s = scrap[bs(scrap, d)];
        showTip(el, tip, (px / W) * el.clientWidth, (py / H) * el.clientHeight,
          [[F.hms(d)], ['Litres produced', F.l1(p.v), C[0]], ['Scrap (L)', F.l2(s.v), C[1]]]);
      })
      .on('mouseleave', () => { tip.hidden = true; });
  });

  // ---------------- litres per batch
  dash.draw('perbatch', (el) => {
    if (notOk(el, 'report')) return;
    el.replaceChildren();
    const rows = dash.data('report').data;
    const W = el.clientWidth || 800, H = 300;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const m = { t: 18, r: 8, b: 26, l: textW(svg, '100 L') + 12 };
    const x = d3.scaleBand(rows.map((r) => r.n), [m.l, W - m.r]).padding(0.2);
    const y = d3.scaleLinear([0, 105], [H - m.b, m.t]);
    const every = Math.ceil(28 / x.step());
    svg.append('g').attr('transform', `translate(0,${H - m.b})`).call((g) => cleanAxis(g.call(d3.axisBottom(x).tickValues(rows.map((r) => r.n).filter((n, i) => i % every === 0)))));
    svg.append('g').attr('transform', `translate(${m.l},0)`).call((g) => cleanAxis(g.call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat((v) => v + ' L'))).call((g) => g.select('.domain').remove()));
    const bw = x.bandwidth();
    const g = svg.selectAll('g.b').data(rows).join('g');
    g.append('rect').attr('x', (r) => x(r.n)).attr('width', bw).attr('rx', 2)
      .attr('y', (r) => y(r.status === 'COMPLETED' ? Number(r.vol_prod) : r.status === 'SKIPPED' ? 0 : Number(r.vol_order)))
      .attr('height', (r) => (r.status === 'SKIPPED' ? 0 : y(0) - y(r.status === 'COMPLETED' ? Number(r.vol_prod) : Number(r.vol_order))))
      .style('fill', (r) => (r.status === 'COMPLETED' ? C[0] : 'var(--color-bad)')).attr('opacity', (r) => (r.status === 'COMPLETED' ? 1 : 0.55));
    g.append('rect').attr('x', (r) => x(r.n)).attr('width', bw).attr('y', (r) => y(Number(r.vol_order))).attr('height', (r) => y(0) - y(Number(r.vol_order)))
      .attr('fill', 'none').style('stroke', (r) => (r.status === 'SKIPPED' ? 'var(--color-warn)' : 'var(--color-fg-muted)'))
      .attr('stroke-width', 1.2).attr('stroke-dasharray', (r) => (r.status === 'SKIPPED' ? '3 2' : null));
    if (bw >= 7) {
      g.append('text').attr('x', (r) => x(r.n) + bw / 2).attr('y', (r) => y(Number(r.vol_order)) - 4).attr('text-anchor', 'middle')
        .attr('font-size', 9).style('fill', 'var(--color-fg-muted)').text((r) => (r.status === 'COMPLETED' ? 'C' : r.status === 'SKIPPED' ? 'S' : 'A'));
    }
    const tip = tipFor(el);
    g.append('rect').attr('x', (r) => x(r.n) - (x.step() - bw) / 2).attr('width', x.step()).attr('y', 0).attr('height', H - m.b).attr('fill', 'transparent')
      .on('mousemove', (ev, r) => {
        const [px, py] = d3.pointer(ev, el);
        showTip(el, tip, px, py, [[`#${r.n} · ${r.batch} · ${r.recipe}`], ['Status', r.status], ['Ordered', F.int(r.vol_order) + ' L'],
          ['Produced', r.vol_prod == null ? '–' : F.l1(r.vol_prod) + ' L', C[0]], ...(r.alarms ? [['Alarms', r.alarms]] : [])]);
      })
      .on('mouseleave', () => { tip.hidden = true; });
  });

  // ---------------- tables
  const td = (tr, v, cls) => { const c = document.createElement('td'); c.textContent = v == null ? '' : v; if (cls) c.className = cls; tr.append(c); };
  dash.draw('alarmlog-body', (tb) => {
    const d = dash.data('alarmlog');
    tb.replaceChildren();
    if (d.status !== 'ok') return;
    for (const r of d.data) {
      const tr = document.createElement('tr');
      tr.dataset.key = `${encodeURIComponent(r.t)},${encodeURIComponent(r.code)}`;
      td(tr, F.hms(pIso(r.clock))); td(tr, r.code, 'num'); td(tr, r.batch); td(tr, r.state); td(tr, r.detail);
      tb.append(tr);
    }
  });
  dash.draw('report-body', (tb) => {
    const d = dash.data('report');
    tb.replaceChildren();
    if (d.status !== 'ok') return;
    for (const r of d.data) {
      const tr = document.createElement('tr');
      td(tr, r.n, 'num'); td(tr, r.batch); td(tr, r.recipe); td(tr, r.vol_order, 'num');
      td(tr, r.vol_prod == null ? '' : F.l1(r.vol_prod), 'num');
      td(tr, r.IN ? F.hms(pIso(r.IN)) : ''); td(tr, r.OUT ? F.hms(pIso(r.OUT)) : '');
      td(tr, r.process_s == null ? '' : F.l1(r.process_s), 'num'); td(tr, r.clean_s == null ? '' : F.l1(r.clean_s), 'num');
      td(tr, r.status, r.status === 'ABORTED (ALARM)' ? 'st-ABORTED' : r.status === 'SKIPPED' ? 'st-SKIPPED' : '');
      td(tr, r.alarms); td(tr, r.remarks);
      tb.append(tr);
    }
  });
})();
