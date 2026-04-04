/* ═══════════════════════════════════════════════════════
   CodeWarriors — Frontend SPA
   Fixed bugs: json import in chatbot, CORS, flow logic,
   chat ordering, null checks, onboarding redirect logic.
   Redesigned: modern cards, toast system, better UX flow.
═══════════════════════════════════════════════════════ */

const $ = (sel, root = document) => root.querySelector(sel);

/* ── Public routes (no auth needed) ── */
const PUBLIC_PATHS = new Set(["/home", "/login", "/register"]);

/* ── Routes allowed before entry quiz ── */
const PRE_ENTRY_ALLOWED = new Set(["/profile", "/subjects", "/topics", "/topic", "/quiz", "/entry-quiz"]);

/* ── Correct onboarding flow ── */
const ONBOARDING_FLOW = [
  "/profile",
  "/subjects",
  "/entry-quiz",
  "/dashboard",
];

let cachedMe = null;

/* ── Storage helpers ── */
const storage = {
  get apiBase() { return localStorage.getItem("apiBase") || "http://localhost:8000"; },
  set apiBase(v) { localStorage.setItem("apiBase", v); },
  get token() { return localStorage.getItem("cwToken") || ""; },
  set token(v) { v ? localStorage.setItem("cwToken", v) : localStorage.removeItem("cwToken"); },
  get sessionId() { return localStorage.getItem("cwChatSession") || ""; },
  set sessionId(v) { v ? localStorage.setItem("cwChatSession", v) : localStorage.removeItem("cwChatSession"); },
};

/* ── Chart refs ── */
let pieChartRef = null, barChartRef = null;
function destroyCharts() {
  try { pieChartRef?.destroy(); barChartRef?.destroy(); } catch (_) {}
  pieChartRef = null; barChartRef = null;
}

/* ── Format helpers ── */
function fmtPct(v) {
  if (v == null) return "—";
  const n = Number(v);
  return Number.isFinite(n) ? `${n}%` : String(v);
}
function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
}
function formatApiDetail(d) {
  if (!d || d === "") return "Request failed";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map(x => typeof x === "string" ? x : (x?.msg || x?.message || JSON.stringify(x))).join("; ");
  if (typeof d === "object") return d.msg || d.message || JSON.stringify(d);
  return String(d);
}
function apiErrMsg(e) {
  if (e instanceof TypeError && String(e.message).includes("fetch"))
    return `Cannot reach API at ${storage.apiBase}. Make sure the backend is running (uvicorn on port 8000) and the URL in ⚙ API Config is correct.`;
  return e.message || String(e);
}
function resIcon(type) {
  return { video:"▶", pdf:"📄", article:"📖", tutorial:"🎓", course:"🏫", practice:"💻" }[type] || "🔗";
}

