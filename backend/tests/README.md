# Backend tests

Run from this directory:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use isolated in-memory SQLite databases. They do not connect to a MikroTik
router, call an external payment provider, send Telegram messages or mutate the
local production database.
