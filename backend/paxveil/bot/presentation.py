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
    "Проверить файл": "upload",
    "Пример проверки": "example",
    "Мои проекты": "projects",
    "Уязвимости": "vulnerabilities",
    "Варианты обновления": "fixlab",
    "Проверить CVE": "fire",
    "Мониторинг": "watch",
    "Настройки": "settings",
}

# Reply keyboards remain in Telegram's history after a bot update.
LEGACY_MENU = {
    "🔍 Проверить проект": "upload",
    "📎 Пример проверки": "example",
    "📁 Мои проекты": "projects",
    "🛡 Уязвимости": "vulnerabilities",
    "🧪 FixLab": "fixlab",
    "🚨 Fire Drill": "fire",
    "🔔 Мониторинг": "watch",
    "⚙️ Настройки": "settings",
}

STATUS_LABELS = {
    "queued": "В очереди",
    "pending": "В очереди",
    "running": "Проверяется",
    "completed": "Завершено",
    "succeeded": "Завершено",
    "partial": "Неполные данные",
    "insufficient_data": "Недостаточно данных",
    "failed": "Ошибка проверки",
    "retry": "Повторная попытка",
    "resolved": "Рассчитано",
    "conflict": "Конфликт зависимостей",
    "unknown": "Нет данных",
}

COMPLETENESS_LABELS = {
    "recorded_versions_checked": "Проверены указанные версии",
    "complete": "Проверка завершена",
    "partial": "Неполные данные",
    "insufficient_data": "Недостаточно данных",
    "unknown": "Нет данных",
}

SEVERITY_LABELS = {
    "critical": "Критическая",
    "high": "Высокая",
    "medium": "Средняя",
    "moderate": "Средняя",
    "low": "Низкая",
    "unknown": "Нет данных",
}

STRATEGY_LABELS = {
    "Minimal Change": "Точечное обновление",
    "Balanced": "В пределах major-версии",
    "Maximum Coverage": "Полное обновление",
}

FIRE_LABELS = {
    "confirmed": "Совпадение уязвимой версии",
    "possible": "Возможное совпадение",
    "no_match": "Совпадений не найдено",
    "insufficient_data": "Недостаточно данных",
    "unknown": "Нет данных",
    "found": "Запись найдена",
    "affected": "Уязвимая версия",
}

EXPLANATIONS = {
    "Smallest newer stable release in the same major/minor family, subject to recorded non-pin bounds.": "Ближайшая новая стабильная версия в текущей ветке. Ограничения исходного файла учитываются.",
    "Newest stable release in the same major family, subject to recorded non-pin bounds.": "Последняя стабильная версия без смены основной версии пакета. Ограничения исходного файла учитываются.",
    "Newest stable release across major families; original non-pin bounds are relaxed explicitly.": "Последняя стабильная версия, включая новую основную версию. Ограничения исходного файла могут быть ослаблены.",
    "Resolution uses official PyPI binary metadata; package code and application tests are never executed.": "Расчёт использует метаданные PyPI. Код пакетов и тесты приложения не запускаются.",
    "A resolved environment is a proposal, not a guarantee of behavioral compatibility.": "Согласованный набор версий ещё нужно проверить тестами вашего приложения.",
    "A version match does not demonstrate application reachability or exploitability.": "Совпадение версии не доказывает возможность эксплуатации в приложении.",
    "A single lock file may omit root paths, extras or platform selection.": "В одном lock-файле могут отсутствовать корневые зависимости, дополнительные группы и выбор платформы.",
}


def text(value: Any, limit: int = 300) -> str:
    return escape(str(value)[:limit], quote=True)


def explanation(value: Any) -> str:
    raw = str(value)
    return EXPLANATIONS.get(raw, raw)


def display_label(value: Any, labels: dict[str, str], limit: int = 80) -> str:
    raw = "unknown" if value is None else str(value)
    return text(labels.get(raw, raw), limit)


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label[:64], callback_data=data) for label, data in row] for row in rows
        ]
    )


def home_keyboard() -> ReplyKeyboardMarkup:
    labels = list(MENU)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in labels[i : i + 2]] for i in range(0, len(labels), 2)],
        resize_keyboard=True,
        input_field_placeholder="Отправьте файл зависимостей или выберите действие",
    )


def project_keyboard(project: dict[str, Any]) -> InlineKeyboardMarkup:
    pid = str(project["id"])
    enabled = bool(project.get("watch"))
    latest = project.get("latest_scan") or {}
    rows = []
    if latest.get("report"):
        rows.append([("Открыть отчёт", f"report:{pid}"), ("Варианты обновления", f"strategies:{pid}")])
    if latest.get("status") in {"queued", "pending", "running", "retry"}:
        rows.append([("Обновить результат", f"scanrefresh:{pid}")])
    else:
        rows.append([("Проверить снова", f"scan:{pid}")])
    rows.extend(
        [
            [
                (
                    "Отключить мониторинг" if enabled else "Включить мониторинг",
                    f"watch:{pid}:{0 if enabled else 1}",
                )
            ],
            [("Все проекты", "list:projects:0")],
            [("Удалить проект", f"delete:{pid}")],
        ]
    )
    return keyboard(rows)