/* ── Toast notifications ── */
function toast(msg, type = "info", duration = 3500) {
  const c = document.getElementById("toastContainer");
  if (!c) return;
  const t = document.createElement("div");
  t.className = `toast toast-${type === "ok" ? "ok" : type === "err" ? "err" : ""}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transform = "translateX(16px)"; t.style.transition = "all 0.3s"; setTimeout(() => t.remove(), 300); }, duration);
}

/* ── Session clear ── */
function clearSession(reason) {
  storage.token = "";
  storage.sessionId = "";
  cachedMe = null;
  const who = document.getElementById("whoami");
  const lb = document.getElementById("logoutBtn");
  if (who) who.textContent = "";
  if (lb) lb.hidden = true;
  try { updateOnboardingStrip(); } catch (_) {}
}

/* ── Central API helper ── */
async function api(path, { method = "GET", query, body, auth = true, _retry = 0 } = {}) {
  const base = storage.apiBase.replace(/\/+$/, "");
  const qs = query ? `?${new URLSearchParams(query)}` : "";
  const url = `${base}${path}${qs}`;
  const headers = { "Content-Type": "application/json" };
  if (auth && storage.token) headers.Authorization = `Bearer ${storage.token}`;
  let res;
  try {
    res = await fetch(url, { method, headers, body: body != null ? JSON.stringify(body) : undefined });
  } catch (e) {
    if (e instanceof TypeError && _retry < 1) {
      await new Promise(r => setTimeout(r, 400));
      return api(path, { method, query, body, auth, _retry: 1 });
    }
    throw e;
  }
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!res.ok) {
    const msg = formatApiDetail(data?.detail ?? data?.message ?? res.statusText);
    if (auth && storage.token && (res.status === 401 || res.status === 403)) {
      clearSession(`${res.status}`);
      const { path: p } = parseRoute();
      if (!PUBLIC_PATHS.has(p)) location.hash = "#/login";
    }
    const err = new Error(msg);
    err.status = res.status; err.data = data;
    throw err;
  }
  return data;
}

/* ── Routing ── */
function parseRoute() {
  const raw = (location.hash || "").replace(/^#/, "");
  const [pathPart, qPart] = raw.split("?");
  const p = pathPart?.startsWith("/") ? pathPart : pathPart ? `/${pathPart}` : "";
  return {
    path: p || (storage.token ? "/dashboard" : "/home"),
    query: Object.fromEntries(new URLSearchParams(qPart || "")),
  };
}
function requireAuth() {
  if (!storage.token) { location.hash = "#/login"; return false; }
  return true;
}

/* ── Render helper ── */
function render(html) {
  const app = document.getElementById("app");
  if (!app) return;
  app.innerHTML = `<div class="view-root">${html}</div>`;
  // stagger children
  const vr = app.querySelector(".view-root");
  requestAnimationFrame(() => {
    [...(vr?.children || [])].forEach((ch, i) => ch.style.setProperty("--stagger", `${0.05 + i * 0.07}s`));
    vr?.classList.add("view-root--in");
  });
}

function stagger(root, sel = "> *") {
  if (!root) return;
  const nodes = sel === "> *" ? [...root.children] : [...root.querySelectorAll(sel)];
  nodes.forEach((el, i) => {
    el.style.setProperty("--stagger", `${i * 0.055}s`);
    el.classList.remove("stagger-el");
    void el.offsetWidth;
    el.classList.add("stagger-el");
  });
}

/* ── Chart theme ── */
let chartThemed = false;
function ensureChartTheme() {
  if (chartThemed || typeof Chart === "undefined") return;
  chartThemed = true;
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.borderColor = "rgba(255,255,255,0.07)";
  Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
}

/* ── Nav build ── */
function buildTopNav(path) {
  const nav = document.getElementById("topNav");
  const logo = document.getElementById("logoLink");
  if (logo) logo.setAttribute("href", storage.token ? "#/dashboard" : "#/home");
  if (!nav) return;
  const links = storage.token
    ? [["Dashboard","#/dashboard"],["Performance","#/performance"],["Path","#/learning-path"],["Subjects","#/subjects"],["Topics","#/topics"],["Recs","#/recommendations"],["Games","#/games"],["Chat","#/chat"],["Profile","#/profile"]]
    : [["Home","#/home"],["Login","#/login"],["Register","#/register"]];
  nav.innerHTML = links.map(([label, h]) => {
    const p = h.slice(1);
    const active = path === p ? " active" : "";
    return `<a href="${h}" class="nav-link${active}">${label}</a>`;
  }).join("");
}

/* ── Onboarding strip ── */
function updateOnboardingStrip() {
  const el = document.getElementById("onboardingStrip");
  if (!el) return;
  if (!storage.token || !cachedMe) { el.hidden = true; return; }
  const p = cachedMe.profile || {};
  const subjects = cachedMe.selected_subjects || [];
  const profDone = !!p.onboarding_complete;
  const subjDone = subjects.length > 0;
  const entryDone = !!cachedMe.entry_quiz_completed;
  if (profDone && subjDone && entryDone) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `
    <span class="onb-label">Setup:</span>
    <div class="onb-steps">
      <a href="#/profile" class="onb-step ${profDone ? "done" : "active"}">${profDone ? "✓" : "1"} Profile</a>
      <span class="onb-arrow">›</span>
      <a href="#/subjects" class="onb-step ${subjDone ? "done" : profDone ? "active" : ""}">${subjDone ? "✓" : "2"} Subjects</a>
      <span class="onb-arrow">›</span>
      <a href="#/entry-quiz" class="onb-step ${entryDone ? "done" : subjDone ? "active" : ""}">${entryDone ? "✓" : "3"} Assessment</a>
    </div>`;
}

async function syncMe() {
  try { cachedMe = await api("/me"); } catch { cachedMe = null; }
  updateOnboardingStrip();
}

/* ── Onboarding redirect ── */
function getOnboardingRedirect(path) {
  if (!storage.token || !cachedMe) return null;
  const p = cachedMe.profile || {};
  const subjects = cachedMe.selected_subjects || [];

  // Must complete profile first
  if (!p.onboarding_complete && path !== "/profile") return "/profile";

  // Must select subjects
  if (p.onboarding_complete && subjects.length === 0 && path !== "/profile" && path !== "/subjects") return "/subjects";

  // Must complete entry quiz
  if (p.onboarding_complete && subjects.length > 0 && !cachedMe.entry_quiz_completed) {
    if (!PRE_ENTRY_ALLOWED.has(path)) return "/entry-quiz";
  }

  // Already fully set up, don't re-show public pages
  if (PUBLIC_PATHS.has(path) && p.onboarding_complete && subjects.length > 0 && cachedMe.entry_quiz_completed)
    return "/dashboard";

  return null;
}

/* ── refreshMe ── */
async function refreshMe() {
  const who = document.getElementById("whoami");
  const lb = document.getElementById("logoutBtn");
  if (!storage.token) {
    cachedMe = null;
    if (who) who.textContent = "";
    if (lb) lb.hidden = true;
    return;
  }
  if (lb) lb.hidden = false;
  try {
    cachedMe = await api("/me");
    if (who) who.textContent = cachedMe.full_name || cachedMe.username || "";
  } catch {
    cachedMe = null;
    storage.token = "";
    if (who) who.textContent = "";
    if (lb) lb.hidden = true;
  }
}

function installGlobalHandlers() {
  const apiIn = document.getElementById("apiBase");
  const saveBtn = document.getElementById("saveApiBaseBtn");
  const hint = document.getElementById("apiHint");
  if (apiIn) apiIn.value = storage.apiBase;
  if (saveBtn && apiIn) {
    saveBtn.onclick = () => {
      storage.apiBase = apiIn.value.trim() || "http://localhost:8000";
      if (hint) { hint.textContent = "Saved ✓"; setTimeout(() => hint.textContent = "", 2000); }
    };
  }
  const lb = document.getElementById("logoutBtn");
  if (lb) {
    lb.onclick = () => {
      clearSession("logout");
      location.hash = "#/home";
      buildTopNav("/home");
    };
  }
}

async function postLoginRedirect() {
  const me = await api("/me");
  cachedMe = me;
  if (!me.profile?.onboarding_complete) { location.hash = "#/profile"; return; }
  const subjects = me.selected_subjects || [];
  if (subjects.length === 0) { location.hash = "#/subjects"; return; }
  if (!me.entry_quiz_completed) { location.hash = "#/entry-quiz"; return; }
  location.hash = "#/dashboard";
}

/* ══════════════════════════════════════════════════════
   PAGES
══════════════════════════════════════════════════════ */

/* ── Home ── */
function pageHome() {
  destroyCharts();
  render(`
    <div class="landing-hero">
      <div class="hero-eyebrow">🚀 AI-Powered CS Learning</div>
      <h1 class="hero-title">Master Computer Science <span class="grad">the smart way</span></h1>
      <p class="hero-sub">Personalized quizzes, AI-generated learning paths, embedded games, weak-area analytics, and a Gemini-powered tutor — all in one place.</p>
      <div class="hero-actions">
        <a class="btn btn-primary btn-lg" href="#/register">Get started free</a>
        <a class="btn btn-outline btn-lg" href="#/login">Sign in</a>
      </div>
    </div>

    <div class="card mt-lg">
      <div class="card-header">
        <div>
          <div class="card-title">Everything you need</div>
          <div class="card-subtitle">One platform, complete CS curriculum</div>
        </div>
      </div>
      <div class="feature-grid">
        <div class="feature-card">
          <div class="feature-icon">📊</div>
          <div class="feature-title">Smart Analytics</div>
          <div class="feature-body">Visual mastery tracking, weak-area detection, and progress charts to show exactly where you stand.</div>
        </div>
        <div class="feature-card">
          <div class="feature-icon">🤖</div>
          <div class="feature-title">AI Tutor (Gemini)</div>
          <div class="feature-body">Ask doubts, get concept explanations, or request resources. Auto-detects your intent.</div>
        </div>
        <div class="feature-card">
          <div class="feature-icon">🗺</div>
          <div class="feature-title">Learning Paths</div>
          <div class="feature-body">AI-generated, day-by-day study plans tailored to your goals and current skill level.</div>
        </div>
        <div class="feature-card">
          <div class="feature-icon">🎮</div>
          <div class="feature-title">Embedded Games</div>
          <div class="feature-body">Matching, ordering, and true/false games per topic — no external portals, play right here.</div>
        </div>
      </div>
      <div class="mt-lg" style="background:rgba(99,102,241,0.07);border:1px solid rgba(99,102,241,0.2);border-radius:10px;padding:1rem 1.25rem;">
        <span style="font-weight:600;color:var(--indigo-2);">Typical flow: </span>
        <span style="color:var(--text-2);font-size:0.88rem;">Register → Complete Profile → Choose Subjects → Entry Assessment → Unlock full dashboard with Performance, Learning Path, Topics, Games, Chat, and more.</span>
      </div>
    </div>`);
}

/* ── Login ── */
async function pageLogin() {
  destroyCharts();
  render(`
    <div class="auth-container">
      <div class="auth-logo-row">
        <a class="logo" href="#/home" style="justify-content:center;">
          <svg class="logo-icon" viewBox="0 0 28 28" fill="none"><rect width="28" height="28" rx="8" fill="url(#lg2)"/><path d="M8 10l4 4-4 4M14 18h6" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><defs><linearGradient id="lg2" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse"><stop stop-color="#6366f1"/><stop offset="1" stop-color="#06b6d4"/></linearGradient></defs></svg>
          <span class="logo-text">Code<span class="logo-accent">Warriors</span></span>
        </a>
      </div>
      <div class="card auth-card">
        <div class="card-title">Welcome back</div>
        <div class="card-subtitle">Sign in to continue your journey</div>
        <div class="auth-divider"></div>
        <p id="st" class="status-muted" style="min-height:1.3em"></p>
        <div class="field">
          <label class="field-label">Email address</label>
          <input id="email" type="email" class="input" autocomplete="username" placeholder="you@example.com" />
        </div>
        <div class="field">
          <label class="field-label">Password</label>
          <input id="password" type="password" class="input" autocomplete="current-password" placeholder="••••••••" />
        </div>
        <button type="button" class="btn btn-primary w-full mt-sm" id="loginBtn">Sign in</button>
        <div class="auth-footer">
          Don't have an account? <a href="#/register">Create one</a>
        </div>
      </div>
    </div>`);

  const doLogin = async () => {
    const email = $("#email")?.value.trim();
    const password = $("#password")?.value;
    if (!email || !password) { setStatus("st", "Please fill in all fields.", "err"); return; }
    const btn = document.getElementById("loginBtn");
    btn.disabled = true; btn.textContent = "Signing in…";
    setStatus("st", "", "muted");
    try {
      const data = await api("/login", { method: "POST", auth: false, body: { email, password } });
      storage.token = data.token;
      await refreshMe();
      updateOnboardingStrip();
      await postLoginRedirect();
    } catch (e) {
      setStatus("st", apiErrMsg(e), "err");
      btn.disabled = false; btn.textContent = "Sign in";
    }
  };

  document.getElementById("loginBtn").onclick = doLogin;
  document.getElementById("password").addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); });
  document.getElementById("email").addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("password")?.focus(); });
}

/* ── Register ── */
async function pageRegister() {
  destroyCharts();
  render(`
    <div class="auth-container">
      <div class="auth-logo-row">
        <a class="logo" href="#/home" style="justify-content:center;">
          <svg class="logo-icon" viewBox="0 0 28 28" fill="none"><rect width="28" height="28" rx="8" fill="url(#lg3)"/><path d="M8 10l4 4-4 4M14 18h6" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><defs><linearGradient id="lg3" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse"><stop stop-color="#6366f1"/><stop offset="1" stop-color="#06b6d4"/></linearGradient></defs></svg>
          <span class="logo-text">Code<span class="logo-accent">Warriors</span></span>
        </a>
      </div>
      <div class="card auth-card">
        <div class="card-title">Create your account</div>
        <div class="card-subtitle">Join thousands of CS learners</div>
        <div class="auth-divider"></div>
        <p id="st" class="status-muted" style="min-height:1.3em"></p>
        <div class="form-row">
          <div class="field">
            <label class="field-label">Full name</label>
            <input id="full_name" type="text" class="input" placeholder="Jane Doe" />
          </div>
          <div class="field">
            <label class="field-label">Username</label>
            <input id="username" type="text" class="input" placeholder="janedoe" />
          </div>
        </div>
        <div class="field">
          <label class="field-label">Email address</label>
          <input id="email" type="email" class="input" placeholder="you@example.com" />
        </div>
        <div class="field">
          <label class="field-label">Password</label>
          <input id="password" type="password" class="input" placeholder="Min. 8 characters" />
        </div>
        <button type="button" class="btn btn-primary w-full" id="regBtn">Create account</button>
        <div class="auth-footer">
          Already have an account? <a href="#/login">Sign in</a>
        </div>
      </div>
    </div>`);

  document.getElementById("regBtn").onclick = async () => {
    const full_name = document.getElementById("full_name")?.value.trim();
    const username = document.getElementById("username")?.value.trim();
    const email = document.getElementById("email")?.value.trim();
    const password = document.getElementById("password")?.value;
    if (!full_name || !username || !email || !password) { setStatus("st", "Please fill in all fields.", "err"); return; }
    const btn = document.getElementById("regBtn");
    btn.disabled = true; btn.textContent = "Creating account…";
    try {
      const data = await api("/register", { method: "POST", auth: false, body: { full_name, username, email, password } });
      storage.token = data.token;
      await refreshMe();
      updateOnboardingStrip();
      location.hash = "#/profile";
    } catch (e) {
      setStatus("st", apiErrMsg(e), "err");
      btn.disabled = false; btn.textContent = "Create account";
    }
  };
}

function setStatus(id, msg, type = "muted") {
  const el = typeof id === "string" ? document.getElementById(id) : id;
  if (!el) return;
  el.className = `status-${type}`;
  el.textContent = msg;
}

/* ── Profile ── */
async function pageProfile() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`<div class="card"><p class="muted pulse">Loading profile…</p></div>`);
  let me;
  try { me = await api("/me"); } catch (e) { render(`<div class="card"><p class="status-err">${escHtml(apiErrMsg(e))}</p></div>`); return; }
  const p = me.profile || {};
  render(`
    <div class="page-header">
      <h1 class="page-title">Your <span class="accent">Profile</span></h1>
      <p class="page-subtitle">We use this to personalize your learning path and AI recommendations.</p>
    </div>
    <div class="card" style="max-width:640px">
      <p id="st" class="status-muted" style="min-height:1.3em"></p>
      <div class="form-row">
        <div class="field">
          <label class="field-label">Full name</label>
          <input id="full_name" class="input" value="${escHtml(me.full_name || "")}" />
        </div>
        <div class="field">
          <label class="field-label">Age (optional)</label>
          <input id="age" type="number" class="input" value="${p.age ?? ""}" placeholder="e.g. 20" />
        </div>
      </div>
      <div class="form-row">
        <div class="field">
          <label class="field-label">Year of college</label>
          <input id="year_of_college" type="number" class="input" min="1" max="8" value="${p.year_of_college ?? ""}" placeholder="1–8" />
        </div>
        <div class="field">
          <label class="field-label">College name</label>
          <input id="college_name" class="input" value="${escHtml(p.college_name || "")}" placeholder="Optional" />
        </div>
      </div>
      <div class="field">
        <label class="field-label">Learning goals</label>
        <textarea id="learning_goals" class="textarea" placeholder="e.g. Master DSA for interviews, build full-stack projects…">${escHtml(p.learning_goals || "")}</textarea>
      </div>
      <button type="button" class="btn btn-primary" id="saveBtn">Save & continue →</button>
    </div>`);

  document.getElementById("saveBtn").onclick = async () => {
    const btn = document.getElementById("saveBtn");
    btn.disabled = true; btn.textContent = "Saving…";
    try {
      await api("/profile", { method: "PUT", body: {
        full_name: document.getElementById("full_name")?.value.trim(),
        age: document.getElementById("age")?.value ? Number(document.getElementById("age").value) : null,
        year_of_college: document.getElementById("year_of_college")?.value ? Number(document.getElementById("year_of_college").value) : null,
        college_name: document.getElementById("college_name")?.value.trim() || null,
        learning_goals: document.getElementById("learning_goals")?.value.trim() || null,
        onboarding_complete: true,
      }});
      await syncMe();
      toast("Profile saved!", "ok");
      location.hash = "#/subjects";
    } catch (e) {
      setStatus("st", apiErrMsg(e), "err");
      btn.disabled = false; btn.textContent = "Save & continue →";
    }
  };
}

/* ── Entry Quiz ── */
let entryPage = 0;
const ENTRY_PAGE_SIZE = 15;

async function pageEntryQuiz() {
  if (!requireAuth()) return;
  destroyCharts();

  const st = await api("/entry-quiz/status").catch(() => null);
  if (!st) { render(`<div class="card"><p class="status-err">Could not load quiz status.</p></div>`); return; }
  if (st.entry_quiz_completed) {
    render(`
      <div class="page-header"><h1 class="page-title">Assessment <span class="accent">Complete</span></h1></div>
      <div class="card" style="max-width:480px;text-align:center">
        <div style="font-size:3rem;margin-bottom:1rem">🎉</div>
        <p style="font-size:1.1rem;font-weight:600;margin-bottom:0.5rem">You're all set!</p>
        <p class="muted mb-md">Skill level detected: <strong style="color:var(--cyan)">${escHtml(st.skill_level || "—")}</strong></p>
        <a class="btn btn-primary" href="#/dashboard">Go to Dashboard →</a>
      </div>`);
    return;
  }
  if (!st.selected_subjects?.length) {
    render(`<div class="card" style="max-width:480px"><p class="status-err mb-md">Please select subjects first.</p><a class="btn btn-primary" href="#/subjects">Choose Subjects →</a></div>`);
    return;
  }

  let data;
  try {
    try { data = await api("/entry-quiz/current"); }
    catch (e) {
      if (e.status === 404) data = await api("/entry-quiz/start", { method: "POST" });
      else throw e;
    }
  } catch (e) { render(`<div class="card"><p class="status-err">${escHtml(e.message)}</p></div>`); return; }

  if (!data.resumed) window.__entryAnswers = {};
  const qs = data.questions || [];
  const totalPages = Math.max(1, Math.ceil(qs.length / ENTRY_PAGE_SIZE));

  let me2;
  try { me2 = await api("/me"); } catch { me2 = { id: "anon" }; }
  const epKey = `cw_entry_page_${me2.id}`;
  const t0Key = `cw_entry_t0_${me2.id}`;
  entryPage = Math.min(Math.max(0, Number(sessionStorage.getItem(epKey) || 0)), totalPages - 1);
  if (!sessionStorage.getItem(t0Key)) sessionStorage.setItem(t0Key, String(Date.now()));

  function drawEntry() {
    const slice = qs.slice(entryPage * ENTRY_PAGE_SIZE, (entryPage + 1) * ENTRY_PAGE_SIZE);
    const answers = window.__entryAnswers || {};
    const answered = Object.keys(answers).length;

    render(`
      <div class="page-header">
        <h1 class="page-title">Entry <span class="accent">Assessment</span></h1>
        <p class="page-subtitle">${qs.length} questions · Page ${entryPage + 1} of ${totalPages} · ${answered} answered so far</p>
      </div>
      <div class="quiz-progress-row">
        <div class="progress-bar" style="flex:1"><div class="progress-fill" style="width:${Math.round((answered/qs.length)*100)}%"></div></div>
        <span class="dimmed">${answered}/${qs.length}</span>
      </div>
      <div id="ql"></div>
      <div class="flex gap-md mt-md" style="flex-wrap:wrap">
        ${entryPage > 0 ? `<button type="button" class="btn btn-outline" id="prevBtn">← Previous</button>` : ""}
        ${entryPage < totalPages - 1
          ? `<button type="button" class="btn btn-primary" id="nextBtn">Next →</button>`
          : `<button type="button" class="btn btn-primary" id="submitBtn">Submit Assessment →</button>`}
        <p id="st" class="status-muted" style="align-self:center"></p>
      </div>`);

    const ql = document.getElementById("ql");
    if (!ql) return;
    ql.innerHTML = slice.map((q, i) => {
      const idx = entryPage * ENTRY_PAGE_SIZE + i;
      const userAns = answers[q.id];
      return `<div class="q-card stagger-el" style="--stagger:${i*0.04}s">
        <div class="q-card-head"><span class="dimmed">${idx + 1}</span></div>
        <div class="q-card-body mb-sm"><strong>${escHtml(q.question)}</strong> <span class="dimmed">(${escHtml(q.topic_name || "")})</span></div>
        <div class="radio-group">
          ${q.options.map((o, j) => `
            <label class="radio-opt">
              <input type="radio" name="eq_${escHtml(q.id)}" value="${j}" ${userAns === j ? "checked" : ""}>
              ${escHtml(o)}
            </label>`).join("")}
        </div>
      </div>`;
    }).join("");

    // Attach change handlers
    slice.forEach(q => {
      document.querySelectorAll(`input[name="eq_${CSS.escape(q.id)}"]`).forEach(inp => {
        inp.onchange = () => { answers[q.id] = Number(inp.value); };
      });
    });

    document.getElementById("prevBtn")?.addEventListener("click", () => {
      entryPage = Math.max(0, entryPage - 1);
      sessionStorage.setItem(epKey, String(entryPage));
      drawEntry();
    });
    document.getElementById("nextBtn")?.addEventListener("click", () => {
      entryPage = Math.min(totalPages - 1, entryPage + 1);
      sessionStorage.setItem(epKey, String(entryPage));
      drawEntry();
    });
    document.getElementById("submitBtn")?.addEventListener("click", async () => {
      const btn = document.getElementById("submitBtn");
      btn.disabled = true; btn.textContent = "Submitting…";
      const t0 = Number(sessionStorage.getItem(t0Key)) || Date.now();
      try {
        const out = await api("/entry-quiz/submit", { method: "POST", body: { answers, time_taken_seconds: Math.round((Date.now()-t0)/1000) } });
        sessionStorage.removeItem(epKey); sessionStorage.removeItem(t0Key);
        window.__entryAnswers = {};
        await syncMe();
        render(`
          <div class="page-header"><h1 class="page-title">Assessment <span class="accent">Complete!</span></h1></div>
          <div class="card" style="max-width:480px;text-align:center">
            <div style="font-size:3rem;margin-bottom:1rem">🎉</div>
            <p style="font-size:1.1rem;font-weight:600;margin-bottom:0.5rem">${escHtml(out.message || "Assessment submitted!")}</p>
            <p class="muted mb-md">Score: <strong style="color:var(--cyan)">${out.score_pct}%</strong></p>
            <a class="btn btn-primary" href="#/dashboard">Go to Dashboard →</a>
          </div>`);
      } catch (e) {
        setStatus("st", apiErrMsg(e), "err");
        btn.disabled = false; btn.textContent = "Submit Assessment →";
      }
    });
  }
  drawEntry();
}

/* ── Dashboard ── */
async function pageDashboard() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`<div class="card"><p class="muted pulse">Loading dashboard…</p></div>`);

  try {
    const [dash, recsResult, perfResult] = await Promise.allSettled([
      api("/dashboard"),
      api("/recommendations"),
      api("/performance"),
    ]);

    const dashData = dash.status === "fulfilled" ? dash.value : null;
    if (!dashData) { render(`<div class="card"><p class="status-err">Could not load dashboard: ${escHtml(dash.reason?.message || "")}</p></div>`); return; }

    const recs = recsResult.status === "fulfilled" ? recsResult.value : { recommendations: [], error: recsResult.reason?.message };
    const perf = perfResult.status === "fulfilled" ? perfResult.value : { chart_data: [] };

    const summary = dashData.summary || {};
    const rep = dashData.weak_area_report || [];
    const attempts = dashData.recent_quiz_attempts || [];
    const pieLabels = (dashData.charts?.strength_pie || []).map(x => x.label);
    const pieData = (dashData.charts?.strength_pie || []).map(x => x.count);

    render(`
      <div class="page-header">
        <h1 class="page-title">Your <span class="accent">Dashboard</span></h1>
        <p class="page-subtitle">Level: <strong style="color:var(--cyan)">${escHtml(dashData.user?.skill_level || "—")}</strong></p>
      </div>

      <div class="stats-row mb-lg">
        <div class="stat-pill stagger-el" style="--stagger:0.05s"><div class="stat-pill-val">${fmtPct(summary.overall_progress_pct)}</div><div class="stat-pill-label">Overall Progress</div></div>
        <div class="stat-pill stagger-el" style="--stagger:0.1s"><div class="stat-pill-val">${summary.enrolled_subjects ?? 0}</div><div class="stat-pill-label">Subjects</div></div>
        <div class="stat-pill stagger-el" style="--stagger:0.15s"><div class="stat-pill-val">${summary.topics_complete ?? 0}</div><div class="stat-pill-label">Topics Done</div></div>
        <div class="stat-pill stagger-el" style="--stagger:0.2s"><div class="stat-pill-val">${summary.topics_in_progress ?? 0}</div><div class="stat-pill-label">In Progress</div></div>
        <div class="stat-pill stagger-el" style="--stagger:0.25s"><div class="stat-pill-val" style="color:var(--red)">${summary.weak_topic_count ?? 0}</div><div class="stat-pill-label">Weak Areas</div></div>
      </div>

      <div class="dash-grid">
        <div class="card stagger-el" style="--stagger:0.3s">
          <div class="card-title mb-md">Mastery Mix</div>
          <div class="chart-wrap"><canvas id="pieC"></canvas></div>
        </div>
        <div class="card stagger-el" style="--stagger:0.35s">
          <div class="card-title mb-md">Topic Progress</div>
          <div class="chart-wrap"><canvas id="barC"></canvas></div>
        </div>

        <div class="card span-2 stagger-el" style="--stagger:0.4s">
          <div class="card-header">
            <div class="card-title">AI Recommendations</div>
            <a href="#/recommendations" class="btn btn-ghost btn-sm">View all →</a>
          </div>
          <div id="recBox"></div>
        </div>

        <div class="card span-2 stagger-el" style="--stagger:0.45s">
          <div class="card-header">
            <div class="card-title">Weak Area Report</div>
            <span class="dimmed">weak &lt;30% · average 30–65% · strong ≥65%</span>
          </div>
          <div class="table-wrapper">
            <table class="data-table">
              <thead><tr><th>Topic</th><th>Subject</th><th>Progress</th><th>Level</th></tr></thead>
              <tbody>${rep.map(r => `<tr>
                <td><strong>${escHtml(r.topic_name)}</strong></td>
                <td class="dimmed">${escHtml(r.subject_name)}</td>
                <td>${fmtPct(r.overall_progress_pct)}</td>
                <td><span class="badge badge-${escHtml(r.strength_category)}">${escHtml(r.strength_category)}</span></td>
              </tr>`).join("") || `<tr><td colspan="4" class="dimmed">No data yet. Complete some quizzes!</td></tr>`}</tbody>
            </table>
          </div>
        </div>

        <div class="card span-2 stagger-el" style="--stagger:0.5s">
          <div class="card-header">
            <div class="card-title">Recent Quiz Attempts</div>
            <a href="#/performance" class="btn btn-ghost btn-sm">Full report →</a>
          </div>
          <div class="table-wrapper">
            <table class="data-table">
              <thead><tr><th>Topic</th><th>Score</th><th>Time</th></tr></thead>
              <tbody>${attempts.map(a => `<tr>
                <td><strong>${escHtml(a.topic_name || a.topic_id)}</strong></td>
                <td><span style="color:${Number(a.score_pct)>=60?'var(--green)':'var(--amber)'}">${fmtPct(a.score_pct)}</span></td>
                <td class="dimmed">${a.time_taken_seconds != null ? `${a.time_taken_seconds}s` : "—"}</td>
              </tr>`).join("") || `<tr><td colspan="3" class="dimmed">No attempts yet. Take a quiz!</td></tr>`}</tbody>
            </table>
          </div>
        </div>
      </div>`);

    // Recs
    const recBox = document.getElementById("recBox");
    if (recBox) {
      if (recs.error) {
        recBox.innerHTML = `<p class="dimmed">AI recommendations unavailable: ${escHtml(recs.error)} <span style="color:var(--text-3)">(configure GEMINI_API_KEY on server)</span></p>`;
      } else {
        recBox.innerHTML = (recs.recommendations || []).map(r => `
          <div class="rec-card">
            <div class="rec-dot"></div>
            <div><div class="rec-title">${escHtml(r.title)}</div><div class="rec-detail">${escHtml(r.detail)}</div></div>
          </div>`).join("") || `<p class="dimmed">No recommendations yet.</p>`;
      }
    }

    // Charts
    ensureChartTheme();
    const ctxP = document.getElementById("pieC");
    if (ctxP && window.Chart) {
      pieChartRef = new Chart(ctxP, {
        type: "pie",
        data: { labels: pieLabels, datasets: [{ data: pieData, backgroundColor: ["rgba(244,63,94,0.8)","rgba(245,158,11,0.8)","rgba(16,185,129,0.8)"], borderWidth: 0, hoverOffset: 10 }] },
        options: { plugins: { legend: { position: "bottom", labels: { padding: 14, color: "#94a3b8" } } }, maintainAspectRatio: false, animation: { duration: 900 } },
      });
    }
    const barRows = perf.chart_data || [];
    const ctxB = document.getElementById("barC");
    if (ctxB && window.Chart) {
      barChartRef = new Chart(ctxB, {
        type: "bar",
        data: {
          labels: barRows.map(r => r.topic_name.length > 12 ? r.topic_name.slice(0,12)+"…" : r.topic_name),
          datasets: [{ label: "Progress %", data: barRows.map(r => r.overall_progress_pct), backgroundColor: "rgba(99,102,241,0.65)", borderRadius: 6, borderSkipped: false }],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 11 } } }, y: { max: 100, beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } } }, animation: { delay: ctx => ctx.dataIndex * 60, duration: 700 } },
      });
    }
  } catch (e) {
    render(`<div class="card"><p class="status-err">${escHtml(apiErrMsg(e))}</p></div>`);
  }
}

/* ── Performance ── */
async function pagePerformance() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`<div class="card"><p class="muted pulse">Loading performance data…</p></div>`);
  let perf;
  try { perf = await api("/performance"); }
  catch (e) { render(`<div class="card"><p class="status-err">${escHtml(apiErrMsg(e))}</p></div>`); return; }

  const rows = perf.chart_data || [];
  const dist = perf.strength_distribution || {};
  render(`
    <div class="page-header">
      <h1 class="page-title">Performance <span class="accent">Report</span></h1>
      <p class="page-subtitle">Detailed breakdown of your quiz scores and topic mastery.</p>
    </div>
    <div class="dash-grid">
      <div class="card stagger-el" style="--stagger:0.05s">
        <div class="card-title mb-md">Strength Distribution</div>
        <div class="chart-wrap"><canvas id="doughC"></canvas></div>
        <div class="flex gap-md mt-md" style="justify-content:center;flex-wrap:wrap">
          <span class="badge badge-weak">Weak: ${dist.weak||0}</span>
          <span class="badge badge-average">Average: ${dist.average||0}</span>
          <span class="badge badge-strong">Strong: ${dist.strong||0}</span>
        </div>
      </div>
      <div class="card stagger-el" style="--stagger:0.1s;grid-column:span 2">
        <div class="card-title mb-md">Topic Breakdown</div>
        <div class="table-wrapper">
          <table class="data-table">
            <thead><tr><th>Topic</th><th>Overall</th><th>Resources</th><th>Avg Quiz</th><th>Attempts</th><th>Best</th><th>Avg Time</th></tr></thead>
            <tbody>${rows.map(r => `<tr>
              <td><strong>${escHtml(r.topic_name)}</strong></td>
              <td>${fmtPct(r.overall_progress_pct)}</td>
              <td>${fmtPct(r.resource_completion_pct)}</td>
              <td>${fmtPct(r.avg_quiz_score)}</td>
              <td>${r.quiz_attempts ?? 0}</td>
              <td style="color:var(--green)">${fmtPct(r.best_quiz_score)}</td>
              <td class="dimmed">${r.avg_time_seconds != null ? `${r.avg_time_seconds}s` : "—"}</td>
            </tr>`).join("") || `<tr><td colspan="7" class="dimmed">No data yet.</td></tr>`}</tbody>
          </table>
        </div>
      </div>
    </div>`);

  ensureChartTheme();
  const ctx = document.getElementById("doughC");
  if (ctx && window.Chart) {
    pieChartRef = new Chart(ctx, {
      type: "doughnut",
      data: { labels: ["Weak","Average","Strong"], datasets: [{ data: [dist.weak||0,dist.average||0,dist.strong||0], backgroundColor: ["rgba(244,63,94,0.8)","rgba(245,158,11,0.8)","rgba(16,185,129,0.8)"], borderWidth: 0, hoverOffset: 8 }] },
      options: { plugins: { legend: { position: "bottom" } }, maintainAspectRatio: false, cutout: "60%", animation: { duration: 900 } },
    });
  }
}

/* ── Learning Path ── */
async function pageLearningPath() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`
    <div class="page-header">
      <h1 class="page-title">Learning <span class="accent">Path</span></h1>
      <p class="page-subtitle">AI-generated, day-by-day study plan based on your skill level and weak areas. Requires Gemini API key.</p>
    </div>
    <div class="card" style="max-width:600px">
      <div class="flex gap-md align-center mb-md" style="align-items:flex-end">
        <div class="field" style="margin:0;flex:1">
          <label class="field-label">Study duration (days)</label>
          <input id="days" type="number" class="input" value="14" min="1" max="120" />
        </div>
        <button type="button" class="btn btn-primary" id="genBtn">Generate Path →</button>
      </div>
      <p id="genSt" class="status-muted" style="min-height:1.3em"></p>
    </div>
    <div id="pathOut" class="mt-md"></div>`);

  document.getElementById("genBtn").onclick = async () => {
    const btn = document.getElementById("genBtn");
    const days = Number(document.getElementById("days")?.value) || 14;
    btn.disabled = true; btn.textContent = "Generating…";
    setStatus("genSt", "Asking Gemini for your personalized plan…", "muted");
    try {
      const data = await api("/learning-path", { method: "POST", body: { days } });
      const p = data.path || {};
      btn.disabled = false; btn.textContent = "Regenerate";
      setStatus("genSt", "", "muted");
      const out = document.getElementById("pathOut");
      if (!out) return;
      out.innerHTML = `
        <div class="card">
          <div class="card-header"><div class="card-title">Your ${days}-Day Plan</div></div>
          ${p.summary ? `<p class="muted mb-md">${escHtml(p.summary)}</p>` : ""}
          ${(p.steps || []).map((s, i) => `
            <div class="path-step stagger-el" style="--stagger:${i*0.07}s">
              <div class="path-step-num">${i+1}</div>
              <div class="path-step-body">
                <div class="path-step-range">${escHtml(s.day_range || "")}</div>
                <div class="path-step-focus">${escHtml(s.focus || "")}</div>
                ${s.tasks?.length ? `<ul class="path-step-tasks">${s.tasks.map(t=>`<li>${escHtml(t)}</li>`).join("")}</ul>` : ""}
                ${s.checkpoint ? `<div class="path-step-checkpoint">✓ ${escHtml(s.checkpoint)}</div>` : ""}
              </div>
            </div>`).join("")}
        </div>`;
    } catch (e) {
      setStatus("genSt", apiErrMsg(e), "err");
      btn.disabled = false; btn.textContent = "Generate Path →";
    }
  };
}

/* ── Subjects ── */
async function pageSubjects() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`<div class="card"><p class="muted pulse">Loading subjects…</p></div>`);
  let subjects;
  try { subjects = await api("/subjects"); }
  catch (e) { render(`<div class="card"><p class="status-err">${escHtml(apiErrMsg(e))}</p></div>`); return; }

  render(`
    <div class="page-header">
      <h1 class="page-title">Choose <span class="accent">Subjects</span></h1>
      <p class="page-subtitle">Select the subjects you want to study. You can change this anytime.</p>
    </div>
    <p id="st" class="status-muted mb-md" style="min-height:1.3em"></p>
    <div class="subjects-grid" id="subjectGrid"></div>
    <div class="flex gap-md mt-lg" style="flex-wrap:wrap">
      <button type="button" class="btn btn-primary" id="saveSubjects">Save Selection →</button>
    </div>`);

  const grid = document.getElementById("subjectGrid");
  if (grid) {
    grid.innerHTML = subjects.map(s => `
      <div class="subject-card ${s.enrolled ? "enrolled" : ""}" data-id="${escHtml(s.id)}">
        <div class="subject-card-top">
          <div>
            <div class="subject-name">${escHtml(s.name)}</div>
            <code style="font-size:0.72rem;color:var(--text-3)">${escHtml(s.id)}</code>
          </div>
          <label class="checkbox-label" style="flex-shrink:0">
            <input type="checkbox" class="subj-pick" data-id="${escHtml(s.id)}" ${s.enrolled ? "checked" : ""}>
          </label>
        </div>
        <div class="subject-desc">${escHtml(s.description || "")}</div>
        <div class="subject-actions">
          <button class="btn btn-secondary btn-sm enroll-btn" data-id="${escHtml(s.id)}">Enroll</button>
          <button class="btn btn-ghost btn-sm unenroll-btn" data-id="${escHtml(s.id)}">Unenroll</button>
        </div>
      </div>`).join("");
    stagger(grid, ".subject-card");
  }

  document.getElementById("saveSubjects").onclick = async () => {
    const ids = [...document.querySelectorAll(".subj-pick")].filter(x => x.checked).map(x => x.getAttribute("data-id"));
    try {
      const r = await api("/select-subjects", { method: "POST", body: { subject_ids: ids } });
      await syncMe();
      toast(r.message, "ok");
      if (r.requires_entry_quiz) setTimeout(() => location.hash = "#/entry-quiz", 600);
      else await pageSubjects();
    } catch (e) { setStatus("st", apiErrMsg(e), "err"); }
  };

  document.querySelectorAll(".enroll-btn").forEach(b => {
    b.onclick = async () => {
      const id = b.getAttribute("data-id");
      try {
        const r = await api(`/enroll/${encodeURIComponent(id)}`, { method: "POST" });
        await syncMe();
        toast("Enrolled!", "ok");
        if (r.requires_entry_quiz) location.hash = "#/entry-quiz";
        else await pageSubjects();
      } catch (e) { setStatus("st", apiErrMsg(e), "err"); }
    };
  });
  document.querySelectorAll(".unenroll-btn").forEach(b => {
    b.onclick = async () => {
      const id = b.getAttribute("data-id");
      try {
        await api(`/unenroll/${encodeURIComponent(id)}`, { method: "POST" });
        await syncMe();
        toast("Unenrolled.", "info");
        await pageSubjects();
      } catch (e) { setStatus("st", apiErrMsg(e), "err"); }
    };
  });
}

/* ── Topics fuzzy search ── */
function levenshtein(a, b) {
  const m=a.length,n=b.length,dp=Array.from({length:m+1},()=>new Array(n+1).fill(0));
  for(let i=0;i<=m;i++)dp[i][0]=i; for(let j=0;j<=n;j++)dp[0][j]=j;
  for(let i=1;i<=m;i++) for(let j=1;j<=n;j++){const c=a[i-1]===b[j-1]?0:1;dp[i][j]=Math.min(dp[i-1][j]+1,dp[i][j-1]+1,dp[i-1][j-1]+c);}
  return dp[m][n];
}
function topicScore(row, q) {
  if (!q.trim()) return 1;
  const tokens = q.toLowerCase().split(/\s+/).filter(t=>t.length>0);
  const blob = `${row.name} ${row.description||""} ${row.subject_name||""}`.toLowerCase();
  let hits=0;
  for(const t of tokens){if(blob.includes(t)){hits++;continue;}let best=false;for(const w of blob.split(/\W+/)){if(w.length>=3&&levenshtein(w,t)<=1){best=true;break;}}if(best)hits+=0.7;}
  return hits/tokens.length;
}

let topicsCache = [];

async function pageTopics() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`
    <div class="page-header">
      <h1 class="page-title">All <span class="accent">Topics</span></h1>
    </div>
    <div class="flex gap-md mb-md" style="flex-wrap:wrap;align-items:flex-end">
      <div style="flex:1;min-width:200px">
        <label class="field-label">Search topics</label>
        <input id="tSearch" type="search" class="input" placeholder="e.g. arrays, recursion, networking…" />
      </div>
      <button type="button" class="btn btn-outline btn-sm" id="reloadTopics">↻ Reload</button>
    </div>
    <div id="topicsList"></div>`);

  async function loadTopics() {
    const el = document.getElementById("topicsList");
    if (el) el.innerHTML = `<p class="muted pulse">Loading…</p>`;
    try {
      topicsCache = await api("/topics-with-progress");
      filterTopics();
    } catch (e) {
      if (el) el.innerHTML = `<p class="status-err">${escHtml(apiErrMsg(e))}</p>`;
    }
  }
  function filterTopics() {
    const q = document.getElementById("tSearch")?.value || "";
    const scored = topicsCache.map(r => ({ r, s: topicScore(r, q) })).filter(x => x.s > 0.35 || !q.trim());
    scored.sort((a,b) => b.s - a.s || (b.r.completion_pct||0) - (a.r.completion_pct||0));
    const el = document.getElementById("topicsList");
    if (!el) return;
    el.innerHTML = scored.length
      ? scored.map(({ r }) => `
          <div class="topic-item stagger-el">
            <div class="topic-info">
              <div class="topic-name">${escHtml(r.name)}</div>
              <div class="topic-meta">${escHtml(r.subject_name)} · ${fmtPct(r.completion_pct)} complete</div>
              <div class="progress-bar mt-sm" style="height:3px;max-width:200px"><div class="progress-fill" style="width:${r.completion_pct||0}%"></div></div>
            </div>
            <div class="topic-actions">
              <a href="#/topic?topic_id=${encodeURIComponent(r.id)}" class="btn btn-ghost btn-sm">Resources</a>
              <a href="#/quiz?topic_id=${encodeURIComponent(r.id)}" class="btn btn-secondary btn-sm">Quiz →</a>
            </div>
          </div>`).join("")
      : `<div class="empty-state"><div class="empty-icon">🔍</div><p>No topics match your search.</p></div>`;
    stagger(el, ".topic-item");
  }
  document.getElementById("tSearch")?.addEventListener("input", filterTopics);
  document.getElementById("reloadTopics")?.addEventListener("click", loadTopics);
  await loadTopics();
}

/* ── Topic Detail ── */
async function pageTopicDetail(topicId) {
  if (!requireAuth()) return;
  destroyCharts();
  if (!topicId) { render(`<p class="status-err">Missing topic ID.</p>`); return; }
  render(`<div class="card"><p class="muted pulse">Loading topic…</p></div>`);
  let topic;
  try { topic = await api(`/topics/${encodeURIComponent(topicId)}`); }
  catch (e) { render(`<div class="card"><p class="status-err">${escHtml(apiErrMsg(e))}</p><a href="#/topics" class="btn btn-ghost btn-sm mt-md">← Back</a></div>`); return; }

  render(`
    <div class="page-header">
      <a href="#/topics" class="btn btn-ghost btn-sm mb-md">← All Topics</a>
      <h1 class="page-title">${escHtml(topic.name)}</h1>
      ${topic.description ? `<p class="page-subtitle">${escHtml(topic.description)}</p>` : ""}
    </div>
    <div class="flex gap-md mb-lg" style="flex-wrap:wrap">
      <a href="#/quiz?topic_id=${encodeURIComponent(topic.id)}" class="btn btn-primary">Standard Quiz →</a>
      <a href="#/quiz?topic_id=${encodeURIComponent(topic.id)}&personalized=1" class="btn btn-secondary">✨ Personalized Quiz (AI)</a>
    </div>
    <div class="card">
      <div class="card-title mb-md">Resources</div>
      <div id="resList"><p class="muted pulse">Loading resources…</p></div>
    </div>`);

  try {
    const resources = await api("/resources", { query: { topic_id: topic.id } });
    const resList = document.getElementById("resList");
    if (!resList) return;
    if (!resources.length) { resList.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div><p>No resources for this topic yet.</p></div>`; return; }
    resList.innerHTML = resources.map(r => `
      <div class="res-card stagger-el">
        <div class="res-icon">${resIcon(r.type)}</div>
        <div class="res-body">
          <div class="res-title">${escHtml(r.title)} <span class="badge badge-cyan">${escHtml(r.type)}</span></div>
          ${r.description ? `<div class="res-desc">${escHtml(r.description)}</div>` : ""}
          ${r.personalized_note ? `<div class="res-desc" style="color:var(--indigo-2)">✨ ${escHtml(r.personalized_note)}</div>` : ""}
          <div class="res-actions">
            <a href="${escHtml(r.url)}" target="_blank" rel="noreferrer" class="res-link">Open →</a>
            <button class="btn btn-xs ${r.completed ? "btn-ghost" : "btn-secondary"} toggle-res" data-rid="${escHtml(r.id)}">${r.completed ? "✓ Done" : "Mark done"}</button>
          </div>
        </div>
      </div>`).join("");
    stagger(resList, ".res-card");

    resList.querySelectorAll(".toggle-res").forEach(btn => {
      btn.onclick = async () => {
        try {
          await api("/mark-resource-complete", { method: "POST", body: { resource_id: btn.getAttribute("data-rid"), topic_id: topic.id } });
          await syncMe();
          toast("Progress saved!", "ok");
          await pageTopicDetail(topic.id);
        } catch (e) { toast(apiErrMsg(e), "err"); }
      };
    });
  } catch (e) {
    const rl = document.getElementById("resList");
    if (rl) rl.innerHTML = `<p class="status-err">${escHtml(apiErrMsg(e))}</p>`;
  }
}

