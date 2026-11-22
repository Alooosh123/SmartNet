"""Optional Telegram operations bot for SmartNet administrators.

Run with: python -m bot.main_bot (from the backend directory).
The Telegram bot uses the same initial admin credentials as the API, so protect
the environment file and rotate the bootstrap password after first deployment.
"""
import asyncio
import logging
from io import BytesIO
from typing import Any

import httpx
from telegram import Update, InputFile
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("smartnet.telegram")


class SmartNetApi:
    def __init__(self) -> None:
        self.base_url = settings.BOT_API_BASE_URL.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=20.0)
        self.token: str | None = None

    async def authenticate(self) -> None:
        response = await self.client.post(
            "/auth/login",
            data={
                "username": settings.DASHBOARD_USERNAME,
                "password": settings.DASHBOARD_PASSWORD,
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("role") != "admin" or not data.get("access_token"):
            raise RuntimeError("Telegram bot could not obtain an administrator API token.")
        self.token = data["access_token"]

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self.token:
            await self.authenticate()
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.token}"
        response = await self.client.request(method, path, headers=headers, **kwargs)
        if response.status_code == 401:
            self.token = None
            await self.authenticate()
            headers["Authorization"] = f"Bearer {self.token}"
            response = await self.client.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()
        return response

    async def close(self) -> None:
        await self.client.aclose()


api = SmartNetApi()


def is_allowed(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in settings.TELEGRAM_ADMIN_IDS)


async def deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("هذا البوت مخصص لمديري الشبكة المصرح لهم فقط.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await deny(update)
        return
    await update.effective_message.reply_text(
        "مرحباً بك في SmartNet Admin Bot\n"
        "/status - حالة الراوتر\n"
        "/users - المستخدمون النشطون\n"
        "/cards - آخر دفعات الكروت\n"
        "/generate عدد profile - توليد كروت\n"
        "/stats - صحة API وقاعدة البيانات"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await deny(update)
        return
    try:
        data = (await api.request("GET", "/mikrotik/status")).json()
        await update.effective_message.reply_text(
            "حالة MikroTik\n"
            f"اللوحة: {data.get('board-name', data.get('board_name', 'غير معروف'))}\n"
            f"الإصدار: {data.get('version', 'غير معروف')}\n"
            f"وقت التشغيل: {data.get('uptime', 'غير معروف')}\n"
            f"CPU: {data.get('cpu-load', data.get('cpu_load', '—'))}\n"
            f"المستخدمون النشطون: {data.get('active_users_count', '—')}"
        )
    except Exception:
        logger.exception("Telegram status command failed")
        await update.effective_message.reply_text("تعذر قراءة حالة الراوتر. راجع سجلات الخادم.")


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await deny(update)
        return
    try:
        records = (await api.request("GET", "/mikrotik/users")).json()
        lines = [f"المستخدمون النشطون: {len(records)}"]
        for item in records[:30]:
            lines.append(
                f"• {item.get('user', item.get('name', item.get('username', '—')))} | "
                f"{item.get('address', item.get('ip', '—'))} | "
                f"{item.get('uptime', '—')}"
            )
        await update.effective_message.reply_text("\n".join(lines)[:4000])
    except Exception:
        logger.exception("Telegram users command failed")
        await update.effective_message.reply_text("تعذر جلب المستخدمين. تحقق من الصلاحيات واتصال MikroTik.")


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await deny(update)
        return
    try:
        batches = (await api.request("GET", "/cards/batches")).json()
        lines = ["آخر دفعات الكروت:"]
        for batch in batches[:15]:
            lines.append(
                f"#{batch['id']} | {batch['profile']} | {batch['count']} كرت"
            )
        await update.effective_message.reply_text("\n".join(lines))
    except Exception:
        logger.exception("Telegram cards command failed")
        await update.effective_message.reply_text("تعذر جلب دفعات الكروت.")


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await deny(update)
        return
    if not context.args:
        await update.effective_message.reply_text("استخدم: /generate 20 1-Day")
        return
    try:
        count = int(context.args[0])
        profile = " ".join(context.args[1:]) or "1 Day"
        if count < 1 or count > 100:
            await update.effective_message.reply_text("العدد المسموح من 1 إلى 100 في أمر البوت.")
            return
        batch = (await api.request(
            "POST",
            "/cards/generate",
            json={"count": count, "profile": profile, "length": 8, "hide_password": False},
        )).json()
        pdf = await api.request("GET", f"/cards/{batch['id']}/pdf")
        document = InputFile(BytesIO(pdf.content), filename=f"smartnet_batch_{batch['id']}.pdf")
        await update.effective_message.reply_document(
            document=document,
            caption=f"تم إنشاء الدفعة #{batch['id']} — {batch['count']} كرت — {batch['profile']}",
        )
    except ValueError:
        await update.effective_message.reply_text("عدد الكروت يجب أن يكون رقماً صحيحاً.")
    except Exception:
        logger.exception("Telegram generate command failed")
        await update.effective_message.reply_text("فشل توليد الكروت. تحقق من الراوتر وملف Profile.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await deny(update)
        return
    try:
        data = (await api.request("GET", "/api/health/ready")).json()
        await update.effective_message.reply_text(
            f"SmartNet API: {data.get('status')}\n"
            f"قاعدة البيانات: {data.get('database')}\n"
            f"البيئة: {data.get('environment')}\n"
            f"وضع MikroTik التجريبي: {data.get('mikrotik_demo_mode')}\n"
            f"وضع الدفع التجريبي: {data.get('payment_demo_mode')}"
        )
    except Exception:
        logger.exception("Telegram health command failed")
        await update.effective_message.reply_text("الخادم غير جاهز أو تعذر الاتصال به.")


async def post_init(application: Application) -> None:
    await api.authenticate()
    logger.info("SmartNet Telegram bot authenticated to the API.")


async def post_shutdown(application: Application) -> None:
    await api.close()


def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required to run the Telegram bot.")
    if not settings.TELEGRAM_ADMIN_IDS:
        raise SystemExit("Set TELEGRAM_ADMIN_IDS to a JSON array of Telegram numeric user IDs.")

    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("users", users))
    application.add_handler(CommandHandler("cards", cards))
    application.add_handler(CommandHandler("generate", generate))
    application.add_handler(CommandHandler("stats", stats))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
