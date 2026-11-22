import random
import string
import asyncio
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

try:
    import routeros_api  # type: ignore
    ROUTEROS_AVAILABLE = True
except ImportError:
    ROUTEROS_AVAILABLE = False
    logger.info("routeros_api not installed — MikroTik client will use demo mode only.")


DEMO_INTERFACES = [
    {
        "name": "ether1",
        "type": "ether",
        "running": True,
        "disabled": False,
        "mac_address": "4C:5E:0C:AA:BB:01",
        "rx_bytes": 1_523_456_789,
        "tx_bytes": 892_345_678,
        "rx_packets": 9_823_456,
        "tx_packets": 7_234_567,
        "comment": "WAN - Internet",
    },
    {
        "name": "ether2",
        "type": "ether",
        "running": True,
        "disabled": False,
        "mac_address": "4C:5E:0C:AA:BB:02",
        "rx_bytes": 345_678_901,
        "tx_bytes": 1_234_567_890,
        "rx_packets": 3_456_789,
        "tx_packets": 8_901_234,
        "comment": "LAN - Local",
    },
    {
        "name": "wlan1",
        "type": "wlan",
        "running": True,
        "disabled": False,
        "mac_address": "4C:5E:0C:AA:BB:03",
        "rx_bytes": 789_012_345,
        "tx_bytes": 456_789_012,
        "rx_packets": 5_678_901,
        "tx_packets": 4_567_890,
        "comment": "WiFi Hotspot",
    },
]

DEMO_USERS = [
    {"username": "AB12CD34", "ip": "192.168.88.10", "mac": "A4:C3:F0:11:22:33",
     "uptime": "2h 14m 32s", "bytes_in": 45_678_901, "bytes_out": 12_345_678,
     "server": "hotspot1", "comment": ""},
    {"username": "EF56GH78", "ip": "192.168.88.11", "mac": "B8:27:EB:AB:CD:EF",
     "uptime": "0h 45m 12s", "bytes_in": 5_234_567, "bytes_out": 1_234_567,
     "server": "hotspot1", "comment": ""},
    {"username": "IJ90KL12", "ip": "192.168.88.12", "mac": "DC:A6:32:12:34:56",
     "uptime": "5h 02m 48s", "bytes_in": 123_456_789, "bytes_out": 45_678_901,
     "server": "hotspot1", "comment": ""},
    {"username": "MN34OP56", "ip": "192.168.88.13", "mac": "E4:5F:01:78:9A:BC",
     "uptime": "1h 30m 00s", "bytes_in": 20_000_000, "bytes_out": 8_000_000,
     "server": "hotspot1", "comment": ""},
    {"username": "QR78ST90", "ip": "192.168.88.14", "mac": "F8:1A:67:DE:F0:12",
     "uptime": "0h 12m 05s", "bytes_in": 1_000_000, "bytes_out": 500_000,
     "server": "hotspot1", "comment": ""},
    {"username": "UV12WX34", "ip": "192.168.88.15", "mac": "CC:32:E5:34:56:78",
     "uptime": "3h 55m 20s", "bytes_in": 87_654_321, "bytes_out": 23_456_789,
     "server": "hotspot1", "comment": ""},
    {"username": "YZ56AB78", "ip": "192.168.88.16", "mac": "00:1A:2B:9A:BC:DE",
     "uptime": "0h 58m 11s", "bytes_in": 11_223_344, "bytes_out": 3_344_556,
     "server": "hotspot1", "comment": ""},
]