/* ── Quiz ── */
async function pageQuiz(topicId, personalized) {
  if (!requireAuth()) return;
  destroyCharts();
  if (!topicId) { render(`<p class="status-err">Missing topic_id parameter.</p>`); return; }
  render(`<div class="card"><p class="muted pulse">Loading quiz…</p></div>`);
  const t0 = Date.now();
  let quiz, fallbackNote = "";

  try {
    if (personalized) {
      try { quiz = await api("/quiz", { query: { topic_id: topicId, personalized: "true" } }); }
      catch (e) {
        if ([503,502,500,429].includes(e.status) || e instanceof TypeError) {
          quiz = await api("/quiz", { query: { topic_id: topicId } });
          fallbackNote = `<div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:9px;padding:0.7rem 1rem;margin-bottom:1rem;font-size:0.85rem;color:var(--amber)">AI personalization unavailable — serving standard quiz instead.</div>`;
        } else throw e;
      }
    } else {
      quiz = await api("/quiz", { query: { topic_id: topicId } });
    }
  } catch (e) {
    render(`<div class="card"><p class="status-err">${escHtml(apiErrMsg(e))}</p><a href="#/topics" class="btn btn-ghost btn-sm mt-md">← Topics</a></div>`);
    return;
  }

  render(`
    <div class="page-header">
      <a href="#/topic?topic_id=${encodeURIComponent(topicId)}" class="btn btn-ghost btn-sm mb-md">← Topic</a>
      <h1 class="page-title">${escHtml(quiz.title)}</h1>
      <p class="page-subtitle">${quiz.total_questions} questions · ${quiz.personalized ? "✨ Personalized" : "Standard"}</p>
    </div>
    ${fallbackNote}
    <div id="quizQuestions"></div>
    <div class="flex gap-md mt-lg" style="flex-wrap:wrap">
      <button type="button" class="btn btn-primary" id="submitQuiz">Submit Quiz →</button>
    </div>
    <div id="quizResult" class="mt-md"></div>`);

  const qqEl = document.getElementById("quizQuestions");
  if (!qqEl) return;
  qqEl.innerHTML = (quiz.questions || []).map((q, i) => `
    <div class="q-card stagger-el" style="--stagger:${i*0.04}s">
      <div class="q-card-body mb-sm"><strong>${i+1}.</strong> ${escHtml(q.question)}</div>
      <div class="radio-group">
        ${q.options.map((o, j) => `<label class="radio-opt"><input type="radio" name="q_${escHtml(q.id)}" value="${j}"> ${escHtml(o)}</label>`).join("")}
      </div>
    </div>`).join("");

  document.getElementById("submitQuiz").onclick = async () => {
    const btn = document.getElementById("submitQuiz");
    const answers = {};
    for (const q of quiz.questions) {
      const picked = document.querySelector(`input[name="q_${CSS.escape(q.id)}"]:checked`);
      if (picked) answers[q.id] = Number(picked.value);
    }
    btn.disabled = true; btn.textContent = "Submitting…";
    try {
      const out = await api("/submit-quiz", { method: "POST", body: { quiz_id: quiz.quiz_id, topic_id: quiz.topic_id, answers, time_taken_seconds: Math.round((Date.now()-t0)/1000) } });
      await syncMe();
      const color = out.score_pct >= 80 ? "var(--green)" : out.score_pct >= 60 ? "var(--amber)" : "var(--red)";
      const result = document.getElementById("quizResult");
      if (!result) return;
      result.innerHTML = `
        <div class="card">
          <div class="quiz-results-banner">
            <div style="font-size:1.5rem;font-weight:700;color:${color}">${out.score_pct}%</div>
            <div style="color:var(--text-2);font-size:0.9rem;margin-top:0.25rem">${escHtml(out.feedback)}</div>
            ${out.personalized_feedback ? `<div style="color:var(--indigo-2);font-size:0.85rem;margin-top:0.5rem">${escHtml(out.personalized_feedback)}</div>` : ""}
          </div>
          <div class="table-wrapper">
            <table class="data-table">
              <thead><tr><th>#</th><th>Result</th></tr></thead>
              <tbody>${(out.results||[]).map((r,i) => `
                <tr>
                  <td class="dimmed">${i+1}. ${escHtml(r.question?.slice?.(0,80) || "")}</td>
                  <td>${r.is_correct ? '<span style="color:var(--green)">✓ Correct</span>' : `<span style="color:var(--red)">✗ Wrong — correct: ${escHtml(r.correct_option_text||"")}</span>`}</td>
                </tr>`).join("")}</tbody>
            </table>
          </div>
          <div class="flex gap-md mt-md" style="flex-wrap:wrap">
            <a href="#/quiz?topic_id=${encodeURIComponent(topicId)}" class="btn btn-secondary">Try again</a>
            <a href="#/topics" class="btn btn-ghost">← Topics</a>
          </div>
        </div>`;
      result.scrollIntoView({ behavior: "smooth", block: "start" });
      btn.hidden = true;
    } catch (e) {
      const r = document.getElementById("quizResult");
      if (r) r.innerHTML = `<p class="status-err">${escHtml(apiErrMsg(e))}</p>`;
      btn.disabled = false; btn.textContent = "Submit Quiz →";
    }
  };
}

