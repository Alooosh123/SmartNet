# تدقيق الاعتماديات وأمن الكود

يستخدم فرع الإنتاج المحسّن `backend/requirements.txt` و`backend/requirements-dev.txt` مع مسار CI منفصل.

التشغيل المحلي في PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip-audit -r requirements.txt --desc
bandit -r . -lll -x tests
```

لا تُحدّث جميع الحزم دفعة واحدة. عالج الثغرات في مجموعات صغيرة متوافقة، وشغّل اختبارات Backend وFrontend وMariaDB بعد كل مجموعة. يجب فحص تاريخ Git بحثاً عن أسرار سابقة وتدويرها؛ إزالة السر من الملف الحالي لا تلغي تعرضه السابق.
