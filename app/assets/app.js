const $ = (id) => document.getElementById(id);
const post = (path, body) => fetch(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
}).then((r) => r.json());

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
    ].map((t) => Object.assign(document.createElement("li"), { textContent: t })));
    $("record").textContent = JSON.stringify(r, null, 2);
  }
}

$("settings").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await post("/api/settings", {
    normal_alarm: f.normal_alarm.value, hard_limit: f.hard_limit.value, enabled: f.enabled.checked ? "1" : "0",
  });
  $("saved").textContent = r.ok ? "Saved." : r.error;
});
$("dismiss").onclick = () => post("/api/dismiss");
$("chime").onclick = () => post("/api/chime");
$("demo-start").onclick = () => post("/api/demo/start", { minutes: Number($("demo-min").value) });
$("demo-stop").onclick = () => post("/api/demo/stop");

refresh();
setInterval(refresh, 3000);