/* ── Recommendations ── */
async function pageRecommendations() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`<div class="page-header"><h1 class="page-title">AI <span class="accent">Recommendations</span></h1><p class="page-subtitle">Personalized suggestions based on your weak areas and progress. Powered by Gemini.</p></div><div class="card"><p class="muted pulse">Loading…</p></div>`);
  try {
    const data = await api("/recommendations");
    const items = data.recommendations || [];
    const el = document.getElementById("app");
    const existing = el?.querySelector(".card");
    if (existing) existing.innerHTML = items.length
      ? items.map(r => `<div class="rec-card stagger-el"><div class="rec-dot"></div><div><div class="rec-title">${escHtml(r.title)}</div><div class="rec-detail">${escHtml(r.detail)}</div></div></div>`).join("")
      : `<div class="empty-state"><div class="empty-icon">🤖</div><p>No recommendations yet. Complete some quizzes to get personalized suggestions!</p></div>`;
    stagger(existing, ".rec-card");
  } catch (e) {
    const hint = e.status===503 ? " Configure GEMINI_API_KEY on the server." : e.status===401||e.status===403 ? " Try signing in again." : "";
    render(`<div class="card"><p class="status-err">${escHtml(apiErrMsg(e))}</p>${hint?`<p class="dimmed mt-sm">${escHtml(hint)}</p>`:""}</div>`);
  }
}

