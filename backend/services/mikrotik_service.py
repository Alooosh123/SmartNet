import logging
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
        if settings.MIKROTIK_DEMO_MODE or not ROUTEROS_AVAILABLE:
            return None
        connection = routeros_api.RouterOsApiPool(
            settings.MIKROTIK_HOST,
            username=settings.MIKROTIK_USERNAME,
            password=settings.MIKROTIK_PASSWORD,
            port=settings.MIKROTIK_PORT,
            plaintext_login=True,
        )
        return connection

    def get_status(self):
        if settings.MIKROTIK_DEMO_MODE or not ROUTEROS_AVAILABLE:
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
        if settings.MIKROTIK_DEMO_MODE or not ROUTEROS_AVAILABLE:
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
        if settings.MIKROTIK_DEMO_MODE or not ROUTEROS_AVAILABLE:
            self._demo_users = [u for u in self._demo_users if u.get("name") != name and u.get("id") != name]
            logger.info(f"[DEMO] Disconnected user: {name}")
            return True

        connection = self._get_api()
        try:
            api = connection.get_api()
            active_resource = api.get_resource('/ip/hotspot/active')
            sessions = active_resource.get(user=name)
            if not sessions:
                # try by id or name directly
                sessions = [s for s in active_resource.get() if s.get('user') == name or s.get('.id') == name]
            for s in sessions:
                sid = s.get('.id') or s.get('id')
                if sid:
                    active_resource.remove(id=sid)
            return True
        finally:
            if connection:
                connection.disconnect()

    def generate_cards(self, count: int, profile: str, length: int = 6):
        import random
        import string
        cards = []
        for _ in range(count):
            username = ''.join(random.choices(string.digits, k=length))
            password = ''.join(random.choices(string.digits, k=length))
            cards.append({'username': username, 'password': password, 'profile': profile})
            
        if not settings.MIKROTIK_DEMO_MODE and ROUTEROS_AVAILABLE:
            connection = self._get_api()
            try:
                api = connection.get_api()
                users_resource = api.get_resource('/ip/hotspot/user')
                for card in cards:
                    users_resource.add(name=card['username'], password=card['password'], profile=profile)
            finally:
                if connection:
                    connection.disconnect()

        return cards
                
    def reboot_router(self) -> dict:
        """Send reboot command to MikroTik router or simulate in demo mode."""
        if settings.MIKROTIK_DEMO_MODE or not ROUTEROS_AVAILABLE:
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
        if not settings.MIKROTIK_DEMO_MODE and ROUTEROS_AVAILABLE:
            connection = self._get_api()
            try:
                api = connection.get_api()
                users_resource = api.get_resource('/ip/hotspot/user')
                for card in cards:
                    users_resource.add(name=card['username'], password=card['password'], profile=profile)
            finally:
                if connection:
                    connection.disconnect()
        return cards


mikrotik_service = MikroTikService()


