# تجهيز وتشغيل وكلاء SmartNet على n8n المحلي – Windows

## متطلبات هذه النسخة

- Windows PowerShell.
- n8n الإصدار 2.49.5 تحت حساب Windows الذي يحتوي قاعدة Workflows الحالية.
- مستودع SmartNet في `D:\SmartNet`.
- اعتماد OpenAI API محفوظ في n8n.
- اعتماد Header Auth مخصص محفوظ في n8n.

تحتوي ملفات المستودع على 13 Workflow، و13 System Prompt عربية، وعقد AI Agent 3.1 وOpenAI Chat Model 1.2 متصلة بنموذج `gpt-6-luna`. مخرجات النموذج استشارية فقط.

## إنشاء الاعتمادات المحلية

من واجهة n8n:

1. افتح Credentials وأنشئ/تحقق من اعتماد `OpenAI API` من النوع `openAiApi`. لا تنسخ المفتاح إلى Git.
2. أنشئ اعتماد Webhook Header Auth جديداً من النوع `httpHeaderAuth` بالاسم الحرفي:
   `SmartNet Agents Header Auth`.
3. اضبط Header Name على `X-SmartNet-Agent-Key`.
4. أنشئ Header Value عشوائية قوية بطول 32 حرفاً أو أكثر واحفظها في مدير كلمات المرور. ستحتاج القيمة نفسها لاحقاً في `backend/.env`. لا ترسلها في المحادثة.

## تحديث الوكلاء التي استوردتها مسبقاً

لقد استوردت الـ13 Workflow من قبل، ولذلك **لا تشغّل Import-SmartNetAgents.ps1 مرة ثانية**. بعد دمج تحديث الوكلاء في main، نفّذ:

~~~powershell
cd D:\SmartNet
git pull origin main
Set-ExecutionPolicy -Scope Process Bypass -Force
.\automation\n8n\scripts\Update-And-Test-SmartNetAgents.ps1
~~~

يقوم المحدث بالآتي:
1. يتحقق من n8n 2.49.5.
2. يصدر نسخة احتياطية من جميع Workflows المحلية.
3. يشترط وجود 31 Workflow محلية كما في تدقيق 26 نوفمبر 2026؛ إذا اختلفت القاعدة أو الحساب يتوقف دون تعديل.
4. يقرأ أسماء ومعرّفات Credentials من تصدير n8n المشفر افتراضياً، ولا يفك القيم السرية ولا يعرضها.
5. يربط عقد OpenAI باعتماد `openAiApi`، ويطلب اختيار اعتماد `SmartNet Agents Header Auth` المخصص.
6. يحدث معرّفات الوكلاء الموجودة نفسها لتفادي النسخ المكررة.
7. يعيد التصدير ويتحقق من عقد النموذج والاتصال والمصادقة وبقاء كل Workflow غير منشورة.
8. يشغّل 13 اختبار Manual Trigger فعلياً؛ كل اختبار يمر بعقدة OpenAI.
9. لا يسجل الاختبار نجاحاً إلا إذا انتهى الأمر بنجاح وظهر marker باسم `SMARTNET_OPENAI_SMOKE_TEST_PASS`، وهذا marker لا يصدر إلا بعد وصول نص فعلي غير فارغ من النموذج. إذا أخفقت OpenAI، يفشل Manual Trigger بوضوح بدلاً من اعتماد مسار fallback كنجاح.
10. الوكيلان 06 و11 يستخدمان fixture محلياً في اختبار النموذج؛ هذا لا يثبت اتصال FastAPI.
11. ينشئ تقريراً وسجلات محلية.

إذا لم يجد الاعتمادات أو إحدى Workflows، يتوقف قبل الاستيراد. وإذا تعثر التحديث بعد بدايته يحاول استرجاع ما تم تحديثه من النسخ الاحتياطية.

## نشر التطوير المحلي بعد نجاح الاختبارات

افتراضياً تبقى كل Workflows غير منشورة. لا تنشر Webhooks على واجهة عامة دون HTTPS وحماية الشبكة.

للتطوير على نفس جهاز Windows فقط، وبعد التأكد أن n8n لا يستمع على واجهة الشبكة العامة، يمكن استخدام loopback:

شغّل n8n نفسه في نافذة PowerShell مستقلة، بعد إيقاف أي عملية n8n سابقة، وبمتغيرات ربط loopback التالية:

~~~powershell
$env:N8N_HOST = "127.0.0.1"
$env:N8N_LISTEN_ADDRESS = "127.0.0.1"
$env:N8N_PROTOCOL = "http"
$env:N8N_PORT = "5678"
$env:ENVIRONMENT = "development"
n8n start
~~~

