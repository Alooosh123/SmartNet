import json
from pathlib import Path

from config.settings import settings
from database import models

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "network_troubleshooting.json"


def _knowledge():
    with KNOWLEDGE_PATH.open("r", encoding="utf-8") as stream:
        return {item["id"]: item for item in json.load(stream)}


def diagnose(metric: models.NetworkMetric | None) -> dict:
    """Evidence-linked diagnostic. This agent never executes router commands."""
    kb = _knowledge()
    if metric is None:
        item = kb["telemetry-missing"]
        return {
            "status": "no_data",
            "findings": [{
                "knowledge_id": item["id"], "severity": item["severity"],
                "title": item["title"], "evidence": ["لا توجد قراءة حديثة محفوظة."],
                "recommended_steps": item["steps"], "sources": item["sources"],
            }],
            "actions_executed": [],
        }

    findings = []
    if metric.status == "degraded":
        item = kb["router-unreachable"]
        findings.append({
            "knowledge_id": item["id"], "severity": item["severity"],
            "title": item["title"], "evidence": [metric.alert_summary or "MikroTik telemetry unavailable"],
            "recommended_steps": item["steps"], "sources": item["sources"],
        })

    if metric.cpu_load is not None and metric.cpu_load >= settings.NETWORK_CPU_ALERT_THRESHOLD:
        item = kb["cpu-high"]
        findings.append({
            "knowledge_id": item["id"], "severity": item["severity"],
            "title": item["title"], "evidence": [f"CPU load = {metric.cpu_load}%"],
            "recommended_steps": item["steps"], "sources": item["sources"],
        })

    if metric.free_memory_bytes is not None and metric.total_memory_bytes:
        free_percent = metric.free_memory_bytes / max(metric.total_memory_bytes, 1) * 100
        if free_percent <= settings.NETWORK_FREE_MEMORY_ALERT_PERCENT:
            item = kb["memory-low"]
            findings.append({
                "knowledge_id": item["id"], "severity": item["severity"],
                "title": item["title"], "evidence": [f"Free memory = {free_percent:.1f}%"],
                "recommended_steps": item["steps"], "sources": item["sources"],
            })

    if not findings:
        findings.append({
            "knowledge_id": "no-current-alerts", "severity": "info",
            "title": "لم تُكتشف مؤشرات تتجاوز الحدود المعرفة.",
            "evidence": [
                f"حالة المراقبة: {metric.status}",
                f"CPU: {metric.cpu_load if metric.cpu_load is not None else 'غير متاح'}",
                f"المستخدمون النشطون: {metric.active_users_count if metric.active_users_count is not None else 'غير متاح'}",
            ],
            "recommended_steps": ["استمر في المراقبة وقارن القراءات مع خط الأساس المعتاد للشبكة."],
            "sources": [],
        })

    return {
        "status": metric.status,
        "observed_at": metric.observed_at.isoformat() if metric.observed_at else None,
        "findings": findings,
        "knowledge_base": "SmartNet curated rules v1",
        "actions_executed": [],
        "safety": "التوصيات فقط؛ لم تُرسل أوامر إلى MikroTik.",
    }