/* ── Chat ── */
async function pageChat() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`
    <div class="page-header">
      <h1 class="page-title">AI <span class="accent">Tutor</span></h1>
      <p class="page-subtitle">Ask doubts, get concept explanations, or request resources. Mode is detected automatically. Powered by Gemini.</p>
    </div>
    <div class="chat-container">
      <div class="chat-header">
        <div style="font-weight:600;font-size:0.9rem">Chat Session <span id="sidSpan" style="font-size:0.75rem;color:var(--text-3);font-weight:400"></span></div>
        <button type="button" class="btn btn-ghost btn-sm" id="newSessBtn">New session</button>
      </div>
      <div class="chat-messages" id="chatMessages">
        <div class="chat-empty">👋 Ask me anything CS-related — doubts, concepts, or resource suggestions!</div>
      </div>
      <div class="chat-input-row">
        <textarea id="chatInput" class="chat-input" rows="1" placeholder="Type your question… (Enter to send, Shift+Enter for newline)"></textarea>
        <button type="button" class="btn btn-primary" id="chatSendBtn">Send</button>
      </div>
    </div>
    <div class="flex gap-md mt-md">
      <button type="button" class="btn btn-ghost btn-sm" id="loadHistBtn">Load history</button>
    </div>`);

  const sidSpan = document.getElementById("sidSpan");
  const setSid = () => { if (sidSpan) sidSpan.textContent = storage.sessionId ? `#${storage.sessionId.slice(0,8)}…` : "(new)"; };
  setSid();

  const chatBox = document.getElementById("chatMessages");

  function addBubble(role, content, mode) {
    if (!chatBox) return;
    const div = document.createElement("div");
    div.className = `chat-bubble ${role === "user" ? "user" : "bot"}`;
    if (role !== "user" && mode) div.innerHTML = `<div class="mode-tag">${escHtml(mode)}</div>${escHtml(content)}`;
    else div.textContent = content;
    // Remove empty state
    const empty = chatBox.querySelector(".chat-empty");
    if (empty) empty.remove();
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  document.getElementById("newSessBtn").onclick = () => {
    storage.sessionId = "";
    setSid();
    if (chatBox) chatBox.innerHTML = `<div class="chat-empty">👋 New session started. Ask me anything!</div>`;
  };

  document.getElementById("loadHistBtn").onclick = async () => {
    try {
      if (!storage.sessionId) {
        const all = await api("/chat/history");
        const sessions = all.sessions || [];
        if (!chatBox) return;
        chatBox.innerHTML = sessions.length
          ? sessions.map(s => `<div class="chat-bubble bot"><div class="mode-tag">Session</div>ID: ${escHtml(s.session_id.slice(0,8))}… · ${s.message_count} messages</div>`).join("")
          : `<div class="chat-empty">No past sessions.</div>`;
        return;
      }
      const h = await api("/chat/history", { query: { session_id: storage.sessionId } });
      if (!chatBox) return;
      chatBox.innerHTML = "";
      const msgs = (h.messages || []);
      if (!msgs.length) { chatBox.innerHTML = `<div class="chat-empty">No messages in this session.</div>`; return; }
      // Display in chronological order (oldest first)
      msgs.forEach(m => addBubble(m.role === "user" ? "user" : "bot", m.content, m.detected_mode));
    } catch (e) { toast(apiErrMsg(e), "err"); }
  };

  const doSend = async () => {
    const input = document.getElementById("chatInput");
    const message = input?.value.trim();
    if (!message) return;
    const sendBtn = document.getElementById("chatSendBtn");
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = "…"; }
    if (input) input.value = "";
    addBubble("user", message, null);
    try {
      const body = { message };
      if (storage.sessionId) body.session_id = storage.sessionId;
      const r = await api("/chat", { method: "POST", body });
      storage.sessionId = r.session_id;
      setSid();
      addBubble("bot", r.response || "", r.detected_mode);
    } catch (e) {
      addBubble("bot", `⚠ ${apiErrMsg(e)}`, "error");
    } finally {
      if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = "Send"; }
    }
  };

  document.getElementById("chatSendBtn").onclick = doSend;
  document.getElementById("chatInput")?.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
  });

  // Auto-resize textarea
  document.getElementById("chatInput")?.addEventListener("input", function() {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 120) + "px";
  });
}

