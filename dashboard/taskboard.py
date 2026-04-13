"""
Доска задач — канбан с колонками.

CRUD задач, комментарии, статусы, drag-and-drop между колонками.
"""

import json
from datetime import datetime

from sqlalchemy import select

from backend.core.database import async_session
from dashboard.models import (
    DashboardAdmin,
    DashboardAuditLog,
    TaskBoard,
    TaskComment,
)

DEFAULT_COLUMNS = [
    {"id": "backlog", "name": "К выполнению", "color": "#3b82f6"},
    {"id": "in_progress", "name": "В работе", "color": "#f59e0b"},
    {"id": "testing", "name": "На тестирование", "color": "#8b5cf6"},
    {"id": "deferred", "name": "Отложено", "color": "#64748b"},
    {"id": "done", "name": "Реализовано", "color": "#22c55e"},
]

TASK_STATUS_LABELS = {c["id"]: c["name"] for c in DEFAULT_COLUMNS}
TASK_STATUS_COLORS = {c["id"]: c["color"] for c in DEFAULT_COLUMNS}


def _task_to_dict(task, comments=None):
    """Сериализация задачи в dict."""
    import json
    
    d = {
        "id": task.id,
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "status_label": TASK_STATUS_LABELS.get(task.status, task.status),
        "status_color": TASK_STATUS_COLORS.get(task.status, "#64748b"),
        "priority": task.priority or "medium",
        "due_date": task.due_date.strftime("%Y-%m-%d") if task.due_date else None,
        "assignee": task.assignee or "",
        "color": task.color or "#3b82f6",
        "created_at": task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else "",
        "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M") if task.updated_at else "",
    }
    
    if task.tags:
        try:
            d["tags"] = json.loads(task.tags)
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
    else:
        d["tags"] = []
    
    if task.checklist:
        try:
            d["checklist"] = json.loads(task.checklist)
        except (json.JSONDecodeError, TypeError):
            d["checklist"] = []
    else:
        d["checklist"] = []
    
    d["comments"] = []
    if comments:
        for c in comments:
            d["comments"].append({
                "text": c.text,
                "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
            })
    
    d["comments_count"] = len(d["comments"])
    d["checklist_done"] = sum(1 for item in d["checklist"] if item.get("done")) if d["checklist"] else 0
    d["checklist_total"] = len(d["checklist"])
    
    return d


async def get_kanban_data(
    search: str = "",
    assignee_filter: str = "",
    tag_filter: str = "",
    priority_filter: str = "",
) -> dict:
    """Полные данные для канбан-доски."""
    async with async_session() as session:
        query = select(TaskBoard).order_by(TaskBoard.updated_at.desc())
        result = await session.execute(query)
        tasks = result.scalars().all()
    
    # Filter
    filtered = []
    for task in tasks:
        if search and search.lower() not in task.title.lower() and search.lower() not in (task.description or "").lower():
            continue
        if assignee_filter and task.assignee != assignee_filter:
            continue
        if priority_filter and task.priority != priority_filter:
            continue
        if tag_filter:
            try:
                tags = json.loads(task.tags or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            if tag_filter not in tags:
                continue
        filtered.append(task)
    
    # Group by status
    columns = []
    for col in DEFAULT_COLUMNS:
        col_tasks = [t for t in filtered if t.status == col["id"]]
        comments_map = {}
        for t in col_tasks:
            async with async_session() as session:
                c_result = await session.execute(
                    select(TaskComment).where(TaskComment.task_id == t.id).order_by(TaskComment.created_at)
                )
                comments_map[t.id] = c_result.scalars().all()
        
        columns.append({
            "id": col["id"],
            "name": col["name"],
            "color": col["color"],
            "tasks": [_task_to_dict(t, comments_map.get(t.id, [])) for t in col_tasks],
        })
    
    # Get all unique assignees and tags
    all_assignees = set()
    all_tags = set()
    for task in tasks:
        if task.assignee:
            all_assignees.add(task.assignee)
        try:
            tags = json.loads(task.tags or "[]")
            all_tags.update(tags)
        except (json.JSONDecodeError, TypeError):
            pass
    
    return {
        "columns": columns,
        "assignees": sorted(all_assignees),
        "tags": sorted(all_tags),
    }


async def create_task(
    title: str,
    description: str = "",
    status: str = "backlog",
    priority: str = "medium",
    color: str = "#3b82f6",
    assignee: str = "",
    due_date: str = "",
    tags: list | None = None,
    admin: DashboardAdmin | None = None,
    ip_address: str | None = None,
) -> TaskBoard:
    """Создать задачу."""
    import json
    
    async with async_session() as session:
        task = TaskBoard(
            title=title.strip(),
            description=description.strip() if description else None,
            status=status,
            priority=priority,
            color=color,
            assignee=assignee,
            tags=json.dumps(tags) if tags else None,
            due_date=datetime.strptime(due_date, "%Y-%m-%d").date() if due_date else None,
            created_by_admin_id=admin.id if admin else None,
        )
        session.add(task)
        
        if admin:
            audit = DashboardAuditLog(
                admin_id=admin.id,
                action="create_task",
                target_type="task_board",
                target_id=str(task.id),
                details_text=title,
                ip_address=ip_address,
            )
            session.add(audit)
        
        await session.commit()
        await session.refresh(task)
    
    return task


async def update_task(
    task_id: int,
    data: dict,
    admin: DashboardAdmin,
    ip_address: str | None,
) -> TaskBoard | None:
    """Обновить задачу."""
    import json
    
    async with async_session() as session:
        result = await session.execute(select(TaskBoard).where(TaskBoard.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return None
        
        for key in ["title", "description", "status", "priority", "color", "assignee"]:
            if key in data and data[key] is not None:
                setattr(task, key, data[key])
        
        if "due_date" in data and data["due_date"]:
            task.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        
        if "tags" in data:
            task.tags = json.dumps(data["tags"]) if data["tags"] else None
        
        if "checklist" in data:
            task.checklist = json.dumps(data["checklist"]) if data["checklist"] else None
        
        task.updated_at = datetime.utcnow()
        
        audit = DashboardAuditLog(
            admin_id=admin.id,
            action="update_task",
            target_type="task_board",
            target_id=str(task_id),
            details_text=task.title,
            ip_address=ip_address,
        )
        session.add(audit)
        await session.commit()
        await session.refresh(task)
    
    return task


async def add_task_comment(
    task_id: int,
    text: str,
    admin: DashboardAdmin | None = None,
) -> TaskComment | None:
    """Добавить комментарий к задаче."""
    async with async_session() as session:
        result = await session.execute(select(TaskBoard).where(TaskBoard.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return None
        
        comment = TaskComment(
            task_id=task_id,
            admin_id=admin.id if admin else None,
            text=text.strip(),
        )
        session.add(comment)
        
        task.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(comment)
    
    return comment


async def delete_task(task_id: int, admin: DashboardAdmin, ip_address: str | None) -> bool:
    """Удалить задачу."""
    async with async_session() as session:
        result = await session.execute(select(TaskBoard).where(TaskBoard.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return False
        
        await session.execute(TaskComment.__table__.delete().where(TaskComment.task_id == task_id))
        await session.delete(task)
        
        audit = DashboardAuditLog(
            admin_id=admin.id,
            action="delete_task",
            target_type="task_board",
            target_id=str(task_id),
            details_text=task.title,
            ip_address=ip_address,
        )
        session.add(audit)
        await session.commit()
    
    return True
