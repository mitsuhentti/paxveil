from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

MENU = {
    "🔍 Проверить проект": "upload",
    "📁 Мои проекты": "projects",
    "🛡 Уязвимости": "vulnerabilities",
    "🧪 FixLab": "fixlab",
    "🚨 Fire Drill": "fire",
    "🔔 Мониторинг": "watch",
    "⚙️ Настройки": "settings",
}


def text(value: Any, limit: int = 300) -> str:
    return escape(str(value)[:limit], quote=True)


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label[:64], callback_data=data)
                for label, data in row
            ]
            for row in rows
        ]
    )


def home_keyboard() -> ReplyKeyboardMarkup:
    labels = list(MENU)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=label) for label in labels[i : i + 2]]
            for i in range(0, len(labels), 2)
        ],
        resize_keyboard=True,
        input_field_placeholder="Отправьте lock-файл или выберите действие",
    )


def project_keyboard(project: dict[str, Any]) -> InlineKeyboardMarkup:
    pid = str(project["id"])
    enabled = bool(project.get("watch"))
    return keyboard(
        [
            [("📄 Отчёт", f"report:{pid}"), ("🧪 FixLab", f"strategies:{pid}")],
            [("🔄 Сканировать", f"scan:{pid}")],
            [
                (
                    "🔕 Отключить Watch" if enabled else "🔔 Включить Watch",
                    f"watch:{pid}:{0 if enabled else 1}",
                )
            ],
            [("🗑 Удалить проект", f"delete:{pid}"), ("← Проекты", "list:projects:0")],
            [("Главное меню", "home")],
        ]
    )


def report_summary(project: dict[str, Any]) -> str:
    latest = project.get("latest_scan") or {}
    report = latest.get("report") or {}
    status = latest.get("status", "нет сканирования")
    title = f"<b>{text(project.get('name', 'Проект'), 80)}</b>"
    if not report:
        return f"{title}\nСканирование: <code>{text(status, 40)}</code>\nWatch: {'включён' if project.get('watch') else 'выключен'}"
    stats = report.get("stats") or {}
    findings = report.get("findings") or []
    priorities = [
        f.get("priority", 0)
        for f in findings
        if isinstance(f.get("priority"), (float, int))
    ]
    lines = [
        title,
        f"Зависимостей: <b>{text(stats.get('dependencies', len(report.get('dependencies', []))))}</b>",
        f"Известных уязвимостей: <b>{text(stats.get('findings', len(findings)))}</b>",
        f"Наибольший приоритет: <b>{max(priorities, default=0)}/100</b>",
        f"Полнота анализа: <code>{text(report.get('completeness', 'unknown'), 80)}</code>",
        f"Watch: {'включён' if project.get('watch') else 'выключен'}",
    ]
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("⚠️ " + text(warnings[0], 350))
        if len(warnings) > 1:
            lines.append(f"Ещё предупреждений: {len(warnings) - 1}. См. полный отчёт.")
    if not findings:
        lines.append(
            "Это результат доступных источников; он не гарантирует отсутствие уязвимостей."
        )
    else:
        lines.append(
            "Наличие уязвимой версии не доказывает эксплуатацию в вашем приложении."
        )
    return "\n".join(lines)


def finding_summary(finding: dict[str, Any]) -> str:
    lines = [
        f"<b>{text(finding.get('id', 'Advisory'), 100)}</b> · {text(finding.get('severity', 'unknown'), 20)}",
        f"<code>{text(finding.get('package'), 100)}=={text(finding.get('version'), 60)}</code>",
        f"Приоритет {text(finding.get('priority', 0))}/100 · CVSS {text(finding.get('cvss') if finding.get('cvss') is not None else 'нет данных')}",
    ]
    epss = finding.get("epss")
    lines.append(
        f"EPSS: {epss:.2%}" if isinstance(epss, (int, float)) else "EPSS: нет данных"
    )
    if finding.get("kev"):
        lines.append("CISA KEV: есть запись о подтверждённой эксплуатации.")
    lines.append(text(finding.get("summary", ""), 350))
    fixed = finding.get("fixed_versions") or []
    lines.append(
        "Исправленные версии: "
        + (text(", ".join(map(str, fixed[:6])), 200) if fixed else "нет данных")
    )
    reasons = finding.get("priority_reasons") or []
    if reasons:
        lines.append(
            "Причины приоритета: " + text("; ".join(map(str, reasons[:3])), 250)
        )
    return "\n".join(lines)


def settings_summary(settings: dict[str, Any]) -> str:
    quiet = (
        f"{text(settings.get('quiet_start'))}–{text(settings.get('quiet_end'))}"
        if settings.get("quiet_start")
        else "выключены"
    )
    return "\n".join(
        [
            "<b>Настройки PAXVEIL Watch</b>",
            f"Часовой пояс: <code>{text(settings.get('timezone', 'UTC'), 80)}</code>",
            f"Тихие часы: {quiet}",
            f"Минимальный приоритет: {text(settings.get('minimum_priority', 0))}/100",
            f"Дайджест: {'включён' if settings.get('digest') else 'выключен'}",
            "",
            "/timezone Europe/Moscow",
            "/quiet 22:00 08:00 или /quiet off",
            "/priority 60",
            "/digest on или /digest off",
            "/category new off (new, priority, fix, exploitation, status)",
            "/link КОД — связать с веб-аккаунтом",
        ]
    )


def fix_summary(strategy: dict[str, Any], limitations: list[str]) -> str:
    lines = [
        f"<b>FixLab · {text(strategy.get('name', 'Стратегия'), 80)}</b>",
        text(strategy.get("reason", ""), 400),
    ]
    lines.append(f"Статус: <code>{text(strategy.get('status', 'unknown'), 60)}</code>")
    updates = strategy.get("updates") or []
    for item in updates[:8]:
        if isinstance(item, dict):
            name = item.get("package", item.get("name", "?"))
            old = item.get("from", item.get("current", item.get("from_version", "?")))
            new = item.get("to", item.get("target", item.get("to_version", "?")))
            lines.append(
                f"• <code>{text(name, 90)}</code>: {text(old, 50)} → {text(new, 50)}"
            )
    if len(updates) > 8:
        lines.append(f"Ещё обновлений: {len(updates) - 8}; см. веб-отчёт.")
    for label, key in [("До", "before"), ("После", "after")]:
        stats = strategy.get(key)
        if isinstance(stats, dict):
            lines.append(
                f"{label}: зависимостей {text(stats.get('dependencies', '?'))}, находок {text(stats.get('findings', '?'))}"
            )
        else:
            lines.append(f"{label}: результат не подтверждён")
    for label, key in [
        ("Конфликты", "conflicts"),
        ("Неопределённости", "uncertainties"),
    ]:
        values = strategy.get(key) or []
        if values:
            lines.append(f"{label}: " + text("; ".join(map(str, values[:2])), 350))
    if limitations:
        lines.append("Ограничения: " + text("; ".join(map(str, limitations[:2])), 400))
    lines.append("Это модель обновления. Перед применением нужны тесты совместимости.")
    return "\n".join(lines)
