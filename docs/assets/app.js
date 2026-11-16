/* Gráficos interativos do artigo (D3 v7). Os dados vêm de window.DATA (embutido em index.html
   e idêntico a assets/data/results.json), de modo que a página funciona também via file://. */
(function () {
  "use strict";
  const D = window.DATA;
  if (!D || !window.d3) return;
  const C = { moss: "#3f7d3a", gold: "#d9a520", goldL: "#f0cf6a", sheikah: "#2fb6c4", ember: "#c4421a", malice: "#5b3a78",
    forest: "#1f3b2a", forestMid: "#2f5d3a", field: "#9bc26b", ink: "#2a2417", soft: "#5b523a", deep: "#cdb677", slate: "#0f1f24" };
  const SEQ = ["#f6ecd0", "#efd98c", "#e0a929", "#c4421a", "#6e1d0f", "#2a0f20"];
  const loc = d3.formatLocale({ decimal: ",", thousands: ".", grouping: [3], currency: ["R$", ""] });
  const fN = loc.format(",d"), fD1 = loc.format(",.1f"), fD2 = loc.format(",.2f");
  const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  /* ---------- utilidades ---------- */
  const tip = d3.select("body").append("div").attr("class", "tip").attr("role", "tooltip");
  const showTip = (html, ev) => {
    tip.html(html).style("opacity", 1);
    const w = tip.node().offsetWidth, x = Math.min(ev.clientX + 14, window.innerWidth - w - 8);
    tip.style("left", Math.max(6, x) + "px").style("top", ev.clientY + 16 + "px");
  };
  const hideTip = () => tip.style("opacity", 0);
  const bind = (sel, html) => sel.on("mousemove", (ev, d) => showTip(html(d), ev)).on("mouseleave", hideTip)
    .on("touchstart", (ev, d) => { const t = ev.touches[0]; showTip(html(d), t); }, { passive: true });

  function box(el, h, m) {
    const W = Math.max(300, el.clientWidth);
    el.innerHTML = "";
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${h}`).attr("role", "img");
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    return { svg, g, W, w: W - m.l - m.r, h: h - m.t - m.b, narrow: W < 520 };
  }
  function toggles(el, opts, current, onChange) {
    let bar = el.previousElementSibling;
    if (!bar || !bar.classList.contains("toggles")) {
      bar = document.createElement("div"); bar.className = "toggles"; bar.setAttribute("role", "group");
      el.parentNode.insertBefore(bar, el);
    }
    bar.innerHTML = "";
    opts.forEach(([key, label]) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label; b.setAttribute("aria-pressed", key === current);
      b.onclick = () => onChange(key);
      bar.appendChild(b);
    });
  }
  function legend(el, items) {
    let lg = el.nextElementSibling;
    if (!lg || !lg.classList.contains("legend")) { lg = document.createElement("div"); lg.className = "legend"; el.parentNode.insertBefore(lg, el.nextSibling); }
    lg.innerHTML = items.map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join("");
  }
  const axisX = (g, sc, h, fmt, ticks) => g.append("g").attr("class", "axis").attr("transform", `translate(0,${h})`)
    .call(d3.axisBottom(sc).ticks(ticks || 6).tickFormat(fmt || null).tickSizeOuter(0));
  const axisY = (g, sc, fmt, ticks) => g.append("g").attr("class", "axis").call(d3.axisLeft(sc).ticks(ticks || 5).tickFormat(fmt || null).tickSizeOuter(0));
  const gridY = (g, sc, w, ticks) => g.append("g").attr("class", "gridline").call(d3.axisLeft(sc).ticks(ticks || 5).tickSize(-w).tickFormat(""));
  const yLabel = (g, text) => g.append("text").attr("class", "lbl soft").attr("x", -4).attr("y", -10).attr("text-anchor", "start").text(text);

  /* ---------- Fig. 1 — série mensal ---------- */
  function monthly(el) {
    const R = D.rq1, data = R.mensal;
    let st = el._st || (el._st = { metric: "acidentes", mode: "linha" });
    const metrics = { acidentes: ["Acidentes", "acidentes"], mortos: ["Mortos", "mortos"], letalidade: ["Letalidade (mortos por 100 acidentes)", "letalidade"] };
    const opts = Object.entries(metrics).map(([k, v]) => [k, v[0].split(" (")[0]]);
    toggles(el, opts.concat(R.anos.length > 1 ? [["_linha", "Linha do tempo"], ["_anos", "Comparar anos"]] : []),
      st.metric, (k) => { if (k === "_linha") st.mode = "linha"; else if (k === "_anos") st.mode = "anos"; else st.metric = k; monthly(el); });
    if (R.anos.length > 1) { const b = el.previousElementSibling.querySelectorAll("button"); b[3].setAttribute("aria-pressed", st.mode === "linha"); b[4].setAttribute("aria-pressed", st.mode === "anos") }
    const key = metrics[st.metric][1];
    const m = { t: 24, r: 18, b: 34, l: 52 };
    const { g, w, h } = box(el, 330, m);
    yLabel(g, metrics[st.metric][0]);
    const fmt = st.metric === "letalidade" ? fD1 : fN;
    if (st.mode === "linha") {
      const x = d3.scalePoint().domain(data.map((d) => d.ano_mes)).range([0, w]).padding(0.4);
      const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d[key]) * 1.12]).nice().range([h, 0]);
      gridY(g, y, w); axisY(g, y, fmt);
      const step = Math.ceil(data.length / Math.max(2, Math.floor(w / 62)));
      axisX(g, x, h, (v) => { const [yy, mm] = v.split("-"); return MES[+mm - 1] + "/" + yy.slice(2); }).selectAll(".tick").style("display", (d, i) => (i % step ? "none" : null));
      const full = data.filter((d) => !d.parcial);
      g.append("path").datum(data).attr("fill", "none").attr("stroke", C.moss).attr("stroke-width", 3)
        .attr("d", d3.line().x((d) => x(d.ano_mes)).y((d) => y(d[key])).curve(d3.curveMonotoneX));
      g.append("path").datum(data).attr("fill", "rgba(63,125,58,.14)")
        .attr("d", d3.area().x((d) => x(d.ano_mes)).y0(h).y1((d) => y(d[key])).curve(d3.curveMonotoneX));
      const pts = g.selectAll("circle").data(data).join("circle").attr("cx", (d) => x(d.ano_mes)).attr("cy", (d) => y(d[key])).attr("r", 5.5)
        .attr("fill", (d) => (d.parcial ? C.parchment || "#f3e6c4" : C.gold)).attr("stroke", C.forest).attr("stroke-width", 2).style("cursor", "pointer");
      bind(pts, (d) => `<b>${MES[d.mes - 1]}/${d.ano}</b>${d.parcial ? " (mês parcial)" : ""}<br>Acidentes: ${fN(d.acidentes)}<br>Mortos: ${fN(d.mortos)}<br>Feridos: ${fN(d.feridos)}<br>Letalidade: ${fD2(d.letalidade)} por 100`);
      if (data.some((d) => d.parcial)) legend(el, [[C.gold, "mês completo"], ["#f3e6c4", "mês com dados parciais (círculo vazado)"]]);
      else legend(el, [[C.gold, "mês completo"]]);
    } else {
      const x = d3.scaleLinear().domain([1, 12]).range([0, w]);
      const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d[key]) * 1.12]).nice().range([h, 0]);
      gridY(g, y, w); axisY(g, y, fmt); axisX(g, x, h, (v) => MES[v - 1], 12);
      const col = d3.scaleOrdinal().domain(R.anos).range([C.moss, C.gold, C.sheikah, C.ember, C.malice, C.field, C.forestMid]);
      R.anos.forEach((a) => {
        const s = data.filter((d) => d.ano === a);
        g.append("path").datum(s).attr("fill", "none").attr("stroke", col(a)).attr("stroke-width", 2.6).attr("d", d3.line().x((d) => x(d.mes)).y((d) => y(d[key])));
        bind(g.selectAll(`.p${a}`).data(s).join("circle").attr("class", "p" + a).attr("cx", (d) => x(d.mes)).attr("cy", (d) => y(d[key])).attr("r", 4.5).attr("fill", col(a)).attr("stroke", C.forest),
          (d) => `<b>${MES[d.mes - 1]}/${d.ano}</b><br>${metrics[st.metric][0]}: ${fmt(d[key])}`);
      });
      legend(el, R.anos.map((a) => [col(a), String(a)]));
    }
  }

  /* ---------- Fig. 2 — mapa de calor dia × hora ---------- */
  function heat(el) {
    const R = D.rq1;
    let st = el._st || (el._st = { metric: "n" });
    toggles(el, [["n", "Acidentes"], ["pct", "% de acidentes fatais"]], st.metric, (k) => { st.metric = k; heat(el); });
    const narrow = el.clientWidth < 520, m = { t: 8, r: 8, b: 34, l: 40 };
    const cell = Math.max(10, Math.floor((Math.max(300, el.clientWidth) - m.l - m.r) / 24));
    const { g, w } = box(el, cell * 7 + m.t + m.b + 10, m);
    const minN = 20;
    const val = (d) => (st.metric === "n" ? d.n : d.n >= minN ? (100 * d.f) / d.n : null);
    const vmax = d3.max(R.heat, (d) => val(d)) || 1;
    const col = d3.scaleSequential(d3.interpolateRgbBasis(SEQ)).domain(st.metric === "n" ? [0, vmax] : [0, Math.min(vmax, 30)]);
    const x = d3.scaleBand().domain(d3.range(24)).range([0, 24 * cell]).padding(0.08);
    const y = d3.scaleBand().domain(d3.range(7)).range([0, 7 * cell]).padding(0.08);
    const cells = g.selectAll("rect").data(R.heat).join("rect").attr("x", (d) => x(d.h)).attr("y", (d) => y(d.d)).attr("width", x.bandwidth()).attr("height", y.bandwidth())
      .attr("rx", 3).attr("fill", (d) => { const v = val(d); return v === null ? "#e4d09b" : col(v); }).attr("stroke", "rgba(42,36,23,.15)");
    bind(cells, (d) => `<b>${R.dias[d.d]}, ${String(d.h).padStart(2, "0")}h</b><br>Acidentes: ${fN(d.n)}<br>Fatais: ${fN(d.f)} (${d.n ? fD1((100 * d.f) / d.n) : "–"}%)<br>Mortos: ${fN(d.m)}`);
    g.append("g").attr("class", "axis").selectAll("text").data(d3.range(7)).join("text").attr("x", -8).attr("y", (d) => y(d) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").attr("class", "lbl").text((d) => R.dias[d]);
    g.append("g").attr("class", "axis").selectAll("text").data(d3.range(0, 24, narrow ? 3 : 2)).join("text").attr("x", (d) => x(d) + x.bandwidth() / 2).attr("y", 7 * cell + 16).attr("text-anchor", "middle").attr("class", "lbl").text((d) => d + "h");
    legend(el, [[SEQ[1], "menos"], [SEQ[3], "mais"], [SEQ[5], "muito mais"]].concat(st.metric === "pct" ? [["#e4d09b", `n < ${minN} (sem estimativa)`]] : []));
  }

  /* ---------- Fig. 3 — fase do dia / hora ---------- */
  function fase(el) {
    const R = D.rq1;
    let st = el._st || (el._st = { mode: "fase" });
    toggles(el, [["fase", "Fase do dia"], ["hora", "Hora do dia"]], st.mode, (k) => { st.mode = k; fase(el); });
    const m = { t: 26, r: 16, b: 38, l: 48 };
    const { g, w, h } = box(el, 320, m);
    yLabel(g, "% de acidentes que tiveram morte (IC 95%)");
    if (st.mode === "fase") {
      const cols = { Amanhecer: C.gold, "Pleno dia": C.field, Anoitecer: C.ember, "Plena Noite": C.malice };
      const x = d3.scaleBand().domain(R.fase.map((d) => d.fase)).range([0, w]).padding(0.28);
      const y = d3.scaleLinear().domain([0, d3.max(R.fase, (d) => d.hi) * 1.15]).nice().range([h, 0]);
      gridY(g, y, w); axisY(g, y, (v) => v + "%"); axisX(g, x, h);
      const bars = g.selectAll("rect").data(R.fase).join("rect").attr("x", (d) => x(d.fase)).attr("width", x.bandwidth()).attr("y", (d) => y(d.pct_fatais)).attr("height", (d) => h - y(d.pct_fatais))
        .attr("rx", 5).attr("fill", (d) => cols[d.fase] || C.moss).attr("stroke", C.forest);
      g.selectAll(".wh").data(R.fase).join("path").attr("class", "wh").attr("stroke", C.ink).attr("stroke-width", 1.6).attr("fill", "none")
        .attr("d", (d) => { const cx = x(d.fase) + x.bandwidth() / 2; return `M${cx},${y(d.lo)}V${y(d.hi)}M${cx - 7},${y(d.lo)}H${cx + 7}M${cx - 7},${y(d.hi)}H${cx + 7}`; });
      g.selectAll(".vl").data(R.fase).join("text").attr("class", "lbl").attr("text-anchor", "middle").attr("x", (d) => x(d.fase) + x.bandwidth() / 2).attr("y", (d) => y(d.hi) - 6).attr("font-weight", 700).text((d) => fD1(d.pct_fatais) + "%");
      bind(bars, (d) => `<b>${d.fase}</b><br>Acidentes: ${fN(d.n)}<br>Fatais: ${fN(d.f)} (${fD2(d.pct_fatais)}%)<br>IC95%: ${fD1(d.lo)}–${fD1(d.hi)}%<br>Mortos por 100 acidentes: ${fD1(d.letalidade)}`);
      legend(el, []);
    } else {
      const x = d3.scaleLinear().domain([0, 23]).range([0, w]);
      const y = d3.scaleLinear().domain([0, d3.max(R.por_hora, (d) => d.hi) * 1.1]).nice().range([h, 0]);
      gridY(g, y, w); axisY(g, y, (v) => v + "%"); axisX(g, x, h, (v) => v + "h", 12);
      g.append("path").datum(R.por_hora).attr("fill", "rgba(91,58,120,.22)").attr("d", d3.area().x((d) => x(d.h)).y0((d) => y(d.lo)).y1((d) => y(d.hi)).curve(d3.curveMonotoneX));
      g.append("path").datum(R.por_hora).attr("fill", "none").attr("stroke", C.malice).attr("stroke-width", 3).attr("d", d3.line().x((d) => x(d.h)).y((d) => y(d.pct_fatais)).curve(d3.curveMonotoneX));
      bind(g.selectAll("circle").data(R.por_hora).join("circle").attr("cx", (d) => x(d.h)).attr("cy", (d) => y(d.pct_fatais)).attr("r", 4.5).attr("fill", C.gold).attr("stroke", C.forest),
        (d) => `<b>${String(d.h).padStart(2, "0")}h</b><br>Acidentes: ${fN(d.n)}<br>Fatais: ${fN(d.f)} (${fD2(d.pct_fatais)}%)<br>IC95%: ${fD1(d.lo)}–${fD1(d.hi)}%`);
      legend(el, [["rgba(91,58,120,.4)", "intervalo de confiança de 95% (Wilson)"]]);
    }
  }

  /* ---------- barras horizontais genéricas ---------- */
  function hbar(el, rows, o) {
    const narrow = el.clientWidth < 520;
    const m = { t: 8, r: narrow ? 52 : 84, b: 26, l: o.labelW ? (narrow ? Math.min(o.labelW, 128) : o.labelW) : narrow ? 124 : 232 };
    const rowH = o.rowH || (narrow ? 30 : 28);
    const { g, w, h } = box(el, rows.length * rowH + m.t + m.b, m);
    const max = o.max || d3.max(rows, (d) => (d.v + (d.v2 || 0)) || 0) * 1.05 || 1;
    const x = d3.scaleLinear().domain([0, max]).range([0, w]);
    const y = d3.scaleBand().domain(rows.map((d) => d.label)).range([0, h]).padding(0.22);
    g.append("g").attr("class", "gridline").call(d3.axisBottom(x).ticks(5).tickSize(h).tickFormat(""));
    axisX(g, x, h, o.axisFmt || fN, narrow ? 3 : 5);
    g.selectAll(".name").data(rows).join("text").attr("class", "lbl").attr("x", -8).attr("y", (d) => y(d.label) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").text((d) => trunc(d.label, narrow ? 19 : 38));
    const bars = g.selectAll(".b1").data(rows).join("rect").attr("x", 0).attr("y", (d) => y(d.label)).attr("height", y.bandwidth()).attr("width", (d) => Math.max(1, x(d.v))).attr("rx", 4)
      .attr("fill", (d) => (d.color || o.color || C.moss)).attr("stroke", C.forest);
    if (rows.some((d) => d.v2)) g.selectAll(".b2").data(rows).join("rect").attr("x", (d) => x(d.v)).attr("y", (d) => y(d.label)).attr("height", y.bandwidth()).attr("width", (d) => Math.max(0, x(d.v + d.v2) - x(d.v))).attr("rx", 4).attr("fill", o.color2 || C.gold).attr("stroke", C.forest);
    if (o.err) g.selectAll(".er").data(rows).join("path").attr("stroke", C.ink).attr("stroke-width", 1.4).attr("fill", "none")
      .attr("d", (d) => { const cy = y(d.label) + y.bandwidth() / 2; return `M${x(d.lo)},${cy}H${x(d.hi)}M${x(d.lo)},${cy - 5}V${cy + 5}M${x(d.hi)},${cy - 5}V${cy + 5}`; });
    g.selectAll(".vl").data(rows).join("text").attr("class", "lbl").attr("font-weight", 700).attr("x", (d) => x(o.err ? d.hi : (d.v + (d.v2 || 0))) + 6).attr("y", (d) => y(d.label) + y.bandwidth() / 2 + 4).text((d) => o.valFmt(d));
    bind(g.selectAll("rect"), (d) => d.tip);
  }

  /* ---------- Fig. 4 — causas ---------- */
  function causas(el) {
    const rows0 = D.rq2.causas;
    let st = el._st || (el._st = { m: "citada" });
    toggles(el, [["citada", "Citadas (principal + concorrente)"], ["principal", "Só como causa principal"], ["pct", "% de acidentes fatais"]], st.m, (k) => { st.m = k; causas(el); });
    let rows;
    const tipOf = (d) => `<b>${d.causa}</b><br>Citada em ${fN(d.n_citada)} acidentes<br>Como principal: ${fN(d.n_principal)} (${d.pct_como_principal === null ? "–" : fD1(d.pct_como_principal)}% das citações)<br>% fatais (acidentes que a citam): ${d.pct_fatais_citada === null ? "–" : fD1(d.pct_fatais_citada)}%`;
    if (st.m === "citada") {
      rows = [...rows0].sort((a, b) => b.n_citada - a.n_citada).map((d) => ({ label: d.causa, v: d.n_principal, v2: Math.max(0, d.n_citada - d.n_principal), tip: tipOf(d), n: d.n_citada }));
      hbar(el, rows, { valFmt: (d) => fN(d.v + d.v2), color: C.forestMid, color2: C.gold });
      legend(el, [[C.forestMid, "como causa principal"], [C.gold, "como causa concorrente"]]);
    } else if (st.m === "principal") {
      rows = [...rows0].sort((a, b) => b.n_principal - a.n_principal).map((d) => ({ label: d.causa, v: d.n_principal, tip: tipOf(d) }));
      hbar(el, rows, { valFmt: (d) => fN(d.v), color: C.forestMid }); legend(el, []);
    } else {
      rows = [...rows0].filter((d) => d.pct_fatais_citada !== null).sort((a, b) => b.pct_fatais_citada - a.pct_fatais_citada).map((d) => ({ label: d.causa, v: d.pct_fatais_citada, tip: tipOf(d) }));
      hbar(el, rows, { valFmt: (d) => fD1(d.v) + "%", color: C.ember, axisFmt: (v) => v + "%" });
      legend(el, [[C.ember, `% de acidentes com morte entre os que citam a causa (as ${rows.length} causas mais frequentes)`]]);
    }
  }

  /* ---------- Fig. 5 — tipos de acidente ---------- */
  function tipos(el) {
    const rows = D.rq2.tipos.filter((d) => d.n > 0);
    const m = { t: 24, r: 28, b: 44, l: 52 };
    const { g, w, h, narrow } = box(el, 380, m);
    const x = d3.scaleLog().domain([Math.max(1, d3.min(rows, (d) => d.n) * 0.7), d3.max(rows, (d) => d.n) * 1.5]).range([0, w]);
    const y = d3.scaleLinear().domain([0, d3.max(rows, (d) => d.pct_fatais) * 1.15]).nice().range([h, 0]);
    const r = d3.scaleSqrt().domain([0, d3.max(rows, (d) => d.m) || 1]).range([4, narrow ? 18 : 28]);
    gridY(g, y, w); axisY(g, y, (v) => v + "%"); axisX(g, x, h, (v) => fN(v), 6).call((a) => a.selectAll(".tick").style("display", (v) => ([1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000].includes(v) ? null : "none")));
    yLabel(g, "% de acidentes fatais"); g.append("text").attr("class", "lbl soft").attr("x", w).attr("y", h + 36).attr("text-anchor", "end").text("Número de acidentes (escala log) — tamanho do círculo = mortos");
    const dots = g.selectAll("circle").data(rows).join("circle").attr("cx", (d) => x(d.n)).attr("cy", (d) => y(d.pct_fatais)).attr("r", (d) => r(d.m)).attr("fill", C.ember).attr("fill-opacity", 0.55).attr("stroke", C.ember).attr("stroke-width", 1.6);
    bind(dots, (d) => `<b>${d.tipo}</b><br>Acidentes: ${fN(d.n)}<br>Fatais: ${fN(d.f)} (${fD1(d.pct_fatais)}%)<br>Mortos: ${fN(d.m)}`);
    const cand = [...rows].sort((p, q) => q.pct_fatais - p.pct_fatais).slice(0, 4).concat([...rows].sort((p, q) => q.n - p.n).slice(0, narrow ? 3 : 6));
    const placed = [], seen = new Set();
    cand.forEach((d) => {
      if (seen.has(d.tipo)) return; seen.add(d.tipo);
      const t = trunc(d.tipo, narrow ? 18 : 26), wd = t.length * 6.2, anchorEnd = x(d.n) > w - 150;
      const lx = anchorEnd ? x(d.n) - r(d.m) - 4 : x(d.n) + r(d.m) + 4, ly = y(d.pct_fatais) + 4;
      const box = { x0: anchorEnd ? lx - wd : lx, x1: anchorEnd ? lx : lx + wd, y0: ly - 11, y1: ly + 3 };
      if (placed.some((q) => box.x0 < q.x1 && box.x1 > q.x0 && box.y0 < q.y1 && box.y1 > q.y0)) return;
      placed.push(box);
      g.append("text").attr("class", "lbl").attr("x", lx).attr("y", ly).attr("text-anchor", anchorEnd ? "end" : "start").text(t);
    });
    legend(el, []);
  }

  /* ---------- Fig. 6 — perfis ---------- */
  function perfis(el) {
    const P = D.rq2.perfis;
    let st = el._st || (el._st = { m: "letal" });
    toggles(el, [["letal", "Letalidade (% de envolvidos que morreram)"], ["part", "Participação: envolvidos × óbitos"]], st.m, (k) => { st.m = k; perfis(el); });
    const tip = (d) => `<b>${d.perfil}</b><br>Envolvidos (estado informado): ${fN(d.n)}<br>Óbitos: ${fN(d.obitos)} (${fD2(d.pct_obito)}%)<br>IC95%: ${fD2(d.lo)}–${fD2(d.hi)}%<br>Óbitos + feridos graves: ${fD1(d.pct_obito_grave)}%<br>Participação: ${fD1(d.share_envolvidos)}% dos envolvidos, ${fD1(d.share_obitos)}% dos óbitos`;
    if (st.m === "letal") {
      const rows = [...P].sort((a, b) => b.pct_obito - a.pct_obito).map((d) => ({ label: d.perfil, v: d.pct_obito, lo: d.lo, hi: d.hi, tip: tip(d), color: d.perfil === "Pedestres" ? C.ember : d.perfil === "Motocicletas" ? C.gold : d.perfil === "Bicicletas" ? C.gold : C.forestMid }));
      hbar(el, rows, { valFmt: (d) => fD1(d.v) + "%", axisFmt: (v) => v + "%", err: true, labelW: 190 });
      legend(el, [[C.ember, "pedestres"], [C.gold, "usuários vulneráveis motorizados/ciclistas"], [C.forestMid, "ocupantes de veículos"]]);
    } else {
      const narrow = el.clientWidth < 520, m = { t: 6, r: 60, b: 26, l: narrow ? 118 : 190 };
      const rows = [...P].sort((a, b) => b.share_envolvidos - a.share_envolvidos);
      const rowH = narrow ? 44 : 44;
      const { g, w, h } = box(el, rows.length * rowH + m.t + m.b, m);
      const x = d3.scaleLinear().domain([0, d3.max(rows, (d) => Math.max(d.share_envolvidos, d.share_obitos)) * 1.12]).range([0, w]);
      const y = d3.scaleBand().domain(rows.map((d) => d.perfil)).range([0, h]).padding(0.2);
      const y2 = d3.scaleBand().domain(["e", "o"]).range([0, y.bandwidth()]).padding(0.08);
      g.append("g").attr("class", "gridline").call(d3.axisBottom(x).ticks(5).tickSize(h).tickFormat(""));
      axisX(g, x, h, (v) => v + "%", 5);
      g.selectAll(".name").data(rows).join("text").attr("class", "lbl").attr("x", -8).attr("y", (d) => y(d.perfil) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").text((d) => trunc(d.perfil, narrow ? 17 : 30));
      [["e", "share_envolvidos", C.moss], ["o", "share_obitos", C.ember]].forEach(([k, f, c]) => {
        const b = g.selectAll(".s" + k).data(rows).join("rect").attr("x", 0).attr("y", (d) => y(d.perfil) + y2(k)).attr("height", y2.bandwidth()).attr("width", (d) => Math.max(1, x(d[f]))).attr("rx", 3).attr("fill", c).attr("stroke", C.forest);
        bind(b, tip);
        g.selectAll(".t" + k).data(rows).join("text").attr("class", "lbl").attr("x", (d) => x(d[f]) + 5).attr("y", (d) => y(d.perfil) + y2(k) + y2.bandwidth() / 2 + 4).text((d) => fD1(d[f]) + "%");
      });
      legend(el, [[C.moss, "% dos envolvidos"], [C.ember, "% dos óbitos"]]);
    }
  }

  /* ---------- Fig. 7 — pirâmide ---------- */
  function piramide(el) {
    const P = D.rq2.piramide;
    const narrow = el.clientWidth < 520, m = { t: 22, r: 14, b: 30, l: 14 };
    const rowH = 30, { g, w, h } = box(el, P.length * rowH + m.t + m.b, m);
    const max = d3.max(P, (d) => Math.max(d.M, d.F)) * 1.12 || 1, mid = w / 2, lab = narrow ? 44 : 54;
    const x = d3.scaleLinear().domain([0, max]).range([0, mid - lab / 2]);
    const y = d3.scaleBand().domain(P.map((d) => d.faixa)).range([0, h]).padding(0.18);
    g.append("text").attr("class", "lbl").attr("x", mid - lab / 2 - 2).attr("y", -8).attr("text-anchor", "end").attr("font-weight", 700).text("Masculino");
    g.append("text").attr("class", "lbl").attr("x", mid + lab / 2 + 2).attr("y", -8).attr("font-weight", 700).text("Feminino");
    const bm = g.selectAll(".m").data(P).join("rect").attr("x", (d) => mid - lab / 2 - x(d.M)).attr("y", (d) => y(d.faixa)).attr("width", (d) => x(d.M)).attr("height", y.bandwidth()).attr("rx", 3).attr("fill", C.forestMid).attr("stroke", C.forest);
    const bf = g.selectAll(".f").data(P).join("rect").attr("x", mid + lab / 2).attr("y", (d) => y(d.faixa)).attr("width", (d) => x(d.F)).attr("height", y.bandwidth()).attr("rx", 3).attr("fill", C.gold).attr("stroke", C.forest);
    const tp = (d) => `<b>${d.faixa} anos</b><br>Homens: ${fN(d.M)}<br>Mulheres: ${fN(d.F)}`;
    bind(bm, tp); bind(bf, tp);
    g.selectAll(".ag").data(P).join("text").attr("class", "lbl soft").attr("x", mid).attr("y", (d) => y(d.faixa) + y.bandwidth() / 2 + 4).attr("text-anchor", "middle").text((d) => d.faixa);
    g.selectAll(".vm").data(P).join("text").attr("class", "lbl").attr("x", (d) => mid - lab / 2 - x(d.M) - 4).attr("y", (d) => y(d.faixa) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").text((d) => (d.M ? fN(d.M) : ""));
    g.selectAll(".vf").data(P).join("text").attr("class", "lbl").attr("x", (d) => mid + lab / 2 + x(d.F) + 4).attr("y", (d) => y(d.faixa) + y.bandwidth() / 2 + 4).text((d) => (d.F ? fN(d.F) : ""));
    legend(el, []);
  }

  /* ---------- Fig. 8 — UF: acidentes × infrações ---------- */
  function ufScatter(el) {
    const R = D.rq3; if (!R || R.sem_sobreposicao) return;
    let st = el._st || (el._st = { x: "acidentes" });
    toggles(el, [["acidentes", "Eixo X: acidentes"], ["mortos", "Eixo X: mortos"]], st.x, (k) => { st.x = k; ufScatter(el); });
    const rows = R.uf.filter((d) => d[st.x] > 0 && d.infracoes > 0);
    const m = { t: 22, r: 24, b: 46, l: 58 };
    const { g, w, h, narrow } = box(el, 380, m);
    const x = d3.scaleLog().domain(d3.extent(rows, (d) => d[st.x]).map((v, i) => (i ? v * 1.4 : v / 1.5))).range([0, w]);
    const y = d3.scaleLog().domain(d3.extent(rows, (d) => d.infracoes).map((v, i) => (i ? v * 1.4 : v / 1.5))).range([h, 0]);
    gridY(g, y, w, 5); axisY(g, y, (v) => fN(v), 5).selectAll(".tick").style("display", (v) => ([1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000, 300000].includes(v) ? null : "none")); axisX(g, x, h, (v) => fN(v), 5).selectAll(".tick").style("display", (v) => ([1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000].includes(v) ? null : "none"));
    yLabel(g, "Infrações no período comum"); g.append("text").attr("class", "lbl soft").attr("x", w).attr("y", h + 38).attr("text-anchor", "end").text(`${st.x === "acidentes" ? "Acidentes" : "Mortos"} no período comum (escala log)`);
    // reta ajustada (log-log) por mínimos quadrados sobre os pontos exibidos
    const lx = rows.map((d) => Math.log10(d[st.x])), ly = rows.map((d) => Math.log10(d.infracoes)), n = lx.length;
    const mx = d3.mean(lx), my = d3.mean(ly), sl = d3.sum(lx.map((v, i) => (v - mx) * (ly[i] - my))) / d3.sum(lx.map((v) => (v - mx) ** 2)), ic = my - sl * mx;
    const [x0, x1] = x.domain();
    g.append("path").attr("d", `M${x(x0)},${y(10 ** (ic + sl * Math.log10(x0)))}L${x(x1)},${y(10 ** (ic + sl * Math.log10(x1)))}`).attr("stroke", C.ember).attr("stroke-dasharray", "6 4").attr("stroke-width", 2).attr("fill", "none");
    const dots = g.selectAll("circle").data(rows).join("circle").attr("cx", (d) => x(d[st.x])).attr("cy", (d) => y(d.infracoes)).attr("r", 6).attr("fill", C.sheikah).attr("fill-opacity", 0.75).attr("stroke", C.forest).attr("stroke-width", 1.4);
    bind(dots, (d) => `<b>${d.uf}</b><br>Acidentes: ${fN(d.acidentes)}<br>Mortos: ${fN(d.mortos)}<br>Infrações: ${fN(d.infracoes)}<br>Infrações por 100 acidentes: ${d.inf_por_100_acid === null ? "–" : fN(d.inf_por_100_acid)}`);
    g.selectAll(".u").data(rows).join("text").attr("class", "lbl").attr("x", (d) => x(d[st.x]) + 8).attr("y", (d) => y(d.infracoes) + 4).text((d) => d.uf);
    const rho = st.x === "acidentes" ? R.corr_uf_acidentes : R.corr_uf_mortos;
    g.append("text").attr("class", "lbl").attr("x", 8).attr("y", 14).attr("font-weight", 700).text(`ρ de Spearman = ${fD2(rho.rho)} (n = ${rho.n} UFs); inclinação log-log = ${fD2(sl)}`);
    legend(el, [[C.sheikah, "unidade da federação"], [C.ember, "ajuste log-log (tracejado)"]]);
  }

  /* ---------- Fig. 9 — perfil horário ---------- */
  function horario(el) {
    const R = D.rq3; if (!R || R.sem_sobreposicao) return;
    const S = [["acid", "Acidentes", C.moss], ["fatais", "Acidentes fatais", C.ember], ["infr", "Infrações (todas)", C.sheikah], ["vel", "Infrações de velocidade", C.gold]];
    let st = el._st || (el._st = { on: new Set(["acid", "fatais", "infr"]) });
    const m = { t: 24, r: 16, b: 36, l: 48 };
    const { g, w, h } = box(el, 330, m);
    const act = S.filter((s) => st.on.has(s[0]));
    const x = d3.scaleLinear().domain([0, 23]).range([0, w]);
    const y = d3.scaleLinear().domain([0, d3.max(R.horario, (d) => d3.max(act.map((s) => d[s[0]]).concat([1]))) * 1.1]).nice().range([h, 0]);
    gridY(g, y, w); axisY(g, y, (v) => v + "%"); axisX(g, x, h, (v) => v + "h", 12); yLabel(g, "% do total diário");
    act.forEach(([k, name, c]) => {
      g.append("path").datum(R.horario).attr("fill", "none").attr("stroke", c).attr("stroke-width", 3).attr("d", d3.line().x((d) => x(d.h)).y((d) => y(d[k])).curve(d3.curveMonotoneX));
    });
    const ov = g.append("rect").attr("width", w).attr("height", h).attr("fill", "transparent");
    const rule = g.append("line").attr("y1", 0).attr("y2", h).attr("stroke", C.slate).attr("stroke-dasharray", "3 3").style("opacity", 0);
    ov.on("mousemove", (ev) => {
      const hh = Math.max(0, Math.min(23, Math.round(x.invert(d3.pointer(ev)[0])))), d = R.horario[hh];
      rule.attr("x1", x(hh)).attr("x2", x(hh)).style("opacity", 1);
      showTip(`<b>${String(hh).padStart(2, "0")}h</b><br>` + act.map(([k, n]) => `${n}: ${fD1(d[k])}%`).join("<br>"), ev);
    }).on("mouseleave", () => { hideTip(); rule.style("opacity", 0); });
    toggles(el, S.map((s) => [s[0], (st.on.has(s[0]) ? "● " : "○ ") + s[1]]), null, (k) => { st.on.has(k) ? (st.on.size > 1 && st.on.delete(k)) : st.on.add(k); horario(el); });
    legend(el, act.map((s) => [s[2], s[1]]));
  }

  /* ---------- Fig. 10 — grupos de infração ---------- */
  function grupos(el) {
    const R = D.rq3; if (!R) return;
    const rows = R.grupos.map((d) => ({ label: d.grupo, v: d.n, tip: `<b>${d.grupo}</b><br>${fN(d.n)} infrações (${fD1(d.pct)}%)<br>Sem abordagem: ${d.pct_sem_abordagem === null ? "–" : fD1(d.pct_sem_abordagem)}%`, color: d.grupo === "Excesso de velocidade" ? C.gold : C.forestMid, pct: d.pct }));
    hbar(el, rows, { valFmt: (d) => fN(d.v) + " (" + fD1(d.pct) + "%)", color: C.forestMid, labelW: 220 });
    legend(el, []);
  }

  /* ---------- Fig. 11 — excesso de velocidade ---------- */
  function excesso(el) {
    const R = D.rq3; if (!R || !R.excesso) return;
    const H = R.excesso.hist, m = { t: 24, r: 14, b: 62, l: 56 };
    const { g, w, h } = box(el, 300, m);
    const x = d3.scaleBand().domain(H.map((d) => d.x0)).range([0, w]).padding(0.12);
    const y = d3.scaleLinear().domain([0, d3.max(H, (d) => d.n) * 1.1]).nice().range([h, 0]);
    gridY(g, y, w); axisY(g, y, (v) => fN(v));
    axisX(g, x, h, (v) => v + "–" + (v + 4), 10).selectAll("text").attr("transform", "rotate(-35)").style("text-anchor", "end");
    yLabel(g, "Infrações de velocidade");
    const b = g.selectAll("rect").data(H).join("rect").attr("x", (d) => x(d.x0)).attr("y", (d) => y(d.n)).attr("width", x.bandwidth()).attr("height", (d) => h - y(d.n)).attr("rx", 3).attr("fill", (d) => (d.x0 >= 30 ? C.ember : C.gold)).attr("stroke", C.forest);
    bind(b, (d) => `<b>${d.x0}–${d.x0 + 4} km/h acima do limite</b><br>${fN(d.n)} infrações`);
    g.append("text").attr("class", "lbl soft").attr("x", w).attr("y", h + 56).attr("text-anchor", "end").text("Excesso verificado (km/h acima do limite)");
    legend(el, [[C.gold, "até 29 km/h"], [C.ember, "30 km/h ou mais"]]);
  }

  /* ---------- Fig. 12 — sub/sobrerrepresentação ---------- */
  function veiculos(el) {
    const R = D.rq3; if (!R || !R.veiculos) return;
    const rows = R.veiculos.filter((d) => d.veic_acid >= 30 || d.infr >= 300);
    const narrow = el.clientWidth < 520, m = { t: 8, r: narrow ? 52 : 70, b: 40, l: narrow ? 118 : 200 };
    const { g, w, h } = box(el, rows.length * 38 + m.t + m.b, m);
    const maxR = Math.max(2, d3.max(rows, (d) => d.razao) * 1.05);
    const x = d3.scaleSymlog().constant(0.2).domain([0, maxR]).range([0, w]);
    const y = d3.scaleBand().domain(rows.map((d) => d.grupo)).range([0, h]).padding(0.25);
    g.append("g").attr("class", "gridline").call(d3.axisBottom(x).tickValues([0.25, 0.5, 1, 2].filter((v) => v <= maxR)).tickSize(h).tickFormat(""));
    axisX(g, x, h, (v) => fD2(v) + "×", 4).call((s) => s.selectAll("text").attr("class", "lbl"));
    g.append("line").attr("x1", x(1)).attr("x2", x(1)).attr("y1", -4).attr("y2", h).attr("stroke", C.slate).attr("stroke-width", 2);
    g.selectAll(".n").data(rows).join("text").attr("class", "lbl").attr("x", -8).attr("y", (d) => y(d.grupo) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").text((d) => trunc(d.grupo, narrow ? 17 : 32));
    const b = g.selectAll("rect").data(rows).join("rect").attr("y", (d) => y(d.grupo)).attr("height", y.bandwidth()).attr("rx", 4)
      .attr("x", (d) => Math.min(x(1), x(d.razao))).attr("width", (d) => Math.max(2, Math.abs(x(d.razao) - x(1)))).attr("fill", (d) => (d.razao >= 1 ? C.sheikah : C.ember)).attr("stroke", C.forest);
    bind(b, (d) => `<b>${d.grupo}</b><br>${fD1(d.share_infr)}% das infrações<br>${fD1(d.share_acid)}% dos veículos em acidentes<br>Razão: ${fD2(d.razao)}×`);
    g.selectAll(".v").data(rows).join("text").attr("class", "lbl").attr("font-weight", 700).attr("x", (d) => (d.razao >= 1 ? x(d.razao) + 6 : x(1) + 6)).attr("y", (d) => y(d.grupo) + y.bandwidth() / 2 + 4).text((d) => fD2(d.razao) + "×");
    g.append("text").attr("class", "lbl soft").attr("x", w).attr("y", h + 36).attr("text-anchor", "end").text("Razão = % das infrações ÷ % dos veículos em acidentes (1× = proporcional)");
    legend(el, [[C.sheikah, "mais autuado do que presente em acidentes"], [C.ember, "menos autuado do que presente em acidentes"]]);
  }

  /* ---------- registro e ciclo de vida ---------- */
  const REG = { "c-monthly": monthly, "c-heat": heat, "c-fase": fase, "c-causas": causas, "c-tipos": tipos, "c-perfis": perfis, "c-piramide": piramide,
    "c-uf": ufScatter, "c-horario": horario, "c-grupos": grupos, "c-excesso": excesso, "c-veiculos": veiculos };
  function renderAll() { Object.entries(REG).forEach(([id, fn]) => { const el = document.getElementById(id); if (el) { try { fn(el); } catch (e) { console.error(id, e); el.textContent = "Não foi possível desenhar este gráfico."; } } }); }
  let lastW = {}, timer;
  function onResize() { clearTimeout(timer); timer = setTimeout(() => { Object.keys(REG).forEach((id) => { const el = document.getElementById(id); if (el && lastW[id] !== el.clientWidth) { lastW[id] = el.clientWidth; try { REG[id](el); } catch (e) { /* noop */ } } }); }, 180); }
  document.addEventListener("DOMContentLoaded", () => {
    renderAll(); Object.keys(REG).forEach((id) => { const el = document.getElementById(id); if (el) lastW[id] = el.clientWidth; });
    window.addEventListener("resize", onResize);
    const links = [...document.querySelectorAll(".nav a.l")];
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id)); }), { rootMargin: "-40% 0px -55% 0px" });
    document.querySelectorAll("main section[id]").forEach((s) => io.observe(s));
  });
})();
