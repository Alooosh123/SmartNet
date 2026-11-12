"""Grounded network diagnostics over a curated, local operations knowledge base."""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings
from services.mikrotik_service import mikrotik_service

logger = logging.getLogger(__name__)
KB_ROOT = Path(__file__).resolve().parents[1] / "knowledge_base"
TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


def search_knowledge_base(question: str, top_k: int = 3) -> list[dict[str, str]]:
    tokens = {
        token.lower() for token in TOKEN_RE.findall(question)
        if len(token) > 2 and token.lower() not in {"من", "على", "الى", "هذا", "هذه", "كيف", "هل", "the", "and", "for"}
    }
    if not tokens or not KB_ROOT.exists():
        return []

    matches = []
    for path in sorted(KB_ROOT.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        sections = re.split(r"(?=^## )", raw, flags=re.MULTILINE)
        for section in sections:
            section_tokens = {token.lower() for token in TOKEN_RE.findall(section)}
            score = len(tokens.intersection(section_tokens))
            if score:
                heading = next((line.lstrip("# ").strip() for line in section.splitlines() if line.startswith("#")), path.stem)
                matches.append({
                    "source": path.name,
                    "heading": heading,
                    "score": str(score),
                    "content": section.strip()[:1800],
                })
    return sorted(matches, key=lambda item: int(item["score"]), reverse=True)[:max(1, min(top_k, 5))]



async def collect_read_only_observations() -> dict[str, Any]:
    """Collect minimal live RouterOS evidence through the read-only monitor account."""
    observed_at = datetime.now(timezone.utc).isoformat()
    if settings.MIKROTIK_DEMO_MODE:
        return {
            "available": False,
            "mode": "demo",
            "observed_at": observed_at,
            "reason": "Live RouterOS measurements are disabled in demo mode.",
        }

    try:
        status, active_users = await asyncio.gather(
            asyncio.wait_for(asyncio.to_thread(mikrotik_service.get_status), timeout=8),
            asyncio.wait_for(asyncio.to_thread(mikrotik_service.get_active_users), timeout=8),
        )
        # Do not disclose usernames, IP addresses, MAC addresses, or credentials
        # to the diagnostic model. Only aggregate network measurements are needed.
        return {
            "available": True,
            "mode": "live-read-only",
            "source": "MikroTik RouterOS API-SSL monitor account",
            "observed_at": observed_at,
            "board": status.get("board-name", status.get("board_name")),
            "router_version": status.get("version"),
            "uptime": status.get("uptime"),
            "cpu_load_percent": status.get("cpu-load", status.get("cpu_load")),
            "free_memory_bytes": status.get("free-memory", status.get("free_memory")),
            "total_memory_bytes": status.get("total-memory", status.get("total_memory")),
            "active_user_count": len(active_users or []),
        }
    except Exception as exc:
        logger.warning("Read-only diagnostic telemetry unavailable: %s", type(exc).__name__)
        return {
            "available": False,
            "mode": "live-read-only",
            "observed_at": observed_at,
            "reason": f"RouterOS read-only collection failed ({type(exc).__name__}).",
        }

async def diagnose(question: str) -> dict[str, Any]:
    """Return a grounded diagnostic answer; no RouterOS write tools exist in this agent."""
    sources = search_knowledge_base(question)
    observations = await collect_read_only_observations()
    if not sources:
        return {
            "answer": (
                "لا توجد مادة موثقة كافية في قاعدة معرفة SmartNet للإجابة بثقة. "
                "لا أستنتج سبب العطل من القياسات وحدها؛ اجمع سجلات المشكلة وأضف مرجعاً تشغيلياً موثوقاً أولاً."
            ),
            "model": "smartnet-kb-no-match",
            "sources": [],
            "observations": observations,
            "actions_executed": [],
        }

    context = "\n\n".join(
        f"[{item['source']} — {item['heading']}]\n{item['content']}"
        for item in sources
    )
    api_key = settings.OPENAI_API_KEY
    observation_context = json.dumps(observations, ensure_ascii=False, indent=2)
    if not api_key:
        return {
            "answer": (
                "وجدت إرشادات تشغيلية مرتبطة بسؤالك. ابدأ بفحوص القراءة فقط، "
                "ولا تطبق تغييرات على الراوتر قبل مراجعة مسؤول الشبكة.\n\n"
                "القياسات الحالية (إن توفرت):\n" + observation_context + "\n\n" + context
            ),
            "model": "smartnet-local-knowledge",
            "sources": [{"file": item["source"], "section": item["heading"]} for item in sources],
            "observations": observations,
            "actions_executed": [],
        }

    try:
        from openai import AsyncOpenAI
        async with AsyncOpenAI(api_key=api_key, timeout=20.0, max_retries=1) as client:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "أنت مهندس تشخيص شبكات داخل SmartNet. استخدم حصراً المعرفة التشغيلية "
                            "والقياسات الحالية المرفقة. ميّز بين القياس الحي ووضع Demo، واذكر وقت القياس. "
                            "اذكر ما هو معلوم وما يحتاج قياساً، ولا تخترع قراءات أو أسباباً مؤكدة. "
                            "اقترح فحوص قراءة فقط أولاً. لا تنفذ أو تصدر أوامر RouterOS، "
                            "ولا تطلب كلمة مرور أو مفاتيح. أي تغيير يحتاج طلب موافقة مسؤول."
                        ),
                    },
                    {"role": "user", "content": f"سؤال المشغل: {question}\n\nالقياسات الحالية:\n{observation_context}\n\nالمعرفة التشغيلية الموثوقة:\n{context}"},
                ],
                max_tokens=450,
                temperature=0.1,
            )
        return {
            "answer": response.choices[0].message.content or "تعذر إنشاء تشخيص موثوق.",
            "model": settings.OPENAI_MODEL,
            "sources": [{"file": item["source"], "section": item["heading"]} for item in sources],
            "observations": observations,
            "actions_executed": [],
        }
    except Exception:
        logger.exception("Network diagnostics model call failed.")
        return {
            "answer": "تعذر الوصول إلى نموذج الذكاء الاصطناعي. هذه هي المواد المحلية التي تطابق السؤال:\n\n" + context,
            "model": "smartnet-local-fallback",
            "sources": [{"file": item["source"], "section": item["heading"]} for item in sources],
            "observations": observations,
            "actions_executed": [],
        }