/* ── Games ── */
async function pageGames() {
  if (!requireAuth()) return;
  destroyCharts();
  render(`
    <div class="page-header">
      <h1 class="page-title">Topic <span class="accent">Games</span></h1>
      <p class="page-subtitle">Interactive learning games embedded right here — no external portals needed.</p>
    </div>
    <div class="card" style="max-width:480px;margin-bottom:1.25rem">
      <div class="flex gap-md align-center" style="align-items:flex-end">
        <div class="field" style="flex:1;margin:0">
          <label class="field-label">Select topic</label>
          <select id="topicPick" class="select"><option value="">Choose a topic…</option></select>
        </div>
        <button type="button" class="btn btn-primary" id="loadGamesBtn">Load Games →</button>
      </div>
    </div>
    <div id="gamesArea"></div>`);

  try {
    const topics = await api("/games/topics");
    const sel = document.getElementById("topicPick");
    for (const tid of (topics.topic_ids || [])) {
      const o = new Option(tid, tid);
      sel?.add(o);
    }
    if (!(topics.topic_ids || []).length) {
      const ga = document.getElementById("gamesArea");
      if (ga) ga.innerHTML = `<div class="empty-state"><div class="empty-icon">🎮</div><p>No game packs configured for any topic yet.</p></div>`;
    }
  } catch (e) {
    const ga = document.getElementById("gamesArea");
    if (ga) ga.innerHTML = `<p class="status-err">${escHtml(apiErrMsg(e))}</p>`;
  }

  document.getElementById("loadGamesBtn").onclick = async () => {
    const tid = document.getElementById("topicPick")?.value;
    if (!tid) return;
    const ga = document.getElementById("gamesArea");
    if (!ga) return;
    ga.innerHTML = `<p class="muted pulse">Loading games…</p>`;
    try {
      const pack = await api(`/games/topics/${encodeURIComponent(tid)}/playsets`);
      const games = pack.games || [];
      if (!games.length) { ga.innerHTML = `<div class="empty-state"><div class="empty-icon">🎮</div><p>No games for this topic yet.</p></div>`; return; }
      ga.innerHTML = `<div class="game-list">${games.map((g, idx) => `
        <div class="game-card">
          <span class="badge badge-info game-kind-badge">${escHtml(g.kind)}</span>
          <div style="font-weight:600;font-size:0.95rem">${escHtml(g.title)}</div>
          <div class="dimmed">${escHtml(g.description || "")}</div>
          <button class="btn btn-secondary btn-sm play-btn" data-idx="${idx}">▶ Play</button>
        </div>`).join("")}</div>
        <div id="gameCanvas" class="game-area" style="display:none"></div>`;
      stagger(ga, ".game-card");
      ga.querySelectorAll(".play-btn").forEach(b => {
        b.onclick = () => {
          const g = games[Number(b.getAttribute("data-idx"))];
          const canvas = document.getElementById("gameCanvas");
          if (canvas) { canvas.style.display = "block"; canvas.scrollIntoView({ behavior: "smooth", block: "start" }); }
          runEmbeddedGame(tid, g, canvas);
        };
      });
    } catch (e) { ga.innerHTML = `<p class="status-err">${escHtml(apiErrMsg(e))}</p>`; }
  };
}