def report_summary(project: dict[str, Any]) -> str:
    latest = project.get("latest_scan") or {}
    report = latest.get("report") or {}
    status = latest.get("status", "Ещё не проверялся")
    title = f"<b>{text(project.get('name', 'Проект'), 80)}</b>"
    if not report:
        lines = [
            title,
            f"Проверка: <code>{display_label(status, STATUS_LABELS, 40)}</code>",
            f"Мониторинг: {'включён' if project.get('watch') else 'выключен'}",
        ]
        if status in {"queued", "pending", "running", "retry"}:
            lines.append("Можно вернуться позже. Проверка продолжится, даже если закрыть чат.")
        elif status == "failed":
            lines.append("Попробуйте «Проверить снова». Если ошибка повторится, проверьте формат файла.")
        return "\n".join(lines)
    stats = report.get("stats") or {}
    findings = report.get("findings") or []
    priorities = [f.get("priority", 0) for f in findings if isinstance(f.get("priority"), (float, int))]
    lines = [
        title,
        f"Зависимостей: <b>{text(stats.get('dependencies', len(report.get('dependencies', []))))}</b>",
        f"Известных уязвимостей: <b>{text(stats.get('findings', len(findings)))}</b>",
        f"Наибольший приоритет: <b>{max(priorities, default=0)}/100</b>",
        f"Проверка: <code>{display_label(report.get('completeness'), COMPLETENESS_LABELS)}</code>",
        f"Мониторинг: {'включён' if project.get('watch') else 'выключен'}",
    ]
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("⚠️ " + text(warnings[0], 350))
        if len(warnings) > 1:
            lines.append(f"Ещё предупреждений: {len(warnings) - 1}. См. полный отчёт.")
    if not findings:
        lines.append("Это результат доступных источников; он не гарантирует отсутствие уязвимостей.")
    else:
        lines.append("Откройте отчёт для деталей или сравните варианты обновления.")
        lines.append("Наличие уязвимой версии не доказывает эксплуатацию в вашем приложении.")
    return "\n".join(lines)


def finding_summary(finding: dict[str, Any]) -> str:
    lines = [
        f"<b>{text(finding.get('id', 'Уязвимость'), 100)}</b> · {display_label(finding.get('severity'), SEVERITY_LABELS, 40)}",
        f"<code>{text(finding.get('package'), 100)}=={text(finding.get('version'), 60)}</code>",
        f"Приоритет {text(finding.get('priority', 0))}/100 · CVSS {text(finding.get('cvss') if finding.get('cvss') is not None else 'нет данных')}",
    ]
    epss = finding.get("epss")
    lines.append(f"EPSS: {epss:.2%}" if isinstance(epss, (int, float)) else "EPSS: нет данных")
    if finding.get("kev"):
        lines.append("CISA KEV: есть запись о подтверждённой эксплуатации.")
    lines.append(text(finding.get("summary", ""), 350))
    fixed = finding.get("fixed_versions") or []
    lines.append("Исправленные версии: " + (text(", ".join(map(str, fixed[:6])), 200) if fixed else "нет данных"))
    reasons = finding.get("priority_reasons") or []
    if reasons:
        lines.append("Причины приоритета: " + text("; ".join(map(str, reasons[:3])), 250))
    return "\n".join(lines)


def settings_summary(settings: dict[str, Any]) -> str:
    quiet = (
        f"{text(settings.get('quiet_start'))} до {text(settings.get('quiet_end'))}"
        if settings.get("quiet_start")
        else "выключены"
    )
    return "\n".join(
        [
            "<b>Настройки мониторинга</b>",
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
            "",
            f"Среда новых проектов: Python {text(settings.get('upload_python_version', '3.11'), 8)} / {text(settings.get('upload_platform', 'linux'), 10)}",
            "/environment 3.12 windows",
            "/privacy: данные, выгрузка и удаление аккаунта",
        ]
    )


def fix_summary(strategy: dict[str, Any], limitations: list[str]) -> str:
    lines = [
        f"<b>FixLab · {display_label(strategy.get('name', 'Вариант обновления'), STRATEGY_LABELS)}</b>",
        text(explanation(strategy.get("reason", "")), 400),
    ]
    lines.append(f"Статус: <code>{display_label(strategy.get('status'), STATUS_LABELS, 60)}</code>")
    updates = strategy.get("updates") or []
    for item in updates[:8]:
        if isinstance(item, dict):
            name = item.get("package", item.get("name", "?"))
            old = item.get("from", item.get("current", item.get("from_version", "?")))
            new = item.get("to", item.get("target", item.get("to_version", "?")))
            lines.append(f"• <code>{text(name, 90)}</code>: {text(old, 50)} → {text(new, 50)}")
    if len(updates) > 8:
        lines.append(f"Ещё обновлений: {len(updates) - 8}; полный список в JSON-файле.")
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
        lines.append("Ограничения: " + text("; ".join(map(explanation, limitations[:2])), 400))
    lines.append("Это модель обновления. Перед применением нужны тесты совместимости.")
    return "\n".join(lines)
