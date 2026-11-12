<div dir="rtl">

# SmartNet — نظام إدارة شبكة Hotspot

منصة عربية لإدارة اشتراكات Hotspot وشبكات MikroTik، توليد كروت المستخدمين وملفات PDF، مراجعة الحوالات، ودعم العملاء. تتضمن API مبنياً بـFastAPI، ولوحة React، وبوت Telegram اختياري، ومساعد تشخيص يعتمد قاعدة معرفة تشغيلية موثوقة.

## المكونات

- **Backend:** Python 3.11+ وFastAPI وSQLAlchemy Async.
- **Frontend:** React 18 وVite 8 بواجهة عربية RTL.
- **Database:** MariaDB 11.4 LTS في الإنتاج؛ SQLite للتطوير والاختبارات المحلية فقط.
- **Runtime:** Podman وPodman Compose باستخدام ملفات Containerfile.
- **HTTPS:** Caddy (اختياري عبر profile باسم edge).
- **Router:** MikroTik RouterOS عبر API-SSL مع التحقق من الشهادة وحساب مراقبة للقراءة فقط وحساب تشغيل منفصل للكتابة.
- **AI:** مساعد OpenAI اختياري، وكيل تشخيص يعتمد ملفات Knowledge Base داخل المستودع.
- **Monitoring:** عامل مراقبة للقراءة فقط، وسجل snapshots وتنبيهات وPrometheus metrics.

## التشغيل المحلي للتطوير

### Backend

من مجلد المشروع:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item ..\.env.example .env
```

اترك الإعدادات المحلية على `ENVIRONMENT=development` و`DATABASE_BACKEND=sqlite` و`MIKROTIK_DEMO_MODE=true` أثناء التطوير فقط.

```powershell
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

الوثائق: `http://127.0.0.1:8000/docs`

### Frontend

في نافذة PowerShell أخرى:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

الواجهة: `http://localhost:5173`

### الاختبارات المحلية

```powershell
cd backend
python -m pytest -q tests
```

ومن مجلد `frontend`:

```powershell
npm run build
npx playwright install chromium
npm run test:e2e
```

فحوص الاعتماديات:

```powershell
cd frontend
npm audit --audit-level=moderate
cd ..\backend
pip-audit -r requirements.txt
```

## تشغيل MariaDB وPodman

SmartNet لا يعتمد Docker أو PostgreSQL. قاعدة البيانات الإنتاجية هي MariaDB، والحاويات تعمل بواسطة Podman.

1. ثبّت Podman Desktop أو Podman CLI ووفّر Compose provider (مثل podman-compose). على Windows شغّل Podman Machine.
2. انسخ `.env.example` إلى `.env` في جذر المشروع.
3. غيّر جميع كلمات المرور والأسرار، واجعل `DATABASE_BACKEND=mariadb`، وأدخل قيم MariaDB، ومعلومات HTTPS والراوتر الحقيقية.
4. لا تستخدم بيانات المثال أو إعدادات demo في الإنتاج.

تشغيل قاعدة البيانات والواجهة الخلفية والواجهة على شبكة Podman:

```bash
podman-compose -f podman-compose.yml up -d --build mariadb backend frontend
```

يُتاح الويب محلياً على `http://127.0.0.1:8080`، وتُربط MariaDB محلياً فقط على المنفذ `127.0.0.1:3307`. لا تُفتح قاعدة البيانات على الإنترنت.

لتفعيل HTTPS عبر Caddy بعد توجيه DNS للنطاق إلى الخادم وضبط `DOMAIN` و`ACME_EMAIL`:

```bash
podman-compose -f podman-compose.yml --profile edge up -d --build
```

لبوت Telegram (اختياري):

```bash
podman-compose -f podman-compose.yml --profile telegram up -d --build telegram-bot
```

### Prometheus للمراقبة المستمرة (اختياري)

يعمل Prometheus داخل شبكة Podman الخاصة، ولا يُنشر على الإنترنت. أضف قيمة عشوائية قوية إلى `METRICS_TOKEN` داخل `.env` (32 حرفاً على الأقل)، ثم أنشئ ملف الرمز المطابق دون إضافته إلى Git:

```bash
set -a
. ./.env
set +a
install -d -m 700 secrets
umask 077
printf '%s' "$METRICS_TOKEN" > secrets/metrics-token
podman-compose -f podman-compose.yml --profile monitoring up -d prometheus
```

واجهة Prometheus متاحة محلياً فقط على `http://127.0.0.1:9090`. نقطة `/api/metrics` في SmartNet تقبل هذا الرمز فقط، ولا تُعرَض عبر واجهة العميل أو Caddy.

يمكن استخدام `podman compose` بدلاً من `podman-compose` عندما يكون Compose provider مضبوطاً في Podman Desktop. راجع `docs/PRODUCTION_RUNBOOK.md` قبل النشر.

## الدفع اليدوي والتسويات

وضع الدفع الافتراضي في الإنتاج هو `PAYMENT_PROVIDER_MODE=manual`. العميل ينشئ طلباً ويرفع صورة التحويل. يراجع المسؤول التحويل في محفظته أو حسابه الفعلي، ويدخل المبلغ والعملة ومرجع الحوالة. بعد التحقق المالي المنفصل، يعتمد المسؤول الاشتراك. الصورة وحدها لا تثبت الدفع ولا تنشط العميل.

المسار `GET /auth/payments/reconciliation` يعرض حالات عدم الاتساق. لا يُعد Gateway mode تكاملاً فعلياً لمزود الدفع حتى يُضاف Adapter خاص بالمزود يتحقق من التوقيع ومرجع الحدث والمبلغ والعملة وفق وثائقه الرسمية.

## وكلاء الذكاء الاصطناعي

- **Network Monitor:** يقرأ حالة الراوتر وعدد الجلسات والأداء، ويحفظ snapshots والتنبيهات. لا يمتلك وظائف تعديل RouterOS.
- **Diagnostics Agent:** يسترجع إرشادات من `backend/knowledge_base` ثم يجيب بمصادرها. لا ينفذ أوامر.
- **Customer Assistant:** يجيب عن الاشتراك والدعم، وتُحال أسئلة أعطال الشبكة إلى قاعدة المعرفة.
- **Network Operations Approval:** طلب فصل مستخدم أو إعادة تشغيل الراوتر يُسجّل ويُراجع ويُنفّذ كخطوات منفصلة مع سجل تدقيق.

تفعيل مراقبة الشبكة يتطلب إعداد `NETWORK_MONITOR_ENABLED=true` وتوصيل MikroTik حقيقي في شبكة إدارة خاصة.

## الاختبارات وموثوقية النشر

GitHub Actions يشغّل فحوص Backend وواجهة React وPlaywright، بالإضافة إلى تدقيق الاعتماديات واختبارات MariaDB/Podman والنسخ الاحتياطي والاستعادة وجمع Prometheus للمقاييس. نتائج CI لا تحل محل اختبار القبول على راوتر حقيقي أو حساب دفع حي.

## وثائق إضافية

- `SECURITY.md` — متطلبات الأمان وبوابات الإنتاج.
- `docs/PRODUCTION_RUNBOOK.md` — خطوات النشر والنسخ الاحتياطي واختبار MikroTik.
- `backend/knowledge_base/` — مصادر التشغيل والتشخيص.

</div>