async function runEmbeddedGame(topicId, g, host) {
  if (!host) return;
  const t0 = Date.now(); let attempts = 0;

  async function finish(score, accuracy, completed) {
    const completion_time = (Date.now() - t0) / 1000;
    try { await api("/games/embedded/result", { method: "POST", body: { topic_id: topicId, game_id: g.game_id, score, accuracy, attempts, completion_time, completed } }); } catch {}
    host.innerHTML = `<div style="text-align:center;padding:2rem"><div style="font-size:2.5rem;margin-bottom:0.75rem">${completed?"🎉":"👍"}</div><div style="font-weight:600;margin-bottom:0.5rem">${completed?"Well done!":"Game Over"}</div><p class="muted">Accuracy: <strong>${accuracy}%</strong></p><button class="btn btn-secondary mt-md" onclick="this.closest('.game-area').style.display='none'">Close</button></div>`;
  }

  if (g.kind === "matching") {
    const pairs = [...g.pairs];
    const terms = pairs.map((p,i)=>({...p,i})).sort(()=>Math.random()-0.5);
    const defs  = pairs.map((p,i)=>({text:p.definition,i})).sort(()=>Math.random()-0.5);
    let sel=null, matched=new Set();
    host.innerHTML = `<h4 style="margin-bottom:0.5rem;font-family:var(--font-display)">${escHtml(g.title)}</h4><p class="dimmed mb-md">Match each term to its definition.</p><div class="pairs-grid" id="pg"></div>`;
    const grid = host.querySelector("#pg");
    function drawMatch() {
      grid.innerHTML = "";
      const click = (node, isTerm, idx) => {
        if (matched.has(idx)) return; attempts++;
        if (!sel) { sel={isTerm,idx,node}; node.classList.add("picked"); return; }
        if (sel.isTerm === isTerm) { sel.node.classList.remove("picked"); sel={isTerm,idx,node}; grid.querySelectorAll(".picked").forEach(x=>x.classList.remove("picked")); node.classList.add("picked"); return; }
        const ok = sel.idx === idx;
        if (ok) { matched.add(idx); sel.node.classList.add("matched"); node.classList.add("matched"); }
        sel.node.classList.remove("picked"); sel=null;
        if (matched.size === pairs.length) finish(pairs.length, Math.round(pairs.length/Math.max(attempts,1)*100), true);
      };
      terms.forEach(p=>{ const d=document.createElement("button"); d.type="button"; d.className="pair-btn"; d.textContent=p.term; d.onclick=()=>click(d,true,p.i); grid.appendChild(d); });
      defs.forEach(p=>{  const d=document.createElement("button"); d.type="button"; d.className="pair-btn"; d.textContent=p.text; d.onclick=()=>click(d,false,p.i); grid.appendChild(d); });
    }
    drawMatch();
  } else if (g.kind === "block_order") {
    let order = g.blocks.map((_,i)=>i).sort(()=>Math.random()-0.5);
    host.innerHTML = `<h4 style="margin-bottom:0.5rem;font-family:var(--font-display)">${escHtml(g.title)}</h4><p class="dimmed mb-md">Arrange the blocks in the correct order using ↑↓.</p><ol id="bl" style="list-style:none;padding:0"></ol><button class="btn btn-primary mt-md" id="checkOrder">Check Order</button>`;
    const bl = host.querySelector("#bl");
    function renderBlocks() {
      bl.innerHTML = order.map(idx=>`
        <li style="display:flex;align-items:center;gap:0.65rem;margin-bottom:0.5rem;background:var(--surface-2);border:1px solid var(--border-2);border-radius:9px;padding:0.65rem 0.85rem">
          <span style="flex:1;font-size:0.88rem">${escHtml(g.blocks[idx])}</span>
          <button class="btn btn-ghost btn-xs up" data-i="${idx}">↑</button>
          <button class="btn btn-ghost btn-xs dn" data-i="${idx}">↓</button>
        </li>`).join("");
      bl.querySelectorAll(".up").forEach(b=>{ b.onclick=()=>{ const i=order.indexOf(Number(b.getAttribute("data-i"))); if(i>0){[order[i-1],order[i]]=[order[i],order[i-1]];attempts++;renderBlocks();} }; });
      bl.querySelectorAll(".dn").forEach(b=>{  b.onclick=()=>{ const i=order.indexOf(Number(b.getAttribute("data-i"))); if(i<order.length-1){[order[i+1],order[i]]=[order[i],order[i+1]];attempts++;renderBlocks();} }; });
    }
    renderBlocks();
    host.querySelector("#checkOrder").onclick=()=>{ const ok=order.every((v,i)=>v===g.correct_order[i]); finish(ok?1:0,ok?100:0,ok); };
  } else if (g.kind === "true_false") {
    let i=0, correct=0;
    const qs = g.questions || [];
    host.innerHTML = `<h4 style="margin-bottom:0.5rem;font-family:var(--font-display)">${escHtml(g.title)}</h4><div id="tfArea"></div>`;
    function step() {
      if (i >= qs.length) { finish(correct,Math.round(correct/qs.length*100),true); return; }
      const q=qs[i];
      const wrap=host.querySelector("#tfArea");
      wrap.innerHTML = `
        <div style="font-size:0.9rem;margin-bottom:1rem;padding:0.75rem;background:var(--surface-2);border-radius:9px"><strong>${escHtml(q.statement)}</strong></div>
        <div style="display:flex;gap:0.75rem">
          <button class="btn btn-primary" id="tfT">✓ True</button>
          <button class="btn btn-outline" id="tfF">✗ False</button>
        </div>
        <div class="dimmed mt-sm">${i+1} / ${qs.length}</div>`;
      wrap.querySelector("#tfT").onclick=()=>{ attempts++; if(q.answer===true)correct++; i++; step(); };
      wrap.querySelector("#tfF").onclick=()=>{ attempts++; if(q.answer===false)correct++; i++; step(); };
    }
    step();
  }
}

