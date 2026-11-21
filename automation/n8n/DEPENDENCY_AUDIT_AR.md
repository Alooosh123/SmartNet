# تدقيق الاعتماديات وأمن الكود

## ما الذي يفعله الفحص

- `pip-audit` يتحقق من الحزم المثبتة في `backend/requirements.txt` مقابل قاعدة الثغرات المعروفة.
- `Bandit` يفحص كود Python بحثاً عن أنماط أمنية عالية الخطورة فقط في هذه المرحلة.
- تقارير JSON تحفظ كـ GitHub Actions artifacts لمدة 14 يوماً.
- فشل أي فحص يمنع نجاح مهمة Security Audit.

## تشغيل محلي على Windows PowerShell

من جذر المستودع:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install pip-audit bandit
pip-audit -r backend\requirements.txt --desc
bandit -r backend -lll -x backend/tests
```

## تحديث الحزم

لا تنفذ تحديثاً شاملاً عشوائياً. لكل ثغرة:
1. حدد الحزمة والإصدار المتأثر والإصدار المصحح.
2. افحص متطلبات التوافق في التطبيق.
3. حدث حزمة واحدة أو مجموعة صغيرة مترابطة.
4. شغل اختبارات السلامة واختبارات التطبيق.
5. راجع التغييرات ثم ادمجها عبر Pull Request.

## حدود الفحص

- نجاح pip-audit لا يعني خلو التطبيق من الثغرات المنطقية.
- Bandit لا يحل محل مراجعة يدوية أو DAST.
- يجب إضافة فحص الأسرار عبر Gitleaks وفحص تاريخ Git، وتدوير أي مفاتيح سبق نشرها.
