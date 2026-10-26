const $ = (id) => document.getElementById(id);
const post = (path, body) => fetch(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
}).then((r) => r.json());
const el = (tag, props) => Object.assign(document.createElement(tag), props);

// Line chart of up to 30 points; zeros mean "no reading" except where lo is 0.
function chart(canvas, values, color, lo, hi) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  const pts = values.map((v, i) => [i, v]).filter(([, v]) => v > 0 || lo === 0);
  if (!pts.length) return;
  const min = Math.min(lo, ...pts.map((p) => p[1])), max = Math.max(hi, ...pts.map((p) => p[1]));
  g.strokeStyle = color; g.lineWidth = 2; g.beginPath();
  pts.forEach(([i, v], k) => {
    const x = (i / 29) * (w - 8) + 4;
    const y = h - 6 - ((v - min) / (max - min || 1)) * (h - 12);
    if (k) g.lineTo(x, y); else g.moveTo(x, y);
  });
  g.stroke();
}

let settingsLoaded = false;

async function refresh() {
  let d;
  try { d = await (await fetch("/api/live")).json(); } catch { $("presence").textContent = "No connection to the clock."; return; }
  const rows = d.rows, last = rows[rows.length - 1];
  if (!last) $("presence").textContent = "Waiting for radar…";
  else if (!last.lines) $("presence").textContent = "No radar lines in the last 10 s. Check the radar cable.";
  else $("presence").textContent = last.presence >= 50 ? "Someone is in bed." : "Nobody detected.";
  const show = (v) => (v > 0 ? v.toFixed(1) : "–");
  $("breath").textContent = last ? show(last.breath) : "–";
  $("heart").textContent = last ? show(last.heart) : "–";
  $("move").textContent = last ? String(last.move_max) : "–";
  chart($("c-breath"), rows.map((r) => r.breath), "#7fb3d5", 10, 20);
  chart($("c-heart"), rows.map((r) => r.heart), "#d98e8e", 55, 80);
  chart($("c-move"), rows.map((r) => r.move_max), "#d9a24e", 0, 100);

  const n = d.night;
  $("night").textContent = !n ? "No data yet."
    : `${n.score} / 100 ${n.confident ? "" : "(not sure: too little data)"} · ${n.minutes} min observed, `
      + `${n.restless_min} restless, ${n.irregular_min} irregular breathing, ${n.long_awakenings} long awakenings, `
      + `${n.coverage_pct}% coverage`;

  $("next").textContent = d.settings.enabled === "1" ? d.next_alarm : "off";
  if (!settingsLoaded) {
    const f = $("settings");
    f.normal_alarm.value = d.settings.normal_alarm;
    f.hard_limit.value = d.settings.hard_limit;
    f.enabled.checked = d.settings.enabled === "1";
    f.rain.checked = d.settings.rain === "1";
    f.card_url.value = d.settings.card_url;
    settingsLoaded = true;
  }

  $("demo-tag").hidden = !d.demo.active;
  $("demo-left").textContent = d.demo.active ? `${Math.ceil(d.demo.left_s / 60)} min left` : "";
  $("wake").textContent = d.wake === "idle" ? "" : d.wake;

  const dec = d.decision;
  if (dec) {
    const r = dec.record;
    $("dec-tag").hidden = !dec.day.startsWith("demo");
    $("message").textContent = dec.message || "Writing the message…";
    $("rules").replaceChildren(...[
      `Alarm ${r.final_alarm} (usual ${r.normal_alarm}, must be up by ${r.hard_limit}): +${r.extra_min} min`,
      ...r.rules,
    ].map((t) => el("li", { textContent: t })));
    $("record").textContent = JSON.stringify(r, null, 2);
  }

  const st = d.step;
  $("step").textContent = !st ? "No step yet: it is picked with the alarm decision."
    : `${st.done ? "✓ " : "→ "}${st.step} (${st.minutes} min)${st.demo ? " [demo]" : ""}`;
  $("step-why").textContent = !st ? "" : st.info.method === "rule"
    ? `Size ${st.size}: rule (${st.info.rows} mornings logged; the predictor starts at 20).`
    : `Size ${st.size}: ${st.info.method}, P(done) ${JSON.stringify(st.info.p_done)}.`;

  $("items").replaceChildren(...d.items.map((i) => {
    const li = el("li", { textContent: `${i.when ? i.when + " · " : ""}${i.title}`
      + `${i.kind === "job" && !i.steps ? " (splitting…)" : ""}${i.done ? " ✓" : ""} ` });
    const del = el("button", { textContent: "×", title: "Delete" });
    del.onclick = () => post("/api/items/delete", { id: i.id });
    li.append(del);
    if (i.steps) {
      const ul = el("ul");
      for (const k of ["tiny", "small", "normal"]) ul.append(el("li", { textContent: `${k}: ${i.steps[k]}`, className: "small" }));
      li.append(ul);
    }
    return li;
  }));

  const rn = d.rain;
  $("rain").textContent = !rn ? `Off. ${d.rain_labels} labelled minutes.`
    : `${rn.detected ? "Rain" : "No rain"} in the last hour (${rn.rain_minutes}/${rn.minutes} min, ${rn.method}`
      + `${rn.confident ? "" : ", not sure"}). ${d.rain_labels} labelled minutes.`;
  $("card").textContent = d.card
    ? `Last update ${new Date(d.card.ts * 1000).toLocaleTimeString()}: ${d.card.ok ? "ok" : d.card.detail}` : "Not sent yet.";
}

$("settings").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await post("/api/settings", {
    normal_alarm: f.normal_alarm.value, hard_limit: f.hard_limit.value, enabled: f.enabled.checked ? "1" : "0",
    rain: f.rain.checked ? "1" : "0", card_url: f.card_url.value,
  });
  $("saved").textContent = r.ok ? "Saved." : r.error;
});
$("dismiss").onclick = () => post("/api/dismiss");
$("chime").onclick = () => post("/api/chime");
$("demo-start").onclick = () => post("/api/demo/start", { minutes: Number($("demo-min").value) });
$("demo-stop").onclick = () => post("/api/demo/stop");
$("step-done").onclick = () => post("/api/step/done");
$("item").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await post("/api/items", { title: f.title.value, due: f.due.value, kind: f.kind.value });
  $("item-msg").textContent = r.ok ? "Added." : r.error;
  if (r.ok) f.reset();
});
const label = async (rain) => {
  const r = await post("/api/rain/label", { rain });
  $("rain-msg").textContent = r.ok ? `Labelled ${r.labelled} min.` : r.error;
};
$("rain-yes").onclick = () => label(true);
$("rain-no").onclick = () => label(false);
$("card-push").onclick = () => post("/api/card/push");

refresh();
setInterval(refresh, 3000);
