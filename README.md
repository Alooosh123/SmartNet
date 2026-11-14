<div dir="rtl">

# SmartNet — نظام إدارة شبكة Hotspot

SmartNet نظام عربي لإدارة اشتراكات Hotspot على MikroTik، إصدار الكروت وملفات PDF، مراجعة الدفعات، وإدارة الشبكة بمساعدة وكلاء ذكاء اصطناعي للقراءة فقط.

## المكونات
- Backend: Python 3.11+ وFastAPI وSQLAlchemy async.
- Frontend: React وVite، واجهة عربية RTL.
- Database: SQLite للتطوير المحلي فقط، وMariaDB 11.8 LTS للإنتاج.
- Router integration: MikroTik RouterOS API-SSL عبر شبكة إدارة خاصة أو VPN، مع تحقق إلزامي من شهادة TLS واسم المضيف (المنفذ الافتراضي 8729).
- Edge / HTTPS: Caddy، دون Docker أو Docker Compose.
- Operations: خدمات Windows/Linux، Alembic، نسخ احتياطي واستعادة.
- AI: مساعد دعم العميل، وكيل مراقبة شبكة للقراءة فقط، ووكيل تشخيص يعتمد قاعدة معرفة MikroTik.

## التشغيل المحلي على Windows

1. ثبّت Python 3.11 أو أحدث وNode.js 22.12 أو أحدث.
2. انسخ .env.example إلى backend/.env، واترك ENVIRONMENT=development وSQLite وDemo MikroTik للتطوير فقط.
3. افتح PowerShell:

~~~powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
~~~

4. في نافذة أخرى:

~~~powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
~~~

5. افتح http://127.0.0.1:5173. أول مدير تطوير ينشأ من DASHBOARD_USERNAME وDASHBOARD_PASSWORD. غيّر كلمة المرور فوراً.

## اختبارات الأمان والرحلة الكاملة

~~~powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip-audit -r requirements.txt --strict
python -m pytest -q tests
cd ..\frontend
npm audit --audit-level=moderate
npm run build
npm run test:e2e
~~~

اختبارات CI تشمل دورة التسجيل، التحقق اليدوي من التحويل، اعتماد الاشتراك، حدود الصلاحيات، توليد الكروت وPDF، وطلب عمليات الشبكة بموافقة الإدارة. بيئة الاختبار تستخدم MikroTik تجريبياً؛ لا تعتبر ذلك اختبار قبول للراوتر الحقيقي.

## الإنتاج: MariaDB + Caddy + خدمات النظام

لم يعد PostgreSQL أو Docker جزءاً من مسار النشر المعتمد. اتبع deploy/README.md لإعداد:
- MariaDB 11.8 LTS بترميز utf8mb4.
- حساب تشغيل محدود الصلاحيات، وحساب منفصل للترحيلات.
- alembic upgrade head قبل تشغيل Backend.
- بناء React static assets.
- Caddy لإدارة HTTPS والـReverse Proxy.
- خدمة systemd على Linux أو WinSW على Windows.
- نسخ احتياطي لقاعدة البيانات ومجلد backend/uploads واختبار الاستعادة.

**مهم:** إذا كانت لديك قاعدة PostgreSQL قديمة تحتوي بيانات حقيقية، فلا تغيّر DATABASE_URL مباشرة. يجب تصدير البيانات وتحويلها والتحقق من العلاقات والملفات في نسخة MariaDB تجريبية أولاً. دليل النشر يوضح أن هذا الانتقال ليس تلقائياً.

## قبول اتصال MikroTik الحقيقي (قراءة فقط أولاً)\nبعد إعداد شهادة API-SSL على RouterOS بحيث يطابق SAN اسم المضيف في MIKROTIK_HOST، وإعداد حساب المراقبة المنفصل، شغّل من مجلد backend:\n\n~~~powershell\npython scripts/mikrotik_readonly_acceptance.py\n~~~\n\nيستخدم الفحص API-SSL ويتحقق من سلسلة الشهادة واسم المضيف، ويعرض بيانات مجمعة وعدد الجلسات فقط دون أسماء أو عناوين المشتركين، ولا ينفذ أي تعديل. عند استخدام CA خاص، عيّن MIKROTIK_TLS_CA_FILE إلى ملف PEM موثوق. لا تستخدم API غير المشفر على المنفذ 8728 في الإنتاج.\n\n## الدفع اليدوي التشغيلي

الوضع المعتمد ما لم يتم توصيل مزود موثق هو PAYMENT_PROVIDER_MODE=manual:
1. ينشئ العميل طلب الاشتراك ويرفع الإيصال الاختياري.
2. يراجع الموظف حركة المحفظة/الحساب خارج SmartNet.
3. يدخل مرجع العملية والمبلغ والعملة وملاحظة المراجعة.
4. يتحقق النظام من تطابق المبلغ والعملة ومن عدم تكرار المرجع.
5. يعتمد المدير الاشتراك بصورة منفصلة.
6. يمكن مطابقة كشف CSV موحد بالحقول reference,amount,currency,status من المسار /auth/reconciliation/statement. المطابقة لا تغير حالة المدفوعات ولا تفعّل الحسابات تلقائياً.

لا يوجد ربط فعلي بمزود دفع محدد قبل تزويد المشروع بوثائق API الرسمية وبياناته.

## وكلاء الذكاء الاصطناعي
- Network Observer: يجمع CPU والذاكرة وإصدار RouterOS وعدد الجلسات فقط. لا يملك أوامر كتابة.
- Network Diagnostic Agent: يربط آخر قراءة بقاعدة معرفة موثقة، ويقدم تشخيصاً واحتمالات ومراجع، ولا ينفذ تغييرات.
- Customer Assistant: دعم واستفسارات اشتراك، ولا يثبت الدفع أو يدعي تنفيذ إجراءات.
- التغييرات على الراوتر تمر عبر طلب موافقة مدير، مع سجل منشئ ومراجع ونتيجة تنفيذ.

## بوابات التشغيل الفعلي
- [ ] pip-audit وnpm audit بلا ثغرات متوسطة/عالية غير معالجة.
- [ ] MariaDB migrations وbackup/restore تم اختبارها على نسخة مخصصة.
- [ ] DNS وHTTPS وCaddy وخدمة Backend يعملان بعد إعادة تشغيل الخادم.
- [ ] RouterOS API متاح عبر VPN/شبكة الإدارة بحساب محدود؛ لا تفتح منفذ API للإنترنت.
- [ ] نجاح قراءة الحالة والجلسات وإنشاء كرت وفصله على راوتر اختبار حقيقي.
- [ ] الدفع اليدوي أو مزود الدفع اجتاز مطابقة عملية حقيقية تجريبية.
- [ ] النسخ الاحتياطي لقاعدة البيانات وملفات uploads تمت استعادتهما فعلياً.
- [ ] سجلات المراقبة والتنبيهات ومؤشرات الوكلاء تعمل.

راجع SECURITY.md وdocs/PRODUCTION_RUNBOOK.md وdeploy/README.md.

</div>