في نافذة PowerShell ثانية، نفّذ المحدث بعد نجاح الاختبارات مع بوابات النشر الصريحة:

~~~powershell
cd D:\SmartNet
$env:N8N_HOST = "127.0.0.1"
$env:N8N_LISTEN_ADDRESS = "127.0.0.1"
$env:N8N_PROTOCOL = "http"
$env:N8N_PORT = "5678"
$env:ENVIRONMENT = "development"
$env:SMARTNET_ALLOW_LOCAL_HTTP_PUBLISH = "YES"
$env:SMARTNET_ALLOW_WEBHOOK_PUBLISH = "YES"
.\automation\n8n\scripts\Update-And-Test-SmartNetAgents.ps1 -PublishAfterSmokeTests
~~~

قبل النشر، يتحقق المحدث عبر Windows من أن منفذ n8n يستمع فعلياً على `127.0.0.1` أو `::1` فقط؛ إذا كان يستمع على `0.0.0.0` أو `::` أو أي واجهة أخرى، سيرفض النشر. لا يكفي تعيين `N8N_HOST` وحده.

لن يحاول المحدث النشر عبر HTTP إلا عندما يكون N8N_HOST وN8N_LISTEN_ADDRESS عنواني loopback، ويؤكد Windows أن مستمع TCP الفعلي لا يرتبط إلا بـ127.0.0.1 أو ::1، والبروتوكول HTTP والبيئة غير إنتاجية، مع تعيين متغيري الموافقة صراحةً، وبعد نجاح اختبارات OpenAI الـ13.

لخادم أو عنوان عام، استخدم HTTPS وشهادة صالحة وReverse Proxy وجداراً نارياً، واضبط WEBHOOK_URL أو N8N_PROTOCOL وفق إعداد الإنتاج. لا تستخدم بوابة HTTP المحلية على الإنتاج.

## تشغيل جسر Backend إلى الوكلاء

بعد إنشاء اعتماد Header Auth ونشر الوكلاء في n8n، افتح `backend/.env` واضبط القيم التالية، مع وضع نفس Header Value المحفوظة في n8n محلياً:

~~~dotenv
N8N_ENABLED=true
N8N_BASE_URL=http://127.0.0.1:5678
N8N_WEBHOOK_AUTH_HEADER=X-SmartNet-Agent-Key
N8N_WEBHOOK_AUTH_VALUE=<same-random-secret-as-n8n-credential>
N8N_TIMEOUT_SECONDS=12
~~~

في الإنتاج استخدم `N8N_BASE_URL=https://...`؛ إعدادات الإنتاج ترفض HTTP. أعد تشغيل FastAPI Backend بعد تعديل `.env`.

بعد تسجيل الدخول بحساب مدير، تظهر واجهات التكامل:
- `GET /api/v1/automation/agents` — قائمة الوكلاء وحالة التكامل.
- `POST /api/v1/automation/agents/{agent_id}/invoke` — استدعاء وكيل محدد.
- `POST /api/v1/automation/dispatch` — المشرف 00 يصنف المهمة ثم يوجهها عبر قائمة ثابتة إلى وكيل فرعي.

مثال لجسم طلب آمن في Swagger:

~~~json
{"task":"repository_audit","payload":{}}
~~~

لا تضع مفاتيح أو رموز دخول في الطلب أو في المحادثة. هذه المسارات تتطلب حساب مدير وتخضع لتحديد معدل الطلبات وسجل تدقيق.

## الصلاحيات والخصوصية

- جميع الوكلاء مستشارون؛ لا توجد AI Tools موصولة.
- لا يستطيع النموذج تشغيل أوامر MikroTik أو تعديل قاعدة البيانات أو الموافقة على دفع أو تعديل Ledger أو نشر التطبيق.
- Backend يحجب بيانات الدفع التفصيلية ومراجع التحويل والمبالغ والعملات وأهداف/أسباب الموافقات قبل إرسالها إلى n8n.
- الوكيل 00 لا ينفذ المهام الحساسة ولا يوجه مهمة إلى مسار غير موجود في القائمة المعتمدة.
- عمليات الدفع والراوتر واستعادة القاعدة والنشر تظل خلف موافقات Backend بشرية دائمة.

## التقرير بعد التشغيل

أرفق فقط:
`Documents\SmartNet-n8n-final-audit\SmartNet-n8n-live-update-<timestamp>.json`

إذا فشل اختبار، أرسل ملف السجل الخاص بالوكيل الفاشل فقط. لا ترسل ملف تصدير Credentials ولا ملف Workflow export الشامل.
