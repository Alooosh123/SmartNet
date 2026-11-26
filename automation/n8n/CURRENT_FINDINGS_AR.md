# الحالة الحالية — SmartNet n8n وBackend Agent Bridge

## ما أظهره التدقيق المحلي المرفق (26 نوفمبر 2026)

- إصدار n8n: 2.49.5.
- عدد Workflows: 31؛ كلّها غير مفعّلة/غير منشورة وقت الفحص.
- عدد العقد: 154.
- عدد عقد AI Agent وChat Model وBasic LLM Chain: صفر وقت الفحص.
- مراجع OpenAI داخل Workflows: صفر وقت الفحص.
- 13 Webhook Trigger للوكلاء من 00 إلى 12 دون مصادقة محددة، و13 عقدة Respond to Webhook منفصلة. التقرير احتسب Respond nodes ضمن العدد الإجمالي للعقد التي لا تملك إعداد مصادقة؛ هذه ليست نقاط استقبال إضافية.
- توجد 14 Webhook Trigger أخرى بإعداد Header Auth في Workflows السابقة للمنصة.

## ما تم تجهيزه في فرع feature/n8n-live-ai-wiring

- إضافة AI Agent 3.1 + OpenAI Chat Model 1.2 إلى كل Workflow من الوكلاء الـ13، مع اتصال ai_languageModel وSystem Prompt عربي.
- اختيار gpt-6-luna بدلاً من gpt-5-mini القديم؛ ملفات العقد تضعه كـID مباشر لتجاوز الاعتماد على قائمة النماذج في واجهة n8n.
- إضافة Manual Trigger مستقل لاختبار كل وكيل.
- ضبط 13 Webhook Trigger على Header Auth. معرّفات الاعتمادات لا تحفظ في Git؛ أداة Windows تربط اعتماد OpenAI واعتماد Header Auth محلياً.
- الحفاظ على نتيجة Code nodes الحتمية، وإضافة نص النموذج في ai_advisory كمشورة فقط.
- لا توجد AI Tools موصولة. لا يملك النموذج أدوات مالية أو RouterOS أو قاعدة بيانات أو نشر.
- تقليل البيانات عند Backend قبل حفظها في n8n، مع حجب مراجع الدفع والمبالغ والعملات وأهداف وسبب الموافقات من مدخلات n8n.
- إضافة Backend allow-listed client وجسر API إداري، مع request rate limits وسجل تدقيق لا يحفظ Payload.
- إضافة اختبارية لوحدات HTTP Mock ورفض المسارات غير المسموحة وعدم التوجيه عند منع المشرف.

## ما لم يكتمل بعد

- لم تُحدّث قاعدة n8n المحلية بعد بالتوصيلات الجديدة؛ يلزم تشغيل `Update-And-Test-SmartNetAgents.ps1` تحت حساب Windows نفسه.
- لم يتم اختبار OpenAI API من جهاز المستخدم ضمن هذه الجلسة؛ اختبار 13 Workflow المحلي عبر Manual Trigger سيقدم الدليل الفعلي.
- لم تُضبط بعد بيانات اعتماد Header Auth المخصصة في n8n وBackend، ولم يتم نشر Webhooks محلياً.
- لم يتم اختبار End-to-End بين FastAPI وn8n المحلي؛ يتطلب تفعيل `N8N_ENABLED` وتطابق Header Auth ونشر المسارات.
- لم يتم اختبار MikroTik حقيقي أو أي مزود دفع خارجي أو Android Wallet Collector على جهاز مادي.
- لا يوجد نشر إنتاجي أو قبول على نطاق إنترنت عام.

## بوابات القبول

1. نجاح CI على أحدث SHA لفرع التحديث.
2. نجاح المحدث المحلي وتقرير 13/13 عقد ونموذج/اتصال ومصادقة.
3. نجاح 13/13 Manual Trigger smoke tests مع OpenAI الفعلي.
4. نشر محلي على loopback أو HTTPS بعد التحقق من الإعدادات.
5. نجاح GET /api/v1/automation/agents ثم POST /api/v1/automation/dispatch باستخدام جلسة مدير.
6. اختبار الرفض للمهام المحظورة وRoute mismatch، والتحقق من سجل التدقيق دون Payload.
7. اختبار قبول MikroTik والدفع والخادم الإنتاجي في بيئاتها الحقيقية قبل ادعاء اكتمال الإنتاج.
