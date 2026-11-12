import logging
import secrets
import string
from config.settings import settings

logger = logging.getLogger(__name__)

try:
    import routeros_api
    ROUTEROS_AVAILABLE = True
except ImportError:
    ROUTEROS_AVAILABLE = False


class MikroTikService:
    def __init__(self):
        self._demo_users = [
            {"id": "*1", "name": "user_demo_1", "uptime": "1d 2h", "bytes-out": "10485760"},
            {"id": "*2", "name": "user_demo_2", "uptime": "5h 10m", "bytes-out": "5242880"},
            {"id": "*3", "name": "user_demo_3", "uptime": "25m 12s", "bytes-out": "1048576"},
        ]

    def _get_api(self):
        if settings.MIKROTIK_DEMO_MODE:
            return None
        if not ROUTEROS_AVAILABLE:
            raise RuntimeError("routeros_api is not installed; real MikroTik mode is unavailable.")
        if not settings.MIKROTIK_HOST or not settings.MIKROTIK_USERNAME or not settings.MIKROTIK_PASSWORD:
            raise RuntimeError("MIKROTIK_HOST, MIKROTIK_USERNAME and MIKROTIK_PASSWORD must be configured.")
        connection = routeros_api.RouterOsApiPool(
            settings.MIKROTIK_HOST,
            username=settings.MIKROTIK_USERNAME,
            password=settings.MIKROTIK_PASSWORD,
            port=settings.MIKROTIK_PORT,
            plaintext_login=True,
        )
        return connection

    def get_status(self):
        if settings.MIKROTIK_DEMO_MODE:
            return {
                "platform": "MikroTik RouterOS (Demo)",
                "board-name": "RB750Gr3 (Demo)",
                "cpu-load": "14",
                "free-memory": "104857600",
                "uptime": "2d 4h 15m",
                "total-memory": "268435456",
                "version": "7.15.2 (stable)",
            }

        connection = self._get_api()
        try:
            api = connection.get_api()
            resource = api.get_resource('/system/resource')
            res = resource.get()
            return res[0] if res else {}
        finally:
            if connection:
                connection.disconnect()

    def get_active_users(self):
        if settings.MIKROTIK_DEMO_MODE:
            return list(self._demo_users)

        connection = self._get_api()
        try:
            api = connection.get_api()
            resource = api.get_resource('/ip/hotspot/active')
            return resource.get()
        finally:
            if connection:
                connection.disconnect()

    def disconnect_user(self, name: str) -> bool:
        """Disconnect an active hotspot user."""
        if settings.MIKROTIK_DEMO_MODE:
            before = len(self._demo_users)
            self._demo_users = [u for u in self._demo_users if u.get("name") != name and u.get("id") != name]
            removed = len(self._demo_users) < before
            logger.info("[DEMO] Disconnected user %s: %s", name, removed)
            return removed

        connection = self._get_api()
        try:
            api = connection.get_api()
            active_resource = api.get_resource('/ip/hotspot/active')
            sessions = active_resource.get(user=name)
            if not sessions:
                # try by id or name directly
                sessions = [s for s in active_resource.get() if s.get('user') == name or s.get('.id') == name]
            if not sessions:
                return False
            removed = False
            for s in sessions:
                sid = s.get('.id') or s.get('id')
                if sid:
                    active_resource.remove(id=sid)
                    removed = True
            return removed
        finally:
            if connection:
                connection.disconnect()

    @staticmethod
    def _profile_limit_uptime(profile: str):
        """Translate known SmartNet card duration labels to RouterOS limit-uptime."""
        value = (profile or "").strip().lower().replace("_", " ")
        known = {
            "1 day": "1d",
            "day": "1d",
            "يوم": "1d",
            "يوم واحد": "1d",
            "1 week": "7d",
            "week": "7d",
            "أسبوع": "7d",
            "اسبوع": "7d",
            "1 month": "30d",
            "month": "30d",
            "شهر": "30d",
        }
        return known.get(value)

    def generate_cards(self, count: int, profile: str, length: int = 6):
        """Create unique, cryptographically random Hotspot credentials."""
        if count < 1 or count > 1000:
            raise ValueError("count must be between 1 and 1000")
        if length < 4 or length > 16:
            raise ValueError("length must be between 4 and 16")

        # The existing router usernames are checked before generation to avoid
        # collisions with prior card batches and other manually-created accounts.
        existing_names = set()
        connection = None
        users_resource = None
        if not settings.MIKROTIK_DEMO_MODE:
            connection = self._get_api()
            try:
                api = connection.get_api()
                users_resource = api.get_resource('/ip/hotspot/user')
                existing_names = {
                    item.get("name") for item in users_resource.get()
                    if item.get("name")
                }
            except Exception:
                if connection:
                    connection.disconnect()
                raise

        try:
            alphabet = string.digits
            cards = []
            reserved = set(existing_names)
            while len(cards) < count:
                username = "".join(secrets.choice(alphabet) for _ in range(length))
                if username in reserved:
                    continue
                reserved.add(username)
                password = "".join(secrets.choice(alphabet) for _ in range(length))
                cards.append({"username": username, "password": password, "profile": profile})

            if users_resource is not None:
                for card in cards:
                    user_args = {
                        "name": card["username"],
                        "password": card["password"],
                        "profile": profile,
                    }
                    uptime_limit = self._profile_limit_uptime(profile)
                    if uptime_limit:
                        user_args["limit-uptime"] = uptime_limit
                    users_resource.add(**user_args)
            return cards
        finally:
            if connection:
                connection.disconnect()

    def reboot_router(self) -> dict:
        """Send reboot command to MikroTik router or simulate in demo mode."""
        if settings.MIKROTIK_DEMO_MODE:
            logger.info("[DEMO] Router reboot command executed.")
            return {
                "ok": True,
                "message": "تم إرسال أمر إعادة تشغيل الراوتر بنجاح (وضع التجريب). سيعود الراوتر للعمل خلال دقيقة."
            }

        connection = self._get_api()
        try:
            api = connection.get_api()
            system = api.get_resource('/system')
            system.call('reboot')
            return {"ok": True, "message": "تم إرسال أمر إعادة تشغيل الراوتر بنجاح."}
        finally:
            if connection:
                connection.disconnect()

    def add_custom_cards(self, cards: list, profile: str):
        """Add owner's custom cards to MikroTik hotspot users."""
        if not settings.MIKROTIK_DEMO_MODE:
            connection = self._get_api()
            try:
                api = connection.get_api()
                users_resource = api.get_resource('/ip/hotspot/user')
                for card in cards:
                    user_args = {
                        "name": card["username"],
                        "password": card["password"],
                        "profile": profile,
                    }
                    uptime_limit = self._profile_limit_uptime(profile)
                    if uptime_limit:
                        user_args["limit-uptime"] = uptime_limit
                    users_resource.add(**user_args)
            finally:
                if connection:
                    connection.disconnect()
        return cards


mikrotik_service = MikroTikService()