/* ══════════════════════════════════════════════════════
   ROUTER
══════════════════════════════════════════════════════ */
async function router() {
  destroyCharts();
  await refreshMe();

  if (!location.hash || location.hash === "#" || location.hash === "#/") {
    location.hash = storage.token ? "#/dashboard" : "#/home";
    return;
  }

  let { path, query } = parseRoute();

  // Logged-in users shouldn't see login/register
  if (storage.token && (path === "/login" || path === "/register")) {
    location.hash = "#/dashboard"; return;
  }

  // Onboarding redirects (only for auth'd users)
  if (storage.token) {
    const redir = getOnboardingRedirect(path);
    if (redir && redir !== path) { location.hash = `#${redir}`; return; }
  }

  // Auth guard
  if (!storage.token && !PUBLIC_PATHS.has(path)) {
    location.hash = "#/login"; return;
  }

  buildTopNav(path);
  updateOnboardingStrip();

  switch (path) {
    case "/home":         return pageHome();
    case "/login":        return pageLogin();
    case "/register":     return pageRegister();
    case "/profile":      return pageProfile();
    case "/entry-quiz":   return pageEntryQuiz();
    case "/dashboard":    return pageDashboard();
    case "/performance":  return pagePerformance();
    case "/learning-path":return pageLearningPath();
    case "/subjects":     return pageSubjects();
    case "/topics":       return pageTopics();
    case "/topic":        return pageTopicDetail(query.topic_id || "");
    case "/quiz":         return pageQuiz(query.topic_id || "", query.personalized === "1" || query.personalized === "true");
    case "/recommendations": return pageRecommendations();
    case "/chat":         return pageChat();
    case "/games":        return pageGames();
    default:              location.hash = storage.token ? "#/dashboard" : "#/home";
  }
}

/* ── Boot ── */
installGlobalHandlers();
window.addEventListener("hashchange", router);
router();
