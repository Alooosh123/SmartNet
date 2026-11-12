import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, Wifi, Users, CreditCard, Layers3, LogOut, RefreshCw,
  Router, ShieldCheck, FileDown, Plus, Power, CheckCircle2, XCircle,
  Menu, X, AlertTriangle, Search, Eye, CalendarClock, MessageCircle, LockKeyhole
} from "lucide-react";

const API = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function api(path, token, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch { /* response was not JSON */ }
    throw new Error(message);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.blob();
}

const nav = [
  { id: "overview", label: "نظرة عامة", icon: Activity },
  { id: "router", label: "الراوتر والمستخدمون", icon: Router },
  { id: "cards", label: "كروت الهوت سبوت", icon: Layers3 },
  { id: "clients", label: "المشتركون", icon: Users },
  { id: "payments", label: "طلبات الاشتراك", icon: CreditCard },
];
const clientNav = [
  { id: "overview", label: "حسابي", icon: Activity },
  { id: "chat", label: "المساعد والدعم", icon: MessageCircle },
];

function Registration({ onBack }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [plan, setPlan] = useState("monthly");
  const [request, setRequest] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const data = await api("/auth/register", "", {
        method: "POST",
        body: JSON.stringify({ username, password, plan }),
      });
      setRequest(data);
      setMessage(data.message || "تم إنشاء طلب الاشتراك.");
      if (data.payment_url) window.open(data.payment_url, "_blank", "noopener");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function checkStatus() {
    if (!request?.registration_token) return;
    setBusy(true); setError("");
    try {
      const data = await api(`/auth/registrations/${request.registration_id}/status`, "", {
        headers: { "X-Registration-Token": request.registration_token },
      });
      setStatus(data);
      setMessage(data.processed ? "تم اعتماد الاشتراك. يمكنك الآن تسجيل الدخول." :
        data.paid ? "تم تسجيل الدفع، والطلب بانتظار اعتماد الإدارة." :
        data.receipt_uploaded ? "تم رفع الإيصال، والطلب بانتظار المراجعة." : "الطلب بانتظار إكمال الدفع.");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function demoPay() {
    if (!request?.registration_token) return;
    setBusy(true); setError("");
    try {
      await api(`/auth/registrations/${request.registration_id}/demo-pay`, "", {
        method: "POST",
        headers: { "X-Registration-Token": request.registration_token },
      });
      await checkStatus();
    } catch (err) { setError(err.message); setBusy(false); }
  }

  async function uploadReceipt(event) {
    const file = event.target.files?.[0];
    if (!file || !request?.registration_token) return;
    setBusy(true); setError("");
    try {
      const form = new FormData(); form.append("file", file);
      await api(`/auth/registrations/${request.registration_id}/receipt`, "", {
        method: "POST",
        headers: { "X-Registration-Token": request.registration_token },
        body: form,
      });
      setMessage("تم رفع الإيصال. انتظر مراجعة الإدارة ولا تغلق هذه الجلسة قبل حفظ رقم الطلب.");
      await checkStatus();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); event.target.value = ""; }
  }

  return <main className="login-shell"><div className="login-card">
    <div className="brand-mark"><Wifi size={28}/></div>
    <p className="eyebrow">SMARTNET SUBSCRIPTIONS</p>
    <h1>إنشاء اشتراك جديد</h1>
    <p className="muted">أنشئ طلبك، ثم أكمل الدفع وانتظر مراجعة الإدارة.</p>
    {!request ? <form onSubmit={submit} className="form-stack">
      <label>اسم المستخدم<input value={username} onChange={e=>setUsername(e.target.value)} minLength={3} required /></label>
      <label>كلمة المرور<input type="password" value={password} onChange={e=>setPassword(e.target.value)} minLength={10} required /><small className="muted">10 أحرف على الأقل.</small></label>
      <label>الباقة<select value={plan} onChange={e=>setPlan(e.target.value)}><option value="monthly">شهري — 20 USD</option><option value="semi_annual">نصف سنة — 60 USD</option><option value="annual">سنوي — 100 USD</option></select></label>
      {error && <div className="alert error"><AlertTriangle size={17}/>{error}</div>}
      <button className="primary full" disabled={busy}>{busy ? "جارٍ إنشاء الطلب..." : "إنشاء طلب الاشتراك"}</button>
    </form> : <div className="form-stack">
      <div className="registration-info">
        <b>رقم الطلب: #{request.registration_id}</b>
        <span>الباقة: {request.plan_name}</span>
        <span>المبلغ: {request.price} USD</span>
        <span>اسم المستخدم: {username}</span>
        <small className="muted">احتفظ بهذه الجلسة ورقم الطلب ورمز الوصول الخاص بها لمتابعة حالة الطلب.</small>
      </div>
      {request.payment_url && <a className="primary full external-payment" href={request.payment_url} target="_blank" rel="noreferrer">فتح بوابة الدفع</a>}
      {request.payment_demo_available && <button className="secondary full" onClick={demoPay} disabled={busy}>تأكيد دفع تجريبي (للتطوير فقط)</button>}
      {!request.payment_url && !request.payment_demo_available && <p className="muted">حوّل المبلغ عبر قناة الدفع المتفق عليها، ثم ارفع صورة الحوالة. ستراجع الإدارة وصول المبلغ قبل تفعيل الحساب.</p>}
      <label>رفع صورة الحوالة (JPG / PNG / WEBP)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={uploadReceipt} disabled={busy}/></label>
      <button className="secondary full" onClick={checkStatus} disabled={busy}><RefreshCw size={16}/> تحديث حالة الطلب</button>
      {status && <div className="registration-info"><b>حالة الطلب</b><span>الدفع: {status.paid ? "مسجل كمدفوع" : "غير مؤكد"}</span><span>المعالجة: {status.processed ? "تم الاعتماد" : "بانتظار الإدارة"}</span></div>}
      <p className="muted">{message}</p>
      {status?.processed && <button className="primary full" onClick={onBack}>العودة لتسجيل الدخول</button>}
    </div>}
    {error && <div className="alert error"><AlertTriangle size={17}/>{error}</div>}
    <button className="text-btn full" onClick={onBack}>العودة إلى تسجيل الدخول</button>
  </div></main>;
}

function Login({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const body = new URLSearchParams({ username, password });
      const response = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "تعذر تسجيل الدخول");
      if (!["admin", "client"].includes(data.role)) throw new Error("نوع الحساب غير مدعوم.");
      onLogin(data.access_token, data.username, data.role);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  if (mode === "register") return <Registration onBack={() => setMode("login")} />;
  return <main className="login-shell">
    <div className="login-card">
      <div className="brand-mark"><Wifi size={28}/></div>
      <p className="eyebrow">SMARTNET CONTROL CENTER</p>
      <h1>إدارة الشبكة بوضوح</h1>
      <p className="muted">سجّل الدخول بحساب المدير أو حساب المشترك.</p>
      <form onSubmit={submit} className="form-stack">
        <label>اسم المستخدم<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" required /></label>
        <label>كلمة المرور<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" required /></label>
        {error && <div className="alert error"><AlertTriangle size={17}/>{error}</div>}
        <button className="primary full" disabled={busy}>{busy ? "جارٍ الدخول..." : "تسجيل الدخول"}</button>
      </form>
      <button className="text-btn full" onClick={() => setMode("register")}>إنشاء اشتراك عميل جديد</button>
      <p className="tiny muted">تأكد من ضبط VITE_API_BASE_URL وتشغيل خادم SmartNet.</p>
    </div>
  </main>;
}

function Stat({ icon: Icon, label, value, note }) {
  return <div className="stat-card">
    <div className="stat-icon"><Icon size={20}/></div>
    <div><span className="muted">{label}</span><strong>{value ?? "—"}</strong><small className="muted">{note}</small></div>
  </div>;
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("smartnet_token") || "");
  const [username, setUsername] = useState(() => sessionStorage.getItem("smartnet_user") || "");
  const [role, setRole] = useState(() => sessionStorage.getItem("smartnet_role") || "");
  const [page, setPage] = useState("overview");
  const [mobileNav, setMobileNav] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [health, setHealth] = useState(null);
  const [router, setRouter] = useState(null);
  const [users, setUsers] = useState([]);
  const [batches, setBatches] = useState([]);
  const [clients, setClients] = useState([]);
  const [registrations, setRegistrations] = useState([]);
  const [userProfile, setUserProfile] = useState(null);
  const [chatQuota, setChatQuota] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatDraft, setChatDraft] = useState("");
  const [sendingChat, setSendingChat] = useState(false);
  const [search, setSearch] = useState("");
  const [count, setCount] = useState(20);
  const [profile, setProfile] = useState("1 Day");
  const [generating, setGenerating] = useState(false);

  const logout = useCallback(() => {
    sessionStorage.removeItem("smartnet_token");
    sessionStorage.removeItem("smartnet_user");
    sessionStorage.removeItem("smartnet_role");
    setToken(""); setUsername(""); setRole("");
  }, []);

  const loadAll = useCallback(async () => {
    if (!token || !role) return;
    setBusy(true); setError("");
    if (role === "admin") {
      const results = await Promise.allSettled([
        api("/api/health/ready", token),
        api("/mikrotik/status", token),
        api("/mikrotik/users", token),
        api("/cards/batches", token),
        api("/auth/clients", token),
        api("/auth/registrations", token),
      ]);
      if (results[0].status === "fulfilled") setHealth(results[0].value);
      if (results[1].status === "fulfilled") setRouter(results[1].value);
      if (results[2].status === "fulfilled") setUsers(results[2].value);
      if (results[3].status === "fulfilled") setBatches(results[3].value);
      if (results[4].status === "fulfilled") setClients(results[4].value);
      if (results[5].status === "fulfilled") setRegistrations(results[5].value);
      const failed = results.filter(x => x.status === "rejected");
      if (failed.length) setError(failed.map(x => x.reason?.message).join(" — "));
    } else {
      const results = await Promise.allSettled([
        api("/auth/me", token),
        api("/client/chat/quota", token),
        api(`/client/chat?username=${encodeURIComponent(username)}`, token),
        api("/mikrotik/status", token),
      ]);
      if (results[0].status === "fulfilled") setUserProfile(results[0].value);
      if (results[1].status === "fulfilled") setChatQuota(results[1].value);
      if (results[2].status === "fulfilled") setChatMessages(results[2].value);
      if (results[3].status === "fulfilled") setRouter(results[3].value);
      setHealth(null); setUsers([]); setBatches([]); setClients([]); setRegistrations([]);
      const failed = results.filter(x => x.status === "rejected");
      if (failed.length) setError(failed.map(x => x.reason?.message).join(" — "));
    }
    setBusy(false);
  }, [token, role, username]);

  useEffect(() => { if (token) loadAll(); }, [token, loadAll]);
  useEffect(() => { if (!notice) return; const id = setTimeout(()=>setNotice(""), 4500); return ()=>clearTimeout(id); }, [notice]);

  function handleLogin(newToken, newUser, newRole) {
    sessionStorage.setItem("smartnet_token", newToken);
    sessionStorage.setItem("smartnet_user", newUser);
    sessionStorage.setItem("smartnet_role", newRole);
    setToken(newToken); setUsername(newUser); setRole(newRole); setPage("overview");
  }

  async function action(fn, success) {
    setError(""); setNotice("");
    try { await fn(); setNotice(success); await loadAll(); }
    catch (err) { setError(err.message); }
  }

  async function generateCards(event) {
    event.preventDefault(); setGenerating(true);
    await action(async () => {
      const batch = await api("/cards/generate", token, {
        method: "POST",
        body: JSON.stringify({ count: Number(count), profile, length: 8, hide_password: false }),
      });
      const blob = await api(`/cards/${batch.id}/pdf`, token);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `smartnet_batch_${batch.id}.pdf`; a.click();
      URL.revokeObjectURL(url);
    }, "تم إنشاء الدفعة وتنزيل ملف PDF.");
    setGenerating(false);
  }

  async function downloadReceipt(regId) {
    try {
      const blob = await api(`/auth/registrations/${regId}/receipt`, token);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setTimeout(()=>URL.revokeObjectURL(url), 60000);
    } catch (err) { setError(err.message); }
  }

  async function reboot() {
    if (!window.confirm("هل أنت متأكد من إعادة تشغيل الراوتر؟ ستنقطع الشبكة مؤقتاً.")) return;
    await action(()=>api("/mikrotik/reboot", token, { method: "POST" }), "تم إرسال أمر إعادة التشغيل.");
  }

  async function changePassword() {
    const current_password = window.prompt("أدخل كلمة المرور الحالية:");
    if (current_password === null) return;
    const new_password = window.prompt("أدخل كلمة المرور الجديدة (10 أحرف على الأقل):");
    if (new_password === null) return;
    const confirmation = window.prompt("أعد إدخال كلمة المرور الجديدة:");
    if (confirmation === null) return;
    if (new_password !== confirmation) {
      setError("كلمتا المرور الجديدتان غير متطابقتين.");
      return;
    }
    await action(() => api("/auth/change-password", token, {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }), "تم تغيير كلمة المرور. احتفظ بها وسجّل الدخول بها في المرة القادمة.");
  }



  async function sendChat(event) {
    event.preventDefault();
    const message = chatDraft.trim();
    if (!message || sendingChat) return;
    setSendingChat(true); setError("");
    try {
      await api("/client/chat", token, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      setChatDraft("");
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setSendingChat(false);
    }
  }

  const isAdmin = role === "admin";
  const navItems = isAdmin ? nav : clientNav;
  const activeClients = clients.filter(c=>c.is_active).length;
  const pending = registrations.filter(r=>!r.processed).length;
  const filteredClients = useMemo(() => clients.filter(c => c.username.toLowerCase().includes(search.toLowerCase())), [clients, search]);

  if (!token || !role) return <Login onLogin={handleLogin}/>;

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
      <div className="sidebar-brand"><div className="brand-mark small"><Wifi size={21}/></div><div><b>SmartNet</b><small>Network Console</small></div><button className="icon-btn mobile-close" onClick={()=>setMobileNav(false)}><X/></button></div>
      <div className="nav-label">{isAdmin ? "الإدارة" : "حساب المشترك"}</div>
      <nav>{navItems.map(item=><button key={item.id} className={page===item.id?"nav-item active":"nav-item"} onClick={()=>{setPage(item.id);setMobileNav(false);}}><item.icon size={18}/><span>{item.label}</span></button>)}</nav>
      <div className="sidebar-bottom">
        <div className="secure-note"><ShieldCheck size={17}/><span>اتصال محمي<br/><small>{isAdmin ? "صلاحيات المدير" : "حساب المشترك"}</small></span></div>
        <button className="nav-item" onClick={changePassword}><LockKeyhole size={18}/>تغيير كلمة المرور</button>
        <button className="nav-item logout" onClick={logout}><LogOut size={18}/>تسجيل الخروج</button>
      </div>
    </aside>
    {mobileNav && <button className="nav-scrim" aria-label="إغلاق القائمة" onClick={()=>setMobileNav(false)}/>}
    <main className="main">
      <header className="topbar">
        <div className="topbar-title"><button className="icon-btn mobile-menu" onClick={()=>setMobileNav(true)}><Menu/></button><div><span className="eyebrow">SMARTNET / CONTROL</span><h1>{navItems.find(n=>n.id===page)?.label}</h1></div></div>
        <div className="topbar-actions"><span className="user-chip"><span className="online-dot"/>{username}</span><button className="icon-btn" onClick={loadAll} title="تحديث البيانات"><RefreshCw size={18} className={busy?"spin":""}/></button></div>
      </header>
      <div className="content">
        {error && <div className="alert error"><AlertTriangle size={17}/><span>{error}</span><button onClick={()=>setError("")}><X size={16}/></button></div>}
        {notice && <div className="alert success"><CheckCircle2 size={17}/>{notice}</div>}
        {page==="overview" && (isAdmin ? <section className="page-section">
          <div className="welcome-row"><div><h2>مرحباً، {username}</h2><p className="muted">إليك ملخص حالة الشبكة ونشاط الاشتراكات.</p></div><span className={health?.status==="ready"?"status-pill good":"status-pill warn"}><span className="online-dot"/>{health?.status==="ready"?"الخادم جاهز":"تحقق من الاتصال"}</span></div>
          <div className="stats-grid">
            <Stat icon={Users} label="المشتركون النشطون" value={activeClients} note={`إجمالي ${clients.length} مشترك`}/>
            <Stat icon={Wifi} label="المستخدمون المتصلون" value={users.length} note="جلسات Hotspot الحالية"/>
            <Stat icon={Layers3} label="دفعات الكروت" value={batches.length} note="دفعات محفوظة"/>
            <Stat icon={CreditCard} label="طلبات بانتظار المراجعة" value={pending} note="تحتاج قرار الإدارة"/>
          </div>
          <div className="two-col">
            <div className="panel"><div className="panel-head"><h3><Router size={18}/> حالة الراوتر</h3><span className="muted">{router?.version || "—"}</span></div>
              <div className="detail-grid"><div><small>اسم اللوحة</small><b>{router?.["board-name"] || router?.board_name || "—"}</b></div><div><small>وقت التشغيل</small><b>{router?.uptime || "—"}</b></div><div><small>استخدام CPU</small><b>{router?.["cpu-load"] ?? router?.cpu_load ?? "—"}%</b></div><div><small>البيئة</small><b>{health?.environment || "—"}</b></div></div>
            </div>
            <div className="panel"><div className="panel-head"><h3><ShieldCheck size={18}/> جاهزية التشغيل</h3></div>
              <ul className="check-list"><li><span className={health?.database==="connected"?"check-dot":"bad-dot"}/><span>قاعدة البيانات</span><b>{health?.database || "غير متاح"}</b></li><li><span className={health?.mikrotik_demo_mode?"warn-dot":"check-dot"}/><span>تكامل MikroTik</span><b>{health?.mikrotik_demo_mode?"وضع تجريبي":"وضع حقيقي"}</b></li><li><span className={health?.payment_demo_mode?"warn-dot":"check-dot"}/><span>الدفع</span><b>{health?.payment_demo_mode?"وضع تجريبي":"وضع حقيقي"}</b></li></ul>
            </div>
          </div>
          <div className="panel"><div className="panel-head"><h3>آخر دفعات الكروت</h3><button className="text-btn" onClick={()=>setPage("cards")}>عرض الكل</button></div><BatchTable batches={batches.slice(0,5)} onDownload={async id=>{try{const blob=await api(`/cards/${id}/pdf`,token);const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=`smartnet_batch_${id}.pdf`;a.click();URL.revokeObjectURL(url);}catch(e){setError(e.message);}}}/></div>
        </section> : <section className="page-section">
          <div className="welcome-row"><div><h2>مرحباً، {username}</h2><p className="muted">تابع باقتك وحالة اشتراكك واستخدم المساعد الذكي للدعم.</p></div><span className={userProfile?.is_active ? "status-pill good" : "status-pill warn"}>{userProfile?.is_active ? "الحساب نشط" : "الحساب غير نشط"}</span></div>
          <div className="stats-grid">
            <Stat icon={CreditCard} label="الباقة الحالية" value={userProfile?.plan || "—"} note="نوع الاشتراك"/>
            <Stat icon={CalendarClock} label="تاريخ الانتهاء" value={userProfile?.subscription_expires ? new Date(userProfile.subscription_expires).toLocaleDateString("ar") : "—"} note="موعد انتهاء الاشتراك"/>
            <Stat icon={MessageCircle} label="المتبقي من رسائل اليوم" value={chatQuota?.unlimited ? "∞" : (chatQuota?.remaining_today ?? "—")} note={chatQuota?.daily_limit ? `${chatQuota.used_today}/${chatQuota.daily_limit} مستخدمة` : "حسب باقتك"}/>
            <Stat icon={Wifi} label="الراوتر" value={router?.version || "متصل عبر الإدارة"} note="حالة الشبكة"/>
          </div>
          <div className="two-col">
            <div className="panel"><div className="panel-head"><h3><ShieldCheck size={18}/> صلاحيات حسابك</h3></div>
              <ul className="check-list">
                <li><span className={userProfile?.can_manage_cards ? "check-dot" : "warn-dot"}/><span>إدارة الكروت</span><b>{userProfile?.can_manage_cards ? "متاحة" : "غير متاحة"}</b></li>
                <li><span className={userProfile?.can_manage_users ? "check-dot" : "warn-dot"}/><span>إدارة المستخدمين</span><b>{userProfile?.can_manage_users ? "متاحة" : "غير متاحة"}</b></li>
                <li><span className={userProfile?.can_reboot_network ? "check-dot" : "warn-dot"}/><span>إعادة تشغيل الشبكة</span><b>{userProfile?.can_reboot_network ? "متاحة" : "غير متاحة"}</b></li>
              </ul>
            </div>
            <div className="panel"><div className="panel-head"><h3><MessageCircle size={18}/> الدعم الذكي</h3></div>
              <p className="muted">استخدم المساعد للاستفسار عن باقتك أو مشاكل الاتصال أو طلب الدعم.</p>
              <button className="primary full" onClick={()=>setPage("chat")}>فتح المساعد الذكي</button>
            </div>
          </div>
        </section>)}
        {page==="chat" && !isAdmin && <section className="page-section">
          <div className="section-intro"><div><h2>المساعد الذكي والدعم</h2><p className="muted">محادثتك خاصة بحسابك، وتُحفظ للرجوع إليها.</p></div><span className="status-pill good">{chatQuota?.unlimited ? "رسائل غير محدودة" : `المتبقي: ${chatQuota?.remaining_today ?? "—"}`}</span></div>
          <div className="panel chat-panel">
            <div className="chat-messages">
              {chatMessages.map(item=><div key={item.id} className={item.sender==="client"?"chat-row own":"chat-row"}>
                <div className="chat-avatar">{item.sender==="client"?"أنت":"SN"}</div>
                <div className="chat-content"><small>{item.sender==="client"?"أنت":"مساعد SmartNet"} · {item.created_at ? new Date(item.created_at).toLocaleString("ar") : ""}</small><p>{item.message}</p></div>
              </div>)}
              {!chatMessages.length && <Empty text="ابدأ المحادثة بكتابة سؤالك عن الشبكة أو الاشتراك."/>}
            </div>
            <form className="chat-compose" onSubmit={sendChat}>
              <input value={chatDraft} onChange={e=>setChatDraft(e.target.value)} placeholder="اكتب رسالتك هنا..." maxLength={1500} required/>
              <button className="primary" disabled={sendingChat || !chatDraft.trim()}>{sendingChat?"جارٍ الإرسال...":"إرسال"}</button>
            </form>
          </div>
        </section>}
        {page==="router" && <section className="page-section">
          <div className="section-intro"><div><h2>الراوتر والمستخدمون</h2><p className="muted">إدارة جلسات Hotspot ومراقبة حالة MikroTik.</p></div><button className="danger-btn" onClick={reboot}><Power size={17}/> إعادة تشغيل الراوتر</button></div>
          <div className="stats-grid compact"><Stat icon={Activity} label="المستخدمون النشطون" value={users.length}/><Stat icon={Router} label="الموديل" value={router?.["board-name"] || router?.board_name || "—"}/><Stat icon={Activity} label="CPU" value={router?.["cpu-load"] ?? router?.cpu_load ?? "—"}/></div>
          <div className="panel"><div className="panel-head"><h3>الجلسات النشطة</h3><button className="icon-btn" onClick={loadAll}><RefreshCw size={17}/></button></div>
            {users.length ? <div className="table-wrap"><table><thead><tr><th>المستخدم</th><th>IP</th><th>MAC</th><th>مدة الاتصال</th><th>الإجراء</th></tr></thead><tbody>{users.map((u,i)=><tr key={u.id||u.username||i}><td className="mono">{u.user||u.name||u.username||"—"}</td><td className="mono">{u.address||u.ip||"—"}</td><td className="mono">{u["mac-address"]||u.mac||"—"}</td><td>{u.uptime||"—"}</td><td><button className="table-action danger" onClick={()=>action(()=>api(`/mikrotik/users/${encodeURIComponent(u.user||u.name||u.username)}/disconnect`,token,{method:"POST"}),"تم إرسال طلب فصل المستخدم.")}>فصل</button></td></tr>)}</tbody></table></div>:<Empty text="لا توجد جلسات أو تعذر جلب المستخدمين."/>}
          </div>
        </section>}
        {page==="cards" && <section className="page-section">
          <div className="section-intro"><div><h2>إصدار كروت Hotspot</h2><p className="muted">إنشاء حسابات على الراوتر وإنتاج ورقة PDF للطباعة.</p></div></div>
          <div className="panel generator"><div><h3><Plus size={18}/> دفعة جديدة</h3><p className="muted">تأكد من وجود Profile بنفس الاسم على جهاز MikroTik قبل التوليد.</p></div>
            <form className="generate-form" onSubmit={generateCards}><label>عدد الكروت<input type="number" min="1" max="1000" value={count} onChange={e=>setCount(e.target.value)} required/></label><label>Profile<select value={profile} onChange={e=>setProfile(e.target.value)}><option>1 Day</option><option>1 Week</option><option>1 Month</option></select></label><button className="primary" disabled={generating}><FileDown size={17}/>{generating?"جارٍ التوليد...":"توليد وتنزيل PDF"}</button></form>
          </div>
          <div className="panel"><div className="panel-head"><h3>سجل الدفعات</h3><span className="muted">{batches.length} دفعة</span></div><BatchTable batches={batches} onDownload={async id=>{try{const blob=await api(`/cards/${id}/pdf`,token);const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=`smartnet_batch_${id}.pdf`;a.click();URL.revokeObjectURL(url);}catch(e){setError(e.message);}}}/></div>
        </section>}
        {page==="clients" && <section className="page-section">
          <div className="section-intro"><div><h2>المشتركون</h2><p className="muted">عرض حسابات العملاء ومدد صلاحيتها وإدارتها.</p></div><div className="search-box"><Search size={17}/><input placeholder="ابحث باسم المستخدم" value={search} onChange={e=>setSearch(e.target.value)}/></div></div>
          <div className="panel"><div className="table-wrap"><table><thead><tr><th>المستخدم</th><th>الباقة</th><th>الحالة</th><th>انتهاء الاشتراك</th><th>إجراءات</th></tr></thead><tbody>{filteredClients.map(c=><tr key={c.id}><td className="mono">{c.username}</td><td><span className="plan-tag">{c.plan||"شهري"}</span></td><td><span className={c.is_active?"status-pill good":"status-pill warn"}>{c.is_active?"نشط":"معطل"}</span></td><td>{c.subscription_expires?new Date(c.subscription_expires).toLocaleString("ar"): "غير محدد"}</td><td><div className="row-actions"><button className="table-action" onClick={()=>{const days=window.prompt("عدد أيام التمديد؟","30");if(days && Number(days)>0) action(()=>api(`/auth/clients/${c.id}/extend?days=${Number(days)}`,token,{method:"POST"}),"تم تمديد الاشتراك.");}}>تمديد</button><button className="table-action danger" onClick={()=>{if(window.confirm("تعطيل هذا المشترك؟")) action(()=>api(`/auth/clients/${c.id}/deactivate`,token,{method:"POST"}),"تم تعطيل المشترك.");}}>تعطيل</button></div></td></tr>)}</tbody></table></div>{!filteredClients.length&&<Empty text="لا توجد نتائج مطابقة."/>}</div>
        </section>}
        {page==="payments" && <section className="page-section">
          <div className="section-intro"><div><h2>طلبات الاشتراك والدفع</h2><p className="muted">راجع إشعار الدفع أو صورة الحوالة قبل اعتماد حساب العميل.</p></div></div>
          <div className="alert warning"><AlertTriangle size={18}/> رفع صورة الحوالة لا يؤكد الدفع تلقائياً. تحقق من التحويل في حسابك أو بوابة الدفع قبل الموافقة.</div>
          <div className="panel"><div className="table-wrap"><table><thead><tr><th>رقم الطلب</th><th>المستخدم</th><th>الباقة</th><th>المبلغ</th><th>الدفع</th><th>الحوالة</th><th>الإجراء</th></tr></thead><tbody>{registrations.map(r=><tr key={r.id}><td>#{r.id}</td><td className="mono">{r.username}</td><td>{r.plan}</td><td>{r.price} USD</td><td><span className={r.paid?"status-pill good":"status-pill warn"}>{r.paid?"مسجل كمدفوع":"بانتظار الدفع"}</span></td><td>{r.receipt_image?<button className="table-action" onClick={()=>downloadReceipt(r.id)}><Eye size={15}/> عرض</button>:"—"}</td><td><div className="row-actions">
            {!r.processed&&!r.paid&&<button className="table-action" onClick={()=>{if(window.confirm("هل تحققت من وصول المبلغ فعلياً إلى حسابك وبنفس القيمة والعملة؟ سيُسجل قرار التحقق باسمك.")) action(()=>api(`/auth/registrations/${r.id}/verify-manual`,token,{method:"POST"}),"تم تأكيد وصول المبلغ. أصبح الطلب جاهزاً للاعتماد.")}}>تأكيد وصول المبلغ</button>}
            {!r.processed&&r.paid&&<button className="approve-btn" onClick={()=>{if(window.confirm("تفعيل حساب العميل الآن؟")) action(()=>api(`/auth/registrations/${r.id}/approve`,token,{method:"POST"}),"تم اعتماد الاشتراك.")}}><CheckCircle2 size={15}/> اعتماد الاشتراك</button>}
            {r.processed&&<span className="muted">معتمد</span>}
          </div></td></tr>)}</tbody></table></div>{!registrations.length&&<Empty text="لا توجد طلبات تسجيل حالياً."/>}</div>
        </section>}
        <footer className="footer"><span>SmartNet v1.1.0</span><span>لوحة إدارة الشبكة</span></footer>
      </div>
    </main>
  </div>;
}

function BatchTable({ batches, onDownload }) {
  if (!batches?.length) return <Empty text="لا توجد دفعات كروت حتى الآن." />;
  return <div className="table-wrap"><table><thead><tr><th>رقم الدفعة</th><th>Profile</th><th>عدد الكروت</th><th>تاريخ الإنشاء</th><th>الملف</th></tr></thead><tbody>{batches.map(b=><tr key={b.id}><td>#{b.id}</td><td>{b.profile}</td><td>{b.count}</td><td>{b.created_at?new Date(b.created_at).toLocaleString("ar"):"—"}</td><td><button className="table-action" onClick={()=>onDownload(b.id)}><FileDown size={15}/> PDF</button></td></tr>)}</tbody></table></div>;
}
function Empty({ text }) { return <div className="empty-state"><Layers3 size={25}/><span>{text}</span></div>; }

export default App;
