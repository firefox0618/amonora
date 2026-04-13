from __future__ import annotations

from dataclasses import dataclass

from bot.config import config


CONTROL_ROLE_OWNER = "owner"
CONTROL_ROLE_ADMIN = "admin"
CONTROL_ROLE_OPERATOR = "operator"
CONTROL_ROLE_SUPPORT_VIEW_ONLY = "support-view-only"
CONTROL_ROLE_TECH_ADMIN = CONTROL_ROLE_ADMIN
CONTROL_ROLE_MANAGER = CONTROL_ROLE_OPERATOR
CONTROL_ROLE_PRIORITY = {
    CONTROL_ROLE_SUPPORT_VIEW_ONLY: 0,
    CONTROL_ROLE_OPERATOR: 1,
    CONTROL_ROLE_ADMIN: 2,
    CONTROL_ROLE_OWNER: 3,
}
CONTROL_ROLE_LABELS = {
    CONTROL_ROLE_OWNER: "Владелец",
    CONTROL_ROLE_ADMIN: "Тех. администратор",
    CONTROL_ROLE_OPERATOR: "Менеджер",
    CONTROL_ROLE_SUPPORT_VIEW_ONLY: "Только просмотр",
}


@dataclass(frozen=True)
class ControlAdmin:
    telegram_id: int
    role: str


def _unique_ids(*groups: list[int]) -> list[int]:
    ordered: list[int] = []
    seen: set[int] = set()
    for group in groups:
        for item in group:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
    return ordered


def control_admins() -> list[ControlAdmin]:
    admins: list[ControlAdmin] = []
    for telegram_id in config.control_owner_ids:
        admins.append(ControlAdmin(telegram_id=telegram_id, role=CONTROL_ROLE_OWNER))
    for telegram_id in config.control_admin_ids:
        admins.append(ControlAdmin(telegram_id=telegram_id, role=CONTROL_ROLE_ADMIN))
    for telegram_id in config.control_operator_ids:
        admins.append(ControlAdmin(telegram_id=telegram_id, role=CONTROL_ROLE_OPERATOR))
    for telegram_id in config.control_support_view_only_ids:
        admins.append(ControlAdmin(telegram_id=telegram_id, role=CONTROL_ROLE_SUPPORT_VIEW_ONLY))

    if not admins and config.control_allowed_telegram_ids:
        admins.extend(
            ControlAdmin(telegram_id=telegram_id, role=CONTROL_ROLE_ADMIN)
            for telegram_id in config.control_allowed_telegram_ids
        )
    if not admins and config.admin_ids:
        admins.extend(
            ControlAdmin(telegram_id=telegram_id, role=CONTROL_ROLE_ADMIN)
            for telegram_id in _unique_ids(config.admin_ids, config.support_admin_ids)
        )
    return admins


def control_allowed_telegram_ids() -> list[int]:
    if config.control_allowed_telegram_ids:
        return _unique_ids(config.control_allowed_telegram_ids)
    if config.admin_ids:
        return _unique_ids(config.admin_ids, config.support_admin_ids)
    return _unique_ids([item.telegram_id for item in control_admins()])


def control_delivery_chat_ids() -> list[int]:
    return _unique_ids(config.control_chat_ids)


def control_role_for_telegram_id(telegram_id: int) -> str | None:
    for admin in control_admins():
        if admin.telegram_id == telegram_id:
            return admin.role
    if telegram_id in control_allowed_telegram_ids():
        return CONTROL_ROLE_ADMIN
    return None


def is_control_admin(telegram_id: int) -> bool:
    return control_role_for_telegram_id(telegram_id) is not None


def control_role_allows(role: str | None, minimum_role: str) -> bool:
    if role is None:
        return False
    return CONTROL_ROLE_PRIORITY.get(role, -1) >= CONTROL_ROLE_PRIORITY.get(minimum_role, 999)


def control_role_label(role: str | None) -> str:
    if role is None:
        return "Неизвестно"
    return CONTROL_ROLE_LABELS.get(role, role)
