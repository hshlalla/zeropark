"""Built-in admin dashboard for the control plane (no separate frontend build).

Served at `/`. Auth = the same X-Admin-Token used by the API, entered once and
kept in localStorage. Intentionally dependency-free vanilla HTML/JS so the
internal tool never adds build complexity to the monorepo.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<title>Zeropark Control Plane</title>
<style>
  :root { --accent:#4F46E5; --bg:#F8FAFC; --card:#FFFFFF; --text:#0F172A; --muted:#64748B; }
  * { box-sizing:border-box; }
  body { font-family:system-ui,-apple-system,sans-serif; background:var(--bg); color:var(--text); margin:0; padding:32px; }
  h1 { font-size:20px; margin:0 0 4px; } .sub { color:var(--muted); font-size:13px; margin-bottom:24px; }
  .card { background:var(--card); border:1px solid #E2E8F0; border-radius:12px; padding:20px; margin-bottom:20px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th,td { text-align:left; padding:10px 12px; border-bottom:1px solid #F1F5F9; }
  th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; }
  .dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; }
  .on { background:#10B981; } .off { background:#CBD5E1; }
  .badge { font-size:11px; padding:2px 8px; border-radius:999px; background:#EEF2FF; color:var(--accent); }
  .badge.inactive { background:#FEF2F2; color:#DC2626; }
  button { cursor:pointer; border:1px solid #E2E8F0; background:#fff; border-radius:8px; padding:6px 12px; font-size:13px; }
  button.primary { background:var(--accent); color:#fff; border:none; }
  input,textarea { width:100%; padding:8px 10px; border:1px solid #E2E8F0; border-radius:8px; font-size:14px; margin-bottom:10px; }
  .row { display:flex; gap:10px; } .row > * { flex:1; }
  .key { font-family:monospace; font-size:11px; color:var(--muted); word-break:break-all; }
  #token-bar { display:flex; gap:10px; align-items:center; margin-bottom:20px; }
  #token-bar input { margin:0; max-width:320px; }
</style>
</head>
<body>
<h1>Zeropark Control Plane</h1>
<div class="sub">고객사 배포본 플릿 관리 — 상태, 라이선스, 프로파일</div>

<div id="token-bar">
  <input id="token" type="password" placeholder="Admin Token"/>
  <button class="primary" onclick="saveToken()">연결</button>
  <span id="conn-status" class="sub"></span>
</div>

<div class="card">
  <h3 style="margin-top:0">새 배포 등록</h3>
  <div class="row">
    <input id="new-name" placeholder="배포 이름 (예: Samsung DS Agent)"/>
    <input id="new-client" placeholder="고객사 (예: Samsung)"/>
    <input id="new-url" placeholder="Base URL (예: https://agent.samsung.example.com)"/>
  </div>
  <textarea id="new-profile" rows="3" placeholder='프로파일 JSON (예: {"branding":{"product_name":"S-Agent"},"features":{"browse":false}})'></textarea>
  <button class="primary" onclick="createDeployment()">등록 + 라이선스 발급</button>
</div>

<div class="card">
  <h3 style="margin-top:0">배포 목록</h3>
  <table>
    <thead><tr><th>상태</th><th>이름</th><th>고객사</th><th>버전</th><th>Capabilities</th><th>마지막 하트비트</th><th>라이선스</th><th></th></tr></thead>
    <tbody id="rows"><tr><td colspan="8" class="sub">토큰을 입력하고 연결하세요.</td></tr></tbody>
  </table>
</div>

<script>
const $ = (id) => document.getElementById(id);
function token() { return localStorage.getItem("zp_cp_token") || ""; }
function saveToken() { localStorage.setItem("zp_cp_token", $("token").value); refresh(); }
async function api(path, opts = {}) {
  opts.headers = Object.assign({"X-Admin-Token": token(), "Content-Type": "application/json"}, opts.headers || {});
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json()).detail || res.status);
  return res.json();
}
async function refresh() {
  try {
    const data = await api("/api/v1/deployments");
    $("conn-status").textContent = "연결됨 — " + data.deployments.length + "개 배포";
    $("rows").innerHTML = data.deployments.map(d => `
      <tr>
        <td><span class="dot ${d.online ? "on" : "off"}"></span>${d.online ? "online" : "offline"}
            ${d.is_active ? "" : '<span class="badge inactive">license off</span>'}</td>
        <td><b>${d.name}</b><div class="key">${d.id}</div></td>
        <td>${d.client_name}</td>
        <td>${d.version || "-"}</td>
        <td>${(d.capabilities || []).join(", ") || "-"}</td>
        <td>${d.last_heartbeat ? new Date(d.last_heartbeat + "Z").toLocaleString() : "-"}</td>
        <td class="key">${d.license_key}</td>
        <td>
          <button onclick="toggleActive('${d.id}', ${!d.is_active})">${d.is_active ? "라이선스 중지" : "라이선스 활성"}</button>
          <button onclick="removeDeployment('${d.id}')">삭제</button>
        </td>
      </tr>`).join("") || '<tr><td colspan="8" class="sub">등록된 배포가 없습니다.</td></tr>';
  } catch (e) {
    $("conn-status").textContent = "오류: " + e.message;
  }
}
async function createDeployment() {
  let profile = {};
  const raw = $("new-profile").value.trim();
  if (raw) { try { profile = JSON.parse(raw); } catch { alert("프로파일 JSON이 올바르지 않습니다."); return; } }
  await api("/api/v1/deployments", {method: "POST", body: JSON.stringify({
    name: $("new-name").value, client_name: $("new-client").value,
    base_url: $("new-url").value || null, profile: profile,
  })});
  $("new-name").value = $("new-client").value = $("new-url").value = $("new-profile").value = "";
  refresh();
}
async function toggleActive(id, active) {
  await api("/api/v1/deployments/" + id, {method: "PATCH", body: JSON.stringify({is_active: active})});
  refresh();
}
async function removeDeployment(id) {
  if (!confirm("정말 삭제할까요? 라이선스가 즉시 무효화됩니다.")) return;
  await api("/api/v1/deployments/" + id, {method: "DELETE"});
  refresh();
}
if (token()) { $("token").value = token(); refresh(); }
setInterval(() => { if (token()) refresh(); }, 15000);
</script>
</body>
</html>"""
