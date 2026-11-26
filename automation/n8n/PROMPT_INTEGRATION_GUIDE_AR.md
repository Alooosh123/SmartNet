# ربط وكلاء SmartNet مع OpenAI في n8n 2.49.5

## الحالة في ملفات المستودع

تحتوي ملفات الوكلاء الـ13 على:
- AI Agent node v3.1.
- OpenAI Chat Model node v1.2 باستخدام model ID `gpt-6-luna`.
- اتصال `ai_languageModel` بين العقدتين.
- System Prompt عربي مستقل لكل وكيل.
- مرحلة تقليل بيانات ومدخلات قبل النموذج.
- Finalizer يحافظ على نتيجة التحقق الحتمية ويضيف `ai_advisory`.
- Webhook Trigger مع Header Auth، وManual Trigger للاختبار المحلي.

تم اختيار GPT-6 Luna للعمل المتكرر منخفض التكلفة. لا توجد أدوات AI متصلة. لا يتم تخزين Credentials داخل Git.

## تحديث قاعدة n8n المحلية

بعد دمج التحديث في main، شغّل:

~~~powershell
cd D:\SmartNet
git pull origin main
Set-ExecutionPolicy -Scope Process Bypass -Force
.\automation\n8n\scripts\Update-And-Test-SmartNetAgents.ps1
~~~

يقوم السكربت بنسخ جميع Workflows المحلية احتياطياً، يتحقق من أن الإصدار 2.49.5 وعدد Workflows يساوي 31، ويقرأ أسماء ومعرفات الاعتمادات من تصدير Credentials المشفر افتراضياً من دون فك القيم السرية أو عرضها. ثم يحدث نفس معرّفات الوكلاء الـ13 ويعيد التصدير للتحقق من عقد النموذج والمصادقة والاتصالات، وينفذ اختبار Manual Trigger لكل وكيل.

يلزم إنشاء Credentialين محلياً:
1. OpenAI API من النوع `openAiApi`، والمفتاح محفوظ داخل n8n.
2. Header Auth Credential من النوع `httpHeaderAuth` وبالاسم الحرفي `SmartNet Agents Header Auth`. اضبط Header Name إلى `X-SmartNet-Agent-Key` وأنشئ قيمة عشوائية قوية لا تقل عن 32 حرفاً. لا تستخدم قيمة منسوخة من مستودع أو ملف عام.

يعرض السكربت أسماء ومعرفات Credentials فقط، ويطلب منك اختيار اعتماد Header Auth ذي الاسم المحدد. يجب أن تطابق القيمة التي أدخلتها في هذا الاعتماد قيمة `N8N_WEBHOOK_AUTH_VALUE` في ملف `backend/.env`.

إذا لم يجد اعتماداً أو Workflow، أو اختلف إصدار n8n أو عدد Workflows، سيتوقف قبل التحديث. يحاول استرجاع النسخ الاحتياطية عند الفشل أثناء التحديث.

## اختبار النموذج

اختبارات Manual Trigger تستدعي عقد OpenAI فعلياً لكل وكيل. الوكيلان 01 و02 يقرآن شجرة GitHub العامة. الوكيلان 06 و11 يستخدمان fixture محلياً في مسار Manual Trigger لاختبار نموذج الذكاء الاصطناعي فقط؛ لا يثبتان عمل Backend. الاختبارات الآمنة لا تنفذ عمليات دفع أو RouterOS أو حذف/استعادة.

## نشر محلي بعد نجاح الاختبارات

لبيئة تطوير محلية loopback فقط، وبعد التحقق أن n8n لا يستمع على واجهة عامة:

~~~powershell
$env:N8N_HOST = "127.0.0.1"
$env:N8N_PROTOCOL = "http"
$env:ENVIRONMENT = "development"
$env:SMARTNET_ALLOW_LOCAL_HTTP_PUBLISH = "YES"
$env:SMARTNET_ALLOW_WEBHOOK_PUBLISH = "YES"
.\automation\n8n\scripts\Update-And-Test-SmartNetAgents.ps1 -PublishAfterSmokeTests
~~~

لا يسمح السكربت بـHTTP إلا عندما يكون N8N_HOST هو localhost أو 127.0.0.1 أو ::1، وبروتوكول HTTP وبيئة غير إنتاجية، مع موافقتين واضحتين. للعناوين العامة أو الخوادم استخدم HTTPS وشهادة صالحة وreverse proxy وجداراً نارياً، ثم استخدم بوابة النشر العامة بعد التحقق من مستهلك Webhook.

## ربط Backend

في ملف `backend/.env`، وبعد نشر Workflows ومطابقة اعتماد Header Auth، اضبط:

~~~dotenv
N8N_ENABLED=true
N8N_BASE_URL=http://127.0.0.1:5678
N8N_WEBHOOK_AUTH_HEADER=X-SmartNet-Agent-Key
N8N_WEBHOOK_AUTH_VALUE=<same-random-secret-as-n8n-credential>
N8N_TIMEOUT_SECONDS=12
~~~

أعد تشغيل Backend ليقرأ البيئة. في الإنتاج يلزم أن يكون `N8N_BASE_URL` HTTPS، وإلا يرفض إعدادات الإنتاج.

تتوفر مسارات إدارية تتطلب JWT مدير:
- `GET /api/v1/automation/agents`
- `POST /api/v1/automation/agents/{agent_id}/invoke`
- `POST /api/v1/automation/dispatch`

مثال آمن لاختبار الاستدعاء بعد تسجيل دخول المدير:

~~~json
{"task":"repository_audit","payload":{}}
~~~

تستدعي واجهة dispatch المشرف 00، وتتحقق من المسار الثابت، ثم تستدعي الوكيل الفرعي المسموح. لا تقبل URL يرسله المستخدم ولا تعرض النموذج لأدوات تنفيذ.

## حدود الصلاحيات

- مخرجات النموذج مشورة فقط؛ لا تستبدل القرار الحتمي.
- لا توجد AI Tools موصولة.
- لا توجد عمليات RouterOS أو الدفع أو Ledger أو Database restore أو deploy متاحة للنموذج.
- Backend يحجب بيانات الدفع ومراجعها والقيم الفعلية قبل إرسالها إلى n8n، كما يحجب نص أهداف وأسباب الموافقات.
- الوكيل 00 لا ينفذ طلباً حساساً؛ المهام المحظورة تظل خلف موافقة بشرية.
- نجاح الاختبارات المحلية لا يثبت قبول MikroTik أو مزود دفع حقيقي أو خادم إنتاجي.
