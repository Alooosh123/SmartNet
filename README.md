<div dir="rtl">

# 🌐 SmartNet — نظام إدارة شبكة الهوت سبوت

<div align="center">

![SmartNet](https://img.shields.io/badge/SmartNet-v1.0.0-00d4aa?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react)
![MikroTik](https://img.shields.io/badge/MikroTik-RouterOS-003366?style=for-the-badge)

نظام متكامل لإدارة شبكات الهوت سبوت MikroTik مع بوت تيليجرام ولوحة تحكم عصرية

</div>

---

## 📋 نظرة عامة

**SmartNet** منصة احترافية لإدارة شبكات الإنترنت اللاسلكي (Hotspot) تتضمن:

- 🤖 **بوت تيليجرام** — توليد كروت الهوت سبوت، متابعة حالة الشبكة، إدارة المستخدمين
- ⚙️ **API خلفي (FastAPI)** — واجهة برمجية كاملة تغذّي لوحة التحكم
- 🖥️ **لوحة تحكم (React)** — داشبورد احترافي بتصميم عصري بالعربية
- 📄 **توليد PDF** — كروت هوت سبوت جاهزة للطباعة
- 🔒 **نظام صلاحيات** — JWT للوحة التحكم + قائمة مديرين للبوت

---

## 🏗️ هيكل المشروع

```
smartnet-project/
├── backend/                    # الواجهة الخلفية (Python)
│   ├── bot/                    # بوت تيليجرام
│   │   ├── handlers/           # معالجات الأوامر
│   │   ├── keyboards/          # الأزرار التفاعلية
│   │   └── main_bot.py         # تشغيل البوت
│   ├── api/                    # REST API
│   │   ├── routes/             # مسارات الـ API
│   │   └── controllers/        # المنطق البرمجي
│   ├── services/               # الخدمات المشتركة
│   │   ├── mikrotik_api.py     # التواصل مع الراوتر
│   │   ├── pdf_generator.py    # توليد ملفات PDF
│   │   └── auth_service.py     # التحقق والصلاحيات
│   ├── config/
│   │   └── settings.py         # إعدادات النظام
│   ├── database/
│   │   ├── models.py           # نماذج قاعدة البيانات
│   │   └── db_core.py          # الاتصال بقاعدة البيانات
│   ├── requirements.txt
│   └── app.py                  # نقطة الانطلاق
├── frontend/                   # لوحة التحكم (React + Vite)
│   ├── src/
│   │   ├── components/         # مكونات قابلة لإعادة الاستخدام
│   │   ├── pages/              # صفحات لوحة التحكم
│   │   ├── services/           # الاتصال بالـ API
│   │   └── App.jsx
│   └── package.json
├── .env.example                # نموذج المتغيرات البيئية
├── .gitignore
└── README.md
```

---

## ⚡ المتطلبات

| الأداة | الإصدار المطلوب |
|--------|----------------|
| Python | 3.11 أو أحدث |
| Node.js | 18 أو أحدث |
| npm | 9 أو أحدث |

---

## 🚀 التشغيل السريع

### 1. استنساخ المشروع

```bash
git clone https://github.com/your-username/smartnet.git
cd smartnet
```

### 2. إعداد المتغيرات البيئية

```bash
cp .env.example .env
# افتح .env وعدّل القيم المطلوبة
```

> **الحد الأدنى للتشغيل (وضع التجريب):**
> - أضف توكن البوت في `TELEGRAM_BOT_TOKEN`
> - أضف معرّف تيليجرام الخاص بك في `TELEGRAM_ADMIN_IDS`
> - اتركه `MIKROTIK_DEMO_MODE=True` للبيانات الوهمية

### 3. تشغيل الواجهة الخلفية

```bash
cd backend

# إنشاء بيئة افتراضية وتثبيت المكتبات
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

pip install -r requirements.txt

# تشغيل الخادم
python app.py
```

سيعمل الخادم على: `http://localhost:8000`
- وثائق API: `http://localhost:8000/docs`

### 4. تشغيل البوت

```bash
# في نافذة ترمينال جديدة (مع تفعيل البيئة الافتراضية)
cd backend
python -m bot.main_bot
```

### 5. تشغيل لوحة التحكم

```bash
cd frontend
npm install
npm run dev
```

ستعمل لوحة التحكم على: `http://localhost:5173`

---

## 🔑 بيانات الدخول الافتراضية

| الحقل | القيمة |
|-------|--------|
| اسم المستخدم | `admin` |
| كلمة المرور | `admin123` |

> ⚠️ **مهم:** غيّر كلمة المرور فور الدخول في بيئة الإنتاج!

## 💳 دورة اشتراك المشتركين

يسجل العميل من رابط **إنشاء حساب مدفوع**، ثم يحصل على رابط الدفع من مزود الدفع عند ضبط المتغير:

```env
PAYMENT_CHECKOUT_URL=https://your-provider.example/checkout/{invoice_id}
PAYMENT_WEBHOOK_SECRET=ضع-سر-webhook-قوي-هنا
```

بعد نجاح الدفع يستدعي مزود الدفع المسار التالي مع رأس `X-Webhook-Secret`:

```text
POST /auth/registrations/{registration_id}/confirm?payment_ref=TRANSACTION_ID
```

تأكيد الدفع لا ينشئ حسابًا فعالًا تلقائيًا. يظهر الطلب للمدير بحالة **مدفوع بانتظار الموافقة**، وبعد الموافقة فقط يتم إنشاء `Client` كمشترك يستطيع تسجيل الدخول.

---

## 📱 أوامر البوت

| الأمر | الوصف |
|-------|-------|
| `/start` | بدء التشغيل وعرض القائمة الرئيسية |
| `/generate` | توليد كروت هوت سبوت جديدة |
| `/cards` | عرض آخر الدفعات المولّدة |
| `/status` | حالة الراوتر والشبكة |
| `/users` | المستخدمون النشطون |
| `/stats` | إحصائيات عامة |
| `/help` | قائمة الأوامر |

---

## 🌐 مسارات API الرئيسية

| المسار | الطريقة | الوصف |
|--------|---------|-------|
| `/api/health` | GET | فحص حالة الخادم |
| `/api/auth/login` | POST | تسجيل الدخول |
| `/api/stats/overview` | GET | الإحصائيات العامة |
| `/api/cards` | GET | قائمة الدفعات |
| `/api/cards/generate` | POST | توليد كروت جديدة |
| `/api/cards/{id}/pdf` | GET | تنزيل PDF |
| `/api/network/status` | GET | حالة الراوتر |
| `/api/network/users` | GET | المستخدمون النشطون |

---

## 🔧 الإعداد لبيئة الإنتاج

### الانتقال لراوتر MikroTik حقيقي

```env
MIKROTIK_DEMO_MODE=False
MIKROTIK_HOST=192.168.88.1
MIKROTIK_USERNAME=admin
MIKROTIK_PASSWORD=your-router-password
```

> تأكد من تفعيل **RouterOS API** في الراوتر:
> `IP → Services → API (port 8728)` → Enable

### تغيير قاعدة البيانات إلى PostgreSQL

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/smartnet
```

```bash
pip install asyncpg
```

---

## 🛡️ الأمان

- ✅ JWT tokens للمصادقة
- ✅ قائمة مديرين مقيّدة في البوت
- ✅ تشفير كلمات المرور (bcrypt)
- ✅ CORS محدود في الإنتاج
- ✅ لا ترفع `.env` على GitHub أبداً!

---

## 📄 الترخيص

MIT License — للاستخدام الحر مع الإشارة للمصدر.

---

<div align="center">
صُنع بـ ❤️ | SmartNet v1.0.0
</div>

</div>