class MikroTikClient:
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self._connection = None

    # ------------------------------------------------------------------ #
    #  Public API methods
    # ------------------------------------------------------------------ #

    async def get_status(self) -> Dict[str, Any]:
        if self.demo_mode or not ROUTEROS_AVAILABLE:
            return await self._demo_status()
        return await self._real_status()

    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        if self.demo_mode or not ROUTEROS_AVAILABLE:
            return await self._demo_sessions()
        return await self._real_sessions()

    async def generate_hotspot_users(
        self, count: int, profile: str, duration_hours: int
    ) -> List[Dict[str, Any]]:
        if self.demo_mode or not ROUTEROS_AVAILABLE:
            return await self._demo_generate(count, profile, duration_hours)
        return await self._real_generate(count, profile, duration_hours)

    async def remove_hotspot_user(self, username: str) -> bool:
        if self.demo_mode or not ROUTEROS_AVAILABLE:
            logger.info(f"[DEMO] Removed hotspot user: {username}")
            return True
        return await self._real_remove(username)

    async def reboot_router(self) -> bool:
        if self.demo_mode or not ROUTEROS_AVAILABLE:
            logger.info("[DEMO] Router reboot command sent.")
            await asyncio.sleep(1)
            return True
        return await self._real_reboot()

    async def get_interfaces(self) -> List[Dict[str, Any]]:
        if self.demo_mode or not ROUTEROS_AVAILABLE:
            return list(DEMO_INTERFACES)
        return await self._real_interfaces()

    # ------------------------------------------------------------------ #
    #  Demo implementations
    # ------------------------------------------------------------------ #

    async def _demo_status(self) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "board_name": "RB750Gr3",
            "version": "7.15.2 (stable)",
            "uptime": "14d 06h 32m 18s",
            "uptime_seconds": 1_235_538,
            "cpu_load": random.randint(5, 25),
            "memory_used": random.randint(50, 90),
            "memory_total": 256,
            "hdd_used": 14,
            "hdd_total": 512,
            "active_users_count": random.randint(4, 10),
            "interfaces": list(DEMO_INTERFACES),
            "connected": True,
        }

    async def _demo_sessions(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.05)
        count = random.randint(4, len(DEMO_USERS))
        return random.sample(DEMO_USERS, count)

    async def _demo_generate(
        self, count: int, profile: str, duration_hours: int
    ) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.1)
        users = []
        for _ in range(count):
            users.append(
                {
                    "username": self._generate_username(),
                    "password": self._generate_password(),
                    "profile": profile,
                    "duration_hours": duration_hours,
                }
            )
        return users

    # ------------------------------------------------------------------ #
    #  Real RouterOS implementations (requires routeros_api)
    # ------------------------------------------------------------------ #

    def _get_connection(self):
        if not ROUTEROS_AVAILABLE:
            raise RuntimeError("routeros_api is not installed.")
        from config.settings import settings  # lazy import
        connection = routeros_api.RouterOsApiPool(
            host=settings.MIKROTIK_HOST,
            port=settings.MIKROTIK_PORT,
            username=settings.MIKROTIK_USERNAME,
            password=settings.MIKROTIK_PASSWORD,
            plaintext_login=True,
        )
        return connection.get_api()

    async def _real_status(self) -> Dict[str, Any]:
        try:
            api = await asyncio.to_thread(self._get_connection)
            resources = await asyncio.to_thread(
                lambda: list(api.get_resource("/system/resource").get())
            )
            if not resources:
                return await self._demo_status()
            r = resources[0]
            active_users = await asyncio.to_thread(
                lambda: list(api.get_resource("/ip/hotspot/active").get())
            )
            mem_used_mb = int(int(r.get("total-memory", 0)) - int(r.get("free-memory", 0))) // (1024 * 1024)
            mem_total_mb = int(r.get("total-memory", 0)) // (1024 * 1024)
            return {
                "board_name": r.get("board-name", "Unknown"),
                "version": r.get("version", "Unknown"),
                "uptime": r.get("uptime", "Unknown"),
                "uptime_seconds": 0,
                "cpu_load": int(r.get("cpu-load", 0)),
                "memory_used": mem_used_mb,
                "memory_total": mem_total_mb,
                "hdd_used": 0,
                "hdd_total": 0,
                "active_users_count": len(active_users),
                "interfaces": await self._real_interfaces(),
                "connected": True,
            }
        except Exception as exc:
            logger.error(f"MikroTik real status failed: {exc} — falling back to demo")
            return await self._demo_status()

    async def _real_sessions(self) -> List[Dict[str, Any]]:
        try:
            api = await asyncio.to_thread(self._get_connection)
            sessions = await asyncio.to_thread(
                lambda: list(api.get_resource("/ip/hotspot/active").get())
            )
            result = []
            for s in sessions:
                result.append({
                    "username": s.get("user", ""),
                    "ip": s.get("address", ""),
                    "mac": s.get("mac-address", ""),
                    "uptime": s.get("uptime", ""),
                    "bytes_in": int(s.get("bytes-in", 0)),
                    "bytes_out": int(s.get("bytes-out", 0)),
                    "server": s.get("server", ""),
                    "comment": s.get("comment", ""),
                })
            return result
        except Exception as exc:
            logger.error(f"MikroTik real sessions failed: {exc} — falling back to demo")
            return await self._demo_sessions()

    async def _real_generate(
        self, count: int, profile: str, duration_hours: int
    ) -> List[Dict[str, Any]]:
        try:
            api = await asyncio.to_thread(self._get_connection)
            hotspot_users = api.get_resource("/ip/hotspot/user")
            users = []
            for _ in range(count):
                username = self._generate_username()
                password = self._generate_password()
                await asyncio.to_thread(
                    hotspot_users.add,
                    name=username,
                    password=password,
                    profile=profile,
                )
                users.append({
                    "username": username,
                    "password": password,
                    "profile": profile,
                    "duration_hours": duration_hours,
                })
            return users
        except Exception as exc:
            logger.error(f"MikroTik real generate failed: {exc} — falling back to demo")
            return await self._demo_generate(count, profile, duration_hours)

    async def _real_remove(self, username: str) -> bool:
        try:
            api = await asyncio.to_thread(self._get_connection)
            hotspot_users = api.get_resource("/ip/hotspot/user")
            users = await asyncio.to_thread(
                lambda: list(hotspot_users.get(name=username))
            )
            for u in users:
                await asyncio.to_thread(hotspot_users.remove, id=u["id"])
            return True
        except Exception as exc:
            logger.error(f"MikroTik real remove failed: {exc}")
            return False

    async def _real_reboot(self) -> bool:
        try:
            api = await asyncio.to_thread(self._get_connection)
            system = api.get_resource("/system")
            await asyncio.to_thread(system.call, "reboot")
            return True
        except Exception as exc:
            logger.error(f"MikroTik real reboot failed: {exc}")
            return False

    async def _real_interfaces(self) -> List[Dict[str, Any]]:
        try:
            api = await asyncio.to_thread(self._get_connection)
            ifaces = await asyncio.to_thread(
                lambda: list(api.get_resource("/interface").get())
            )
            result = []
            for iface in ifaces:
                result.append({
                    "name": iface.get("name", ""),
                    "type": iface.get("type", ""),
                    "running": iface.get("running", "false") == "true",
                    "disabled": iface.get("disabled", "false") == "true",
                    "mac_address": iface.get("mac-address", ""),
                    "rx_bytes": int(iface.get("rx-byte", 0)),
                    "tx_bytes": int(iface.get("tx-byte", 0)),
                    "rx_packets": int(iface.get("rx-packet", 0)),
                    "tx_packets": int(iface.get("tx-packet", 0)),
                    "comment": iface.get("comment", ""),
                })
            return result
        except Exception as exc:
            logger.error(f"MikroTik real interfaces failed: {exc} — falling back to demo")
            return list(DEMO_INTERFACES)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _generate_username(self) -> str:
        chars = string.ascii_uppercase + string.digits
        return "".join(random.choices(chars, k=8))

    def _generate_password(self) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(random.choices(chars, k=8))


# Module-level singleton — created lazily so settings are loaded first
_client: Optional[MikroTikClient] = None


def get_mikrotik_client() -> MikroTikClient:
    global _client
    if _client is None:
        from config.settings import settings
        _client = MikroTikClient(demo_mode=settings.MIKROTIK_DEMO_MODE)
    return _client
