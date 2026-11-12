<div dir="rtl">

# SmartNet — إدارة شبكات MikroTik وHotspot

منصة عربية لإدارة اشتراكات Hotspot والمستخدمين وكروت الاتصال والمدفوعات اليدوية الموثقة، مع وكلاء لمراقبة الشبكة وتشخيص الأعطال.

## التقنية

- Backend: Python 3.11+ وFastAPI وSQLAlchemy async.
- Web: React 19 وVite 8 بواجهة عربية RTL.
- Database: SQLite للتطوير فقط؛ MariaDB 12.3 LTS للإنتاج عبر asyncmy.
- Runtime: Podman وPodman Compose وContainerfiles؛ لا يلزم استخدام الحاويات للتطوير المحلي.
- Router: MikroTik RouterOS عبر API-SSL 8729 في شبكة خاصة/VPN.
- Payment: التحقق اليدوي الموثق افتراضياً. لا توجد بوابة خارجية حتى يتم اختيار المزود وتوفير وثائقه ومفاتيحه.
- Agents: مراقبة قراءة فقط وتشخيص بقواعد معرفة، وموافقات لتنفيذ عمليات الراوتر.
- Monitoring: Prometheus metrics وGrafana اختياريان.

## تطوير محلي على Windows

Backend:
```powershell
cd backend
Copy-Item ..\.env.example .env
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Frontend في نافذة أخرى:
```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

افتح http://localhost:5173. وثائق API على http://127.0.0.1:8000/docs. استخدم SQLite وMikroTik demo للتطوير فقط.

## الاختبارات

من backend:
```powershell
python -m compileall -q .
pytest -q tests
```

يتضمن CI أيضاً pip-audit وnpm audit، واختبار Playwright، واختبار MariaDB والترحيلات والمعاملات وdump/restore، وبناء صور Podman.

## تشغيل Podman

المتطلبات: Podman Engine/Podman Desktop وCompose provider مثل podman-compose.

```bash
cp .env.example .env
# استبدل جميع قيم dev-only واضبط بيانات MariaDB والراوتر والدومين
podman-compose -f compose.yaml config
podman-compose -f compose.yaml up -d --build
podman-compose -f compose.yaml ps
```

الواجهة على المنفذ 8080 افتراضياً. ضع HTTPS reverse proxy أمامها. قاعدة MariaDB لا تنشر منفذاً عاماً. لتشغيل المراقبة:
```bash
podman-compose -f compose.yaml --profile observability up -d
```

## MariaDB والهجرة والنسخ

- يستخدم الإنتاج mysql+asyncmy ولا يعتمد على PostgreSQL.
- الهجرة من SQLite: راجع docs/PRODUCTION_RUNBOOK.md واستخدم backend/scripts/migrate_sqlite_to_mariadb.py إلى قاعدة فارغة.
- النسخ الاحتياطي: scripts/backup-mariadb.sh.
- الاستعادة المتعمدة: CONFIRM_RESTORE=YES scripts/restore-mariadb.sh ...
- استعادة المرفقات: RESTORE_FILES=YES scripts/restore-application-files.sh ...

## وكلاء SmartNet

- Network Observer: يقرأ CPU والذاكرة ومدة التشغيل وعدد الجلسات باستخدام هوية RouterOS مخصصة للقراءة فقط.
- Diagnostic Agent: يعتمد ملف معرفة تشغيلية ومراجع MikroTik، ويصدر توصيات وأدلة ولا ينفذ أوامر.
- Network Approvals: عمليات reboot/disconnect تتحول إلى طلبات بموافقة مسؤول، وطلب المدير نفسه لا يعتمده منشئه.
- Finance Reconciliation: يطابق الاشتراكات مع سجل ManualPayment ولا يؤكد التحويلات أو يفعّل الحسابات تلقائياً.

## متطلبات خارجية

- MikroTik فعلي مع شهادة API-SSL موثوقة وحسابي قراءة/تحكم منفصلين وVPN وHotspot profile اختباري.
- للتحقق اليدوي: قناة تحويل فعلية ومسؤول يفحص وصول المبلغ. وللبوابة الآلية: اسم مزود ووثائقه ومفاتيح sandbox.
- دومين HTTPS، أسرار محمية، واستضافة ذات تخزين دائم ونسخ احتياطية خارج الخادم.

لا يتضمن المستودع بيانات حقيقية للراوتر أو لمزود الدفع، ولا ينبغي اختلاقها.

## الأمن

راجع SECURITY.md وdocs/PRODUCTION_RUNBOOK.md. إزالة الملفات من الشجرة الحالية لا تحذفها من تاريخ Git أو forks. قم بتدوير الأسرار القديمة ومراجعة تاريخ المستودع قبل الإطلاق.

</div>
