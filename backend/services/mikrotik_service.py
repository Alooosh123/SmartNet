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

    def _get_api(self, read_only: bool = False):
        if settings.MIKROTIK_DEMO_MODE:
            return None
        if not ROUTEROS_AVAILABLE:
            raise RuntimeError("routeros_api is not installed; real MikroTik mode is unavailable.")
        username = settings.MIKROTIK_USERNAME
        password = settings.MIKROTIK_PASSWORD
        if read_only:
            username = settings.MIKROTIK_READ_USERNAME or username
            password = settings.MIKROTIK_READ_PASSWORD or password
        if not settings.MIKROTIK_HOST or not username or not password:
            raise RuntimeError("MikroTik host and credentials for the selected access role must be configured.")
        return routeros_api.RouterOsApiPool(
            settings.MIKROTIK_HOST, username=username, password=password,
            port=settings.MIKROTIK_PORT, use_ssl=settings.MIKROTIK_USE_SSL,
            ssl_verify=settings.MIKROTIK_USE_SSL, ssl_verify_hostname=settings.MIKROTIK_USE_SSL,
            plaintext_login=not settings.MIKROTIK_USE_SSL,
        )

    def get_status(self):
        if settings.MIKROTIK_DEMO_MODE:
            return {
                "platform": "MikroTik RouterOS (Demo)", "board-name": "RB750Gr3 (Demo)",
                "cpu-load": "14", "free-memory": "104857600",
                "uptime": "2d 4h 15m", "total-memory": "268435456", "version": "7.15.2 (stable)",
            }
        connection = self._get_api(read_only=True)
        try:
            result = connection.get_api().get_resource("/system/resource").get()
            return result[0] if result else {}
        finally:
            connection.disconnect()

    def get_active_users(self):
        if settings.MIKROTIK_DEMO_MODE:
            return list(self._demo_users)
        connection = self._get_api(read_only=True)
        try:
            return connection.get_api().get_resource("/ip/hotspot/active").get()
        finally:
            connection.disconnect()

    def monitor_snapshot(self):
        """Read-only telemetry collection; this method has no write operations."""
        if settings.MIKROTIK_DEMO_MODE:
            return {
                "status": "online", "board_name": "RB750Gr3 (Demo)", "uptime": "2d 4h 15m",
                "cpu_load": 14, "free_memory_bytes": 104857600,
                "total_memory_bytes": 268435456, "active_users_count": len(self._demo_users),
            }
        connection = self._get_api(read_only=True)
        try:
            api = connection.get_api()
            resources = api.get_resource("/system/resource").get()
            identity = api.get_resource("/system/identity").get()
            active = api.get_resource("/ip/hotspot/active").get()
            resource = resources[0] if resources else {}
            ident = identity[0] if identity else {}
            return {
                "status": "online", "board_name": ident.get("name") or resource.get("board-name"),
                "uptime": resource.get("uptime"), "cpu_load": resource.get("cpu-load"),
                "free_memory_bytes": resource.get("free-memory"),
                "total_memory_bytes": resource.get("total-memory"), "active_users_count": len(active),
            }
        finally:
            connection.disconnect()

    def disconnect_user(self, name: str) -> bool:
        if settings.MIKROTIK_DEMO_MODE:
            before = len(self._demo_users)
            self._demo_users = [u for u in self._demo_users if u.get("name") != name and u.get("id") != name]
            removed = len(self._demo_users) < before
            logger.info("[DEMO] Disconnected user %s: %s", name, removed)
            return removed
        connection = self._get_api()
        try:
            active = connection.get_api().get_resource("/ip/hotspot/active")
            sessions = active.get(user=name)
            if not sessions:
                sessions = [s for s in active.get() if s.get("user") == name or s.get(".id") == name]
            removed = False
            for item in sessions:
                session_id = item.get(".id") or item.get("id")
                if session_id:
                    active.remove(id=session_id)
                    removed = True
            return removed
        finally:
            connection.disconnect()

    @staticmethod
    def _profile_limit_uptime(profile: str):
        value = (profile or "").strip().lower().replace("_", " ")
        return {
            "1 day": "1d", "day": "1d", "يوم": "1d", "يوم واحد": "1d",
            "1 week": "7d", "week": "7d", "أسبوع": "7d", "اسبوع": "7d",
            "1 month": "30d", "month": "30d", "شهر": "30d",
        }.get(value)

    def generate_cards(self, count: int, profile: str, length: int = 6):
        if count < 1 or count > 1000:
            raise ValueError("count must be between 1 and 1000")
        if length < 4 or length > 16:
            raise ValueError("length must be between 4 and 16")
        existing_names = set()
        connection = None
        users_resource = None
        if not settings.MIKROTIK_DEMO_MODE:
            connection = self._get_api()
            try:
                api = connection.get_api()
                users_resource = api.get_resource("/ip/hotspot/user")
                existing_names = {x.get("name") for x in users_resource.get() if x.get("name")}
            except Exception:
                connection.disconnect()
                raise
        try:
            reserved = set(existing_names)
            cards = []
            while len(cards) < count:
                username = "".join(secrets.choice(string.digits) for _ in range(length))
                if username in reserved:
                    continue
                reserved.add(username)
                password = "".join(secrets.choice(string.digits) for _ in range(length))
                cards.append({"username": username, "password": password, "profile": profile})
            if users_resource is not None:
                api = connection.get_api()
                profile_names = {x.get("name") for x in api.get_resource("/ip/hotspot/user/profile").get()}
                if profile not in profile_names:
                    raise ValueError(f"RouterOS Hotspot profile not found: {profile}")
                for card in cards:
                    args = {"name": card["username"], "password": card["password"], "profile": profile}
                    limit = self._profile_limit_uptime(profile)
                    if limit:
                        args["limit-uptime"] = limit
                    users_resource.add(**args)
            return cards
        finally:
            if connection:
                connection.disconnect()

    def reboot_router(self) -> dict:
        if settings.MIKROTIK_DEMO_MODE:
            logger.info("[DEMO] Router reboot command simulated.")
            return {"ok": True, "message": "تمت محاكاة أمر إعادة تشغيل الراوتر (وضع التجريب)."}
        connection = self._get_api()
        try:
            connection.get_api().get_resource("/system").call("reboot")
            return {"ok": True, "message": "تم إرسال أمر إعادة تشغيل الراوتر."}
        finally:
            connection.disconnect()

    def add_custom_cards(self, cards: list, profile: str):
        if not settings.MIKROTIK_DEMO_MODE:
            connection = self._get_api()
            try:
                api = connection.get_api()
                profile_names = {x.get("name") for x in api.get_resource("/ip/hotspot/user/profile").get()}
                if profile not in profile_names:
                    raise ValueError(f"RouterOS Hotspot profile not found: {profile}")
                users = api.get_resource("/ip/hotspot/user")
                for card in cards:
                    args = {"name": card["username"], "password": card["password"], "profile": profile}
                    limit = self._profile_limit_uptime(profile)
                    if limit:
                        args["limit-uptime"] = limit
                    users.add(**args)
            finally:
                connection.disconnect()
        return cards


mikrotik_service = MikroTikService()
