<div dir="rtl">

# SmartNet — نظام إدارة شبكات MikroTik وHotspot

نظام لإدارة شبكات Hotspot من خلال واجهة عربية، وواجهة API، وبوت Telegram اختياري. يدعم إنشاء كروت المشتركين وملفات PDF، متابعة المستخدمين، إدارة الاشتراكات وطلباتها.

> **حالة المشروع:** تم استكمال بنية تشغيل وإدارة أولية على فرع `production-readiness`. التشغيل التجاري الفعلي يظل مشروطاً بإعداد بيانات مزود الدفع والراوتر الحقيقي وإجراء اختبارات القبول الموضحة في [دليل الإنتاج](docs/PRODUCTION_RUNBOOK.md).

## المكونات

- **Backend:** Python 3.11+ وFastAPI وSQLAlchemy async.
- **Admin Web:** React 18 + Vite، واجهة عربية RTL.
- **Database:** SQLite للتطوير المحلي، وPostgreSQL للإنتاج.
- **MikroTik:** وضع تجريبي محلي أو اتصال RouterOS API حقيقي.
- **Subscriptions:** تسجيل طلبات، رفع إيصال خاص، مراجعة واعتماد إداري.
- **PDF:** إصدار أوراق كروت Hotspot.
- **Telegram:** بوت إداري اختياري ومقيد بقائمة IDs.
- **Operations:** Alembic migrations وDocker Compose وGitHub Actions.

## التشغيل المحلي على Windows

### 1. المتطلبات

- Python 3.11 أو أحدث.
- Node.js 20 أو أحدث.
- npm.
- لا تحتاج إلى MikroTik أو بوابة دفع لتشغيل وضع التطوير التجريبي.

### 2. إعداد Backend

من مجلد المشروع:

```powershell
cd backend
Copy-Item ..\.env.example .env
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

عند أول تشغيل ينشئ النظام حساب المدير الأول من `DASHBOARD_USERNAME` و`DASHBOARD_PASSWORD` الموجودين في ملف `backend/.env`. بعد الدخول غيّر كلمة المرور من زر «تغيير كلمة المرور» في القائمة الجانبية. مسار `/auth/change-password` يطلب كلمة المرور الحالية، وتُحفظ الجديدة مجزأة. لا تستخدم قيمة المثال في خادم عام.

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health`
- Readiness: `http://127.0.0.1:8000/api/health/ready`

### 3. إعداد الواجهة

افتح نافذة PowerShell أخرى:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

افتح `http://localhost:5173`.

تحتوي الواجهة على تسجيل دخول المدير، وإنشاء طلب اشتراك عميل، ولوحة معلومات الشبكة، وإدارة الراوتر والمستخدمين، وتوليد الكروت، وإدارة المشتركين، ومراجعة طلبات الدفع.

### 4. الاختبارات

من مجلد `backend` مع تفعيل البيئة الافتراضية:

```powershell
python -m compileall -q .
python -m pytest -q
```

الاختبارات الآلية تستخدم SQLite داخل الذاكرة، ولا تتصل براوتر حقيقي ولا ترسل مدفوعات أو رسائل Telegram.

## إعداد MikroTik حقيقي

في `backend/.env` غيّر القيم التالية بعد تجهيز الراوتر:

```env
MIKROTIK_DEMO_MODE=false
MIKROTIK_HOST=عنوان-الراوتر-الخاص
MIKROTIK_USERNAME=حساب-api-مخصص
MIKROTIK_PASSWORD=كلمة-مرور-قوية
MIKROTIK_PORT=8728
```

أنشئ حساباً محدود الصلاحيات على RouterOS، واسمح بالوصول من خادم SmartNet فقط عبر VPN أو شبكة خاصة. لا تفتح منفذ RouterOS API على الإنترنت العام. يجب إنشاء Profiles المطلوبة مسبقاً على الراوتر؛ أسماء مثل `1 Day` و`1 Week` في الواجهة لا تنشئ Profiles تلقائياً.

عند تفعيل الوضع الحقيقي لا يقوم النظام بعرض بيانات Demo عند فشل الاتصال؛ بل يعيد خطأ واضحاً حتى لا يتم الخلط بين بيانات وهمية وحالة الشبكة الحقيقية.

## التسجيل والدفع والاشتراكات

1. يسجل العميل من الواجهة العامة ويحصل على رقم طلب ورمز خاص لمتابعته.
2. يستخدم العميل بوابة الدفع الفعلية أو يرفع صورة حوالة للمراجعة.
3. صورة الحوالة لا تعتبر إثبات دفع ولا تفعّل الحساب تلقائياً.
4. إشعار الدفع الموثوق يضع الطلب في حالة مدفوع بانتظار مراجعة الإدارة.
5. المدير يتحقق من وصول المبلغ ثم يعتمد الطلب من لوحة الإدارة.
6. لا يصبح الحساب فعالاً إلا بعد موافقة الإدارة.

### تكامل الدفع

اختر `PAYMENT_PROVIDER_MODE=manual` للتحويلات اليدوية عبر المحافظ أو الحساب البنكي، أو `PAYMENT_PROVIDER_MODE=gateway` عند بناء Adapter وربط بوابة دفع فعلية. في وضع manual يرفع العميل الإيصال، ثم يؤكد المدير وصول المبلغ من لوحة الإدارة، ثم يعتمد الاشتراك منفصلاً. في وضع gateway اضبط `PAYMENT_CHECKOUT_URL` وفق رابط مزود الدفع. نقطة `POST /auth/registrations/{id}/confirm` تستقبل إشعاراً موثوقاً عبر رأس `X-Webhook-Secret` ومعرف معاملة `payment_ref`.

**مهم:** هذه النقطة العامة لا تتحقق بنفسها من توقيع مزود خارجي أو مبلغ التسوية أو العملة أو تكرار Event ID. يجب بناء Adapter خاص بمزود الدفع المختار ليتحقق من التوقيع والمبلغ والعملة ورقم الفاتورة وحالة التسوية قبل استدعاء نقطة التأكيد. لا تعتبر المشروع مربوطاً ببوابة دفع حقيقية قبل تنفيذ واختبار ذلك الـ Adapter.

في التطوير فقط، يمكن استخدام زر الدفع التجريبي؛ لكنه لا يعتمد الحساب، بل يتركه بانتظار موافقة المدير. الدفع التجريبي ممنوع في وضع الإنتاج.

## Telegram Bot (اختياري)

أضف إلى ملف `backend/.env`:

```env
TELEGRAM_BOT_TOKEN=توكن-البوت
TELEGRAM_ADMIN_IDS=[123456789]
BOT_API_BASE_URL=http://127.0.0.1:8000
```

شغّل من مجلد `backend`:

```powershell
python -m bot.main_bot
```

الأوامر: `/start` و`/status` و`/users` و`/cards` و`/generate 20 1 Day` و`/stats`. البوت يرفض المستخدمين غير الموجودين في قائمة المديرين.

## تشغيل Docker للإنتاج

ملف `.env` في جذر المشروع يجب أن يحتوي على بيانات إنتاج حقيقية قبل تشغيل Compose. انسخ `.env.example` ثم اضبط:

- `ENVIRONMENT=production`.
- أسرار JWT وWebhook عشوائية منفصلة بطول 32 حرفاً أو أكثر.
- اسم مدير غير افتراضي وكلمة مرور قوية وفريدة.
- `POSTGRES_PASSWORD` فريد بطول 16 حرفاً على الأقل.
- بيانات PostgreSQL، بما فيها `POSTGRES_PASSWORD`.
- `PAYMENT_DEMO_MODE=false` و`MIKROTIK_DEMO_MODE=false`.
- في وضع gateway فقط: `PAYMENT_CHECKOUT_URL` الفعلي؛ في وضع manual تُراجع الحوالات يدوياً من لوحة الإدارة.
- `CORS_ORIGINS` كقائمة JSON لعناوين HTTPS الدقيقة.
- بيانات الراوتر الفعلي.

بعد استكمال القيم:

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

الواجهة متاحة افتراضياً على المنفذ 8080. ضع Reverse Proxy أمامها مع HTTPS وشهادة TLS. لتفعيل البوت الاختياري:

```powershell
docker compose --profile telegram up -d --build
```

تشغيل الإنتاج يرفض تلقائياً الإعدادات التجريبية، والأسرار الافتراضية، وSQLite، وعناوين CORS غير HTTPS.

## قاعدة البيانات والهجرات

يستخدم Docker أمر `alembic upgrade head` قبل بدء Backend. قاعدة البيانات المحلية SQLite تُنشأ تلقائياً وتُجرى لها ترقية توافقية عند التشغيل.

الهجرة الأولى هي Baseline للمخطط الحالي. قبل استخدام Alembic على قاعدة بيانات PostgreSQL قديمة أو تحتوي بيانات، خذ نسخة احتياطية وراجع [دليل الإنتاج](docs/PRODUCTION_RUNBOOK.md)؛ لا تطبقها على قاعدة بيانات غير مفحوصة.

## وثائق الأمان والتشغيل

- [SECURITY.md](SECURITY.md) — الأسرار، ملفات العملاء، الدفع، وحدود التكامل.
- [docs/PRODUCTION_RUNBOOK.md](docs/PRODUCTION_RUNBOOK.md) — خطوات التشغيل والتهيئة.
- [backend/tests/README.md](backend/tests/README.md) — تشغيل الاختبارات.

**تنبيه بيانات:** سبق أن احتوى المستودع على قاعدة SQLite وملفات إيصالات وملفات تشغيل مولدة. حذفها من النسخة الحالية لا يمحوها من تاريخ Git أو النسخ المتفرعة. يجب تدوير أي أسرار أو بيانات اعتماد يحتمل أنها كُشفت، ومراجعة تنظيف تاريخ Git عند الحاجة.

## الترخيص

MIT — راجع ملف الترخيص إذا تم إضافته إلى التوزيعة.

</div>
