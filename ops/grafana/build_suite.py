from __future__ import annotations

import json

from pathlib import Path


DASHBOARDS_DIR = Path(__file__).resolve().parent / "dashboards"
DATASOURCE = {"type": "postgres", "uid": "amonora-analytics"}
GRAPHITE = "#131A23"
SLATE = "#223042"
CYAN = "#52D6E5"
AMBER = "#F6B73C"
CORAL = "#FF6F61"
GREEN = "#3DD598"
# Keep Grafana template vars literal when they appear inside Python f-strings.
source_mode = "{source_mode}"
source_key = "{source_key}"
cohort_type = "{cohort_type}"
CONNECTION_STARTED_EVENTS = ("onboarding_started", "connection_started")
CONNECTION_READY_EVENTS = ("onboarding_completed", "connection_ready")
SOURCE_ORGANIC = "organic_bot"
PAYMENT_KIND_NEW = "new"
PAYMENT_KIND_RENEWAL = "renewal"
PAYMENT_KIND_OTHER = "other"


def sql_literal(value: str) -> str:
    return f"'{value}'"


def sql_in(values: tuple[str, ...] | list[str] | set[str]) -> str:
    return ", ".join(sql_literal(value) for value in values)


def event_condition(column: str, event_names: str | tuple[str, ...] | list[str] | set[str]) -> str:
    if isinstance(event_names, str):
        return f"{column} = {sql_literal(event_names)}"
    normalized = tuple(event_names)
    if len(normalized) == 1:
        return f"{column} = {sql_literal(normalized[0])}"
    return f"{column} IN ({sql_in(normalized)})"


def nav_links():
    items = [
        ("Главная Amonora", "amonora-home"),
        ("Воронка роста", "amonora-growth-funnel"),
        ("Источники и посты", "amonora-source-performance"),
        ("Выручка и монетизация", "amonora-revenue-monetization"),
        ("Удержание и отток", "amonora-retention-churn"),
        ("Качество подключения", "amonora-connection-quality"),
        ("Операции и ремонты", "amonora-ops-repair"),
        ("Алерты и инциденты", "amonora-alerts-incidents"),
    ]
    return [
        {
            "title": title,
            "type": "link",
            "url": (
                f"/d/{uid}"
                f"?var-source_mode=${source_mode}"
                f"&var-source_key=${source_key}"
                f"&var-cohort_type=${cohort_type}"
                f"&${{__url_time_range}}"
            ),
        }
        for title, uid in items
    ]


def source_mode_variable():
    return {
        "current": {"selected": True, "text": "Последний источник", "value": "last"},
        "hide": 0,
        "label": "Атрибуция",
        "name": "source_mode",
        "options": [
            {"selected": False, "text": "Первый источник", "value": "first"},
            {"selected": True, "text": "Последний источник", "value": "last"},
        ],
        "query": "first,last",
        "type": "custom",
    }


def source_key_variable():
    query = (
        "SELECT DISTINCT source_key "
        "FROM analytics_daily_stage_counts "
        "WHERE source_key IS NOT NULL AND BTRIM(source_key) <> '' "
        "ORDER BY 1"
    )
    return {
        "allValue": "__all",
        "current": {"selected": True, "text": "Все", "value": "__all"},
        "datasource": DATASOURCE,
        "definition": query,
        "hide": 0,
        "includeAll": True,
        "label": "Источник / start_param",
        "multi": False,
        "name": "source_key",
        "options": [],
        "query": query,
        "refresh": 1,
        "sort": 1,
        "type": "query",
    }


def cohort_variable():
    return {
        "current": {"selected": True, "text": "Первая платная активация", "value": "subscription_activated"},
        "hide": 0,
        "label": "Когорта",
        "name": "cohort_type",
        "options": [
            {"selected": False, "text": "Пробный старт", "value": "trial_started"},
            {"selected": True, "text": "Первая платная активация", "value": "subscription_activated"},
        ],
        "query": "trial_started,subscription_activated",
        "type": "custom",
    }


def source_key_filter(column: str = "source_key") -> str:
    return f"('${{source_key}}' = '__all' OR {column} = '${{source_key}}')"


def source_key_label(column: str = "source_key") -> str:
    return (
        f"CASE "
        f"WHEN {column} IS NULL OR BTRIM({column}) = '' THEN 'Без источника' "
        f"WHEN {column} = '{SOURCE_ORGANIC}' THEN 'Органика' "
        f"ELSE {column} END"
    )


def rate_expr(numerator: str, denominator: str) -> str:
    return f"ROUND(100.0 * ({numerator}) / NULLIF(({denominator}), 0), 2)"


def stage_total_sql(event_names: str | tuple[str, ...] | list[str] | set[str], *, alias: str = "value", filter_source_key: bool = True) -> str:
    source_key_where = f"\n  AND {source_key_filter()}" if filter_source_key else ""
    return f"""
SELECT COALESCE(SUM(users_count), 0)::bigint AS {alias}
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'{source_key_where}
  AND {event_condition('event_name', event_names)};
    """


def revenue_total_sql(*, alias: str = "value", filter_source_key: bool = True, payment_kinds: tuple[str, ...] | None = None) -> str:
    source_key_where = f"\n  AND {source_key_filter()}" if filter_source_key else ""
    payment_kind_where = f"\n  AND {event_condition('payment_kind', payment_kinds)}" if payment_kinds else ""
    return f"""
SELECT COALESCE(SUM(revenue_amount_rub), 0)::bigint AS {alias}
FROM analytics_daily_revenue
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'{source_key_where}{payment_kind_where};
    """


def source_key_links(target_uid: str = "amonora-source-performance"):
    return [
        {
            "title": "Открыть источник",
            "url": f"/d/{target_uid}?var-source_key=${{__value.raw}}&var-source_mode=${{source_mode}}&${{__url_time_range}}",
            "targetBlank": False,
        }
    ]


def source_key_overrides(field_name: str = "Источник / start_param", *, target_uid: str = "amonora-source-performance"):
    return [
        {
            "matcher": {"id": "byName", "options": field_name},
            "properties": [{"id": "links", "value": source_key_links(target_uid)}],
        }
    ]


def text_panel(panel_id: int, title: str, markdown: str, *, x: int, y: int, w: int, h: int):
    return {
        "datasource": None,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_id,
        "options": {"content": markdown, "mode": "markdown"},
        "title": title,
        "type": "text",
    }


def row_panel(panel_id: int, title: str, *, y: int):
    return {
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
        "id": panel_id,
        "panels": [],
        "title": title,
        "type": "row",
    }


def stat_panel(
    panel_id: int,
    title: str,
    sql: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int = 5,
    unit: str = "none",
    thresholds=None,
    description: str = "",
    color_mode: str = "background",
):
    return {
        "datasource": DATASOURCE,
        "description": description,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": thresholds
                    or [
                        {"color": GRAPHITE, "value": None},
                        {"color": CYAN, "value": 1},
                        {"color": GREEN, "value": 10},
                    ],
                },
                "unit": unit,
            },
            "overrides": [],
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_id,
        "options": {
            "colorMode": color_mode,
            "graphMode": "none",
            "justifyMode": "center",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "value",
            "wideLayout": True,
        },
        "targets": [
            {
                "editorMode": "code",
                "format": "table",
                "rawQuery": True,
                "rawSql": sql.strip(),
                "refId": "A",
            }
        ],
        "title": title,
        "type": "stat",
    }


def table_panel(
    panel_id: int,
    title: str,
    sql: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    description: str = "",
    overrides=None,
):
    return {
        "datasource": DATASOURCE,
        "description": description,
        "fieldConfig": {"defaults": {}, "overrides": overrides or []},
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_id,
        "options": {"footer": {"show": False}, "showHeader": True},
        "targets": [
            {
                "editorMode": "code",
                "format": "table",
                "rawQuery": True,
                "rawSql": sql.strip(),
                "refId": "A",
            }
        ],
        "title": title,
        "type": "table",
    }


def timeseries_panel(
    panel_id: int,
    title: str,
    sql: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    unit: str = "none",
    description: str = "",
):
    return {
        "datasource": DATASOURCE,
        "description": description,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisBorderShow": False,
                    "drawStyle": "line",
                    "lineInterpolation": "smooth",
                    "lineWidth": 2,
                },
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": CYAN, "value": None},
                        {"color": AMBER, "value": 1},
                        {"color": CORAL, "value": 5},
                    ],
                },
                "unit": unit,
            },
            "overrides": [],
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_id,
        "options": {
            "legend": {"displayMode": "table", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
        "targets": [
            {
                "editorMode": "code",
                "format": "time_series",
                "rawQuery": True,
                "rawSql": sql.strip(),
                "refId": "A",
            }
        ],
        "title": title,
        "type": "timeseries",
    }


def dashboard(title: str, uid: str, *, tags, time_from: str, panels, variables=None):
    return {
        "annotations": {"list": []},
        "editable": False,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": nav_links(),
        "panels": panels,
        "refresh": "5m",
        "schemaVersion": 39,
        "style": "dark",
        "tags": tags,
        "templating": {"list": variables or []},
        "time": {"from": time_from, "to": "now"},
        "timezone": "",
        "title": title,
        "uid": uid,
        "version": 1,
        "weekStart": "",
    }


def funnel_cte(*, filter_source_key: bool = True) -> str:
    source_key_where = f"\n    AND {source_key_filter()}" if filter_source_key else ""
    return f"""
WITH funnel AS (
  SELECT 1 AS step_order, 'link_touched' AS stage_key, 'Переход по ссылке' AS stage_name,
         COALESCE(SUM(users_count), 0)::bigint AS total
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND event_name = 'link_touched'
  UNION ALL
  SELECT 2, 'bot_start', 'Старт в боте',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND event_name = 'bot_start'
  UNION ALL
  SELECT 3, 'channel_membership_confirmed', 'Подтвердили подписку',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND event_name = 'channel_membership_confirmed'
  UNION ALL
  SELECT 4, 'connection_started', 'Начало подключения',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND {event_condition('event_name', CONNECTION_STARTED_EVENTS)}
  UNION ALL
  SELECT 5, 'connection_ready', 'Готов к подключению',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND {event_condition('event_name', CONNECTION_READY_EVENTS)}
  UNION ALL
  SELECT 6, 'config_issued', 'Ключ / конфиг выдан',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND event_name = 'config_issued'
  UNION ALL
  SELECT 7, 'subscription_payment_started', 'Оплата начата',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND event_name = 'subscription_payment_started'
  UNION ALL
  SELECT 8, 'subscription_payment_success', 'Оплата успешна',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND {event_condition('event_name', ('subscription_activated', 'subscription_renewed'))}
  UNION ALL
  SELECT 9, 'first_connection_success', 'Первое подключение',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND event_name = 'first_connection_success'
  UNION ALL
  SELECT 10, 'subscription_renewed', 'Продление',
         COALESCE(SUM(users_count), 0)::bigint
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'{source_key_where}
    AND event_name = 'subscription_renewed'
),
ranked AS (
  SELECT *,
         LAG(total) OVER (ORDER BY step_order) AS previous_total,
         MAX(CASE WHEN step_order = 1 THEN total END) OVER () AS funnel_start
  FROM funnel
)
"""


def build_home():
    panels = [
        row_panel(1, "Ключевые показатели", y=0),
        stat_panel(2, "Переходы по ссылке", stage_total_sql("link_touched"), x=0, y=1, w=6, h=4),
        stat_panel(3, "Старт в боте", stage_total_sql("bot_start"), x=6, y=1, w=6, h=4),
        stat_panel(4, "Подтвердили подписку", stage_total_sql("channel_membership_confirmed"), x=12, y=1, w=6, h=4),
        stat_panel(5, "Ключ / конфиг выдан", stage_total_sql("config_issued"), x=18, y=1, w=6, h=4),
        stat_panel(6, "Успешные оплаты", stage_total_sql(("subscription_activated", "subscription_renewed")), x=0, y=5, w=6, h=4),
        stat_panel(7, "Первые подключения", stage_total_sql("first_connection_success"), x=6, y=5, w=6, h=4),
        stat_panel(8, "Продления", stage_total_sql("subscription_renewed"), x=12, y=5, w=6, h=4),
        stat_panel(9, "Выручка", revenue_total_sql(payment_kinds=(PAYMENT_KIND_NEW, PAYMENT_KIND_RENEWAL)), x=18, y=5, w=6, h=4, unit="currencyRUB"),
        stat_panel(
            10,
            "Конверсия в оплату, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name = 'bot_start' THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'
  AND {source_key_filter()}
  AND event_name IN ('bot_start','subscription_activated','subscription_renewed');
            """,
            x=0,
            y=9,
            w=6,
            h=4,
            unit="percent",
        ),
        stat_panel(
            11,
            "Конверсия в подключение, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'
  AND {source_key_filter()}
  AND event_name IN ('subscription_activated','subscription_renewed','first_connection_success');
            """,
            x=6,
            y=9,
            w=6,
            h=4,
            unit="percent",
        ),
        stat_panel(
            12,
            "Разрыв оплата → подключение",
            f"""
WITH gap AS (
  SELECT
    COALESCE(SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END), 0)::bigint AS paid,
    COALESCE(SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END), 0)::bigint AS connected
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'
    AND {source_key_filter()}
    AND event_name IN ('subscription_activated','subscription_renewed','first_connection_success')
)
SELECT GREATEST(paid - connected, 0)::bigint AS value
FROM gap;
            """,
            x=12,
            y=9,
            w=6,
            h=4,
        ),
        stat_panel(
            13,
            "Активные подписки",
            """
SELECT COALESCE((detail_json::json ->> 'active_users')::integer, 0) AS value
FROM analytics_runtime_status
WHERE status_key = 'growth_active_users'
ORDER BY updated_at DESC
LIMIT 1;
            """,
            x=18,
            y=9,
            w=6,
            h=4,
        ),
        row_panel(14, "Обзор окна", y=13),
        table_panel(
            15,
            "Короткая воронка",
            f"""
{funnel_cte()}
SELECT stage_name AS "Этап",
       total AS "Пользователи",
       {rate_expr("total", "funnel_start")} AS "% от начала"
FROM ranked
WHERE step_order IN (1, 2, 3, 6, 8, 9, 10)
ORDER BY step_order;
            """,
            x=0,
            y=14,
            w=10,
            h=9,
            description="Короткий executive-срез без детальной простыни.",
        ),
        table_panel(
            16,
            "Сегодня / 7д / 30д",
            """
WITH windows AS (
  SELECT 'Сегодня' AS window_name, CURRENT_DATE AS starts_at
  UNION ALL
  SELECT '7д', CURRENT_DATE - INTERVAL '6 day'
  UNION ALL
  SELECT '30д', CURRENT_DATE - INTERVAL '29 day'
),
stage AS (
  SELECT
    windows.window_name,
    stage.event_name,
    SUM(stage.users_count)::bigint AS users_count
  FROM windows
  LEFT JOIN analytics_daily_stage_counts stage
    ON stage.bucket_date >= windows.starts_at
   AND stage.source_mode = '${source_mode}'
   AND ('${source_key}' = '__all' OR stage.source_key = '${source_key}')
   AND stage.event_name IN ('link_touched','bot_start','channel_membership_confirmed','config_issued','subscription_activated','subscription_renewed','first_connection_success')
  GROUP BY windows.window_name, stage.event_name
),
revenue AS (
  SELECT
    windows.window_name,
    COALESCE(SUM(revenue.revenue_amount_rub), 0)::bigint AS revenue_rub
  FROM windows
  LEFT JOIN analytics_daily_revenue revenue
    ON revenue.bucket_date >= windows.starts_at
   AND revenue.source_mode = '${source_mode}'
   AND ('${source_key}' = '__all' OR revenue.source_key = '${source_key}')
   AND revenue.payment_kind IN ('new', 'renewal')
  GROUP BY windows.window_name
)
SELECT
  stage.window_name AS "Окно",
  SUM(CASE WHEN event_name = 'link_touched' THEN users_count ELSE 0 END)::bigint AS "Переходы",
  SUM(CASE WHEN event_name = 'bot_start' THEN users_count ELSE 0 END)::bigint AS "Старты",
  SUM(CASE WHEN event_name = 'channel_membership_confirmed' THEN users_count ELSE 0 END)::bigint AS "Подписки",
  SUM(CASE WHEN event_name = 'config_issued' THEN users_count ELSE 0 END)::bigint AS "Ключи",
  SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)::bigint AS "Оплаты",
  SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END)::bigint AS "Подключения",
  SUM(CASE WHEN event_name = 'subscription_renewed' THEN users_count ELSE 0 END)::bigint AS "Продления",
  COALESCE(revenue.revenue_rub, 0)::bigint AS "Выручка, ₽"
FROM stage
LEFT JOIN revenue ON revenue.window_name = stage.window_name
GROUP BY stage.window_name, revenue.revenue_rub
ORDER BY CASE stage.window_name WHEN 'Сегодня' THEN 1 WHEN '7д' THEN 2 ELSE 3 END;
            """,
            x=10,
            y=14,
            w=14,
            h=9,
        ),
        row_panel(17, "Контроль", y=23),
        stat_panel(
            18,
            "Целостность атрибуции",
            """
SELECT ROUND(COALESCE((detail_json::json ->> 'integrity_ratio')::numeric, 1.0) * 100, 2) AS value
FROM analytics_runtime_status
WHERE status_key = 'source_key_integrity'
ORDER BY updated_at DESC
LIMIT 1;
            """,
            x=0,
            y=24,
            w=6,
            h=4,
            unit="percent",
        ),
        table_panel(
            19,
            "Свежесть данных",
            """
SELECT
  CASE status_key
    WHEN 'analytics_refresh' THEN 'Обновление аналитики'
    WHEN 'restore_proof' THEN 'Проверка restore'
    WHEN 'source_key_integrity' THEN 'Целостность source_key'
    WHEN 'growth_active_users' THEN 'Активные подписки'
    WHEN 'repair_open' THEN 'Открытые ремонты'
    WHEN 'open_incidents' THEN 'Открытые инциденты'
    ELSE status_key
  END AS "Показатель",
  status_value AS "Статус",
  observed_at AS "Наблюдалось",
  updated_at AS "Обновлено"
FROM analytics_runtime_status
ORDER BY updated_at DESC
LIMIT 12;
            """,
            x=6,
            y=24,
            w=10,
            h=8,
        ),
        table_panel(
            20,
            "Активные алерты",
            """
SELECT
  bucket_hour AS "Срез",
  repair_needed_open_count AS "Открытые ремонты",
  unresolved_incident_count AS "Инциденты",
  unresolved_warning_count AS "Предупреждения",
  unresolved_critical_count AS "Критические",
  provisioning_failure_events_24h AS "Provisioning 24ч",
  reconcile_failure_events_24h AS "Reconcile 24ч"
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 8;
            """,
            x=16,
            y=24,
            w=8,
            h=8,
        ),
    ]
    return dashboard(
        "Главная Amonora",
        "amonora-home",
        tags=["analytics", "home", "owner", "stage-b"],
        time_from="now-30d",
        panels=panels,
        variables=[source_mode_variable(), source_key_variable()],
    )


def build_growth():
    panels = [
        row_panel(1, "Ключевые показатели", y=0),
        stat_panel(2, "Переходы", stage_total_sql("link_touched"), x=0, y=1, w=4, h=4),
        stat_panel(3, "Старты", stage_total_sql("bot_start"), x=4, y=1, w=4, h=4),
        stat_panel(4, "Подписки", stage_total_sql("channel_membership_confirmed"), x=8, y=1, w=4, h=4),
        stat_panel(5, "Ключ выдан", stage_total_sql("config_issued"), x=12, y=1, w=4, h=4),
        stat_panel(6, "Успешные оплаты", stage_total_sql(("subscription_activated", "subscription_renewed")), x=16, y=1, w=4, h=4),
        stat_panel(7, "Первые подключения", stage_total_sql("first_connection_success"), x=20, y=1, w=4, h=4),
        stat_panel(8, "Продления", stage_total_sql("subscription_renewed"), x=0, y=5, w=4, h=4),
        stat_panel(9, "Выручка", revenue_total_sql(payment_kinds=(PAYMENT_KIND_NEW, PAYMENT_KIND_RENEWAL)), x=4, y=5, w=4, h=4, unit="currencyRUB"),
        stat_panel(
            10,
            "Конверсия в оплату, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name = 'bot_start' THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'
  AND {source_key_filter()}
  AND event_name IN ('bot_start','subscription_activated','subscription_renewed');
            """,
            x=8,
            y=5,
            w=4,
            h=4,
            unit="percent",
        ),
        stat_panel(
            11,
            "Конверсия в подключение, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'
  AND {source_key_filter()}
  AND event_name IN ('subscription_activated','subscription_renewed','first_connection_success');
            """,
            x=12,
            y=5,
            w=4,
            h=4,
            unit="percent",
        ),
        stat_panel(
            12,
            "Разрыв оплата → подключение",
            f"""
WITH gap AS (
  SELECT
    COALESCE(SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END), 0)::bigint AS paid,
    COALESCE(SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END), 0)::bigint AS connected
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'
    AND {source_key_filter()}
    AND event_name IN ('subscription_activated','subscription_renewed','first_connection_success')
)
SELECT GREATEST(paid - connected, 0)::bigint AS value
FROM gap;
            """,
            x=16,
            y=5,
            w=4,
            h=4,
        ),
        stat_panel(
            13,
            "Разрыв, %",
            f"""
WITH gap AS (
  SELECT
    COALESCE(SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END), 0)::bigint AS paid,
    COALESCE(SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END), 0)::bigint AS connected
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'
    AND {source_key_filter()}
    AND event_name IN ('subscription_activated','subscription_renewed','first_connection_success')
)
SELECT {rate_expr("GREATEST(paid - connected, 0)", "paid")} AS value
FROM gap;
            """,
            x=20,
            y=5,
            w=4,
            h=4,
            unit="percent",
        ),
        row_panel(14, "Воронка подключения", y=9),
        table_panel(
            15,
            "Воронка подключения",
            f"""
{funnel_cte()}
SELECT stage_name AS "Этап",
       total AS "Пользователи",
       {rate_expr("total", "COALESCE(previous_total, total)")} AS "% от предыдущего",
       {rate_expr("total", "funnel_start")} AS "% от начала"
FROM ranked
ORDER BY step_order;
            """,
            x=0,
            y=10,
            w=24,
            h=11,
        ),
        row_panel(16, "Потери по этапам", y=21),
        table_panel(
            17,
            "Потери по этапам",
            f"""
{funnel_cte()}
SELECT stage_name AS "Этап",
       COALESCE(previous_total, total) AS "Было на шаге выше",
       total AS "Дошло до шага",
       GREATEST(COALESCE(previous_total, total) - total, 0) AS "Потеря",
       {rate_expr("GREATEST(COALESCE(previous_total, total) - total, 0)", "COALESCE(previous_total, total)")} AS "Потеря, %"
FROM ranked
WHERE step_order > 1
ORDER BY step_order;
            """,
            x=0,
            y=22,
            w=24,
            h=10,
        ),
        row_panel(18, "Источники", y=32),
        table_panel(
            19,
            "Источники",
            """
WITH stage AS (
  SELECT
    source_mode,
    source_key,
    SUM(CASE WHEN event_name = 'link_touched' THEN users_count ELSE 0 END)::bigint AS link_touched,
    SUM(CASE WHEN event_name = 'bot_start' THEN users_count ELSE 0 END)::bigint AS bot_start,
    SUM(CASE WHEN event_name = 'channel_membership_confirmed' THEN users_count ELSE 0 END)::bigint AS channel_membership_confirmed,
    SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)::bigint AS payment_success,
    SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END)::bigint AS first_connection_success,
    SUM(CASE WHEN event_name = 'subscription_renewed' THEN users_count ELSE 0 END)::bigint AS subscription_renewed
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${source_mode}'
    AND ('${source_key}' = '__all' OR source_key = '${source_key}')
    AND event_name IN ('link_touched','bot_start','channel_membership_confirmed','subscription_activated','subscription_renewed','first_connection_success')
  GROUP BY source_mode, source_key
),
revenue AS (
  SELECT
    source_mode,
    source_key,
    SUM(revenue_amount_rub)::bigint AS revenue_rub
  FROM analytics_daily_revenue
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${source_mode}'
    AND ('${source_key}' = '__all' OR source_key = '${source_key}')
    AND payment_kind IN ('new', 'renewal')
  GROUP BY source_mode, source_key
)
SELECT
  CASE stage.source_mode WHEN 'first' THEN 'Первый источник' ELSE 'Последний источник' END AS "Режим источника",
  """
            + source_key_label("stage.source_key")
            + """ AS "Источник / start_param",
  stage.link_touched AS "Переходы",
  stage.bot_start AS "Старты",
  stage.channel_membership_confirmed AS "Подтверждённые подписки",
  stage.payment_success AS "Оплаты",
  stage.first_connection_success AS "Первые подключения",
  stage.subscription_renewed AS "Продления",
  COALESCE(revenue.revenue_rub, 0)::bigint AS "Выручка, ₽",
  """
            + rate_expr("stage.payment_success", "stage.bot_start")
            + """ AS "Конверсия в оплату, %",
  """
            + rate_expr("stage.first_connection_success", "stage.bot_start")
            + """ AS "Конверсия в подключение, %"
FROM stage
LEFT JOIN revenue
  ON revenue.source_mode = stage.source_mode
 AND revenue.source_key = stage.source_key
ORDER BY "Выручка, ₽" DESC, "Оплаты" DESC
LIMIT 40;
            """,
            x=0,
            y=33,
            w=24,
            h=11,
            overrides=source_key_overrides(),
        ),
        row_panel(20, "Платежи и выручка", y=44),
        stat_panel(21, "Оплата начата", stage_total_sql("subscription_payment_started"), x=0, y=45, w=4, h=4),
        stat_panel(22, "Оплата успешна", stage_total_sql(("subscription_activated", "subscription_renewed")), x=4, y=45, w=4, h=4),
        stat_panel(23, "Оплата неуспешна", stage_total_sql("subscription_payment_failed"), x=8, y=45, w=4, h=4),
        stat_panel(
            24,
            "Успех оплаты, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name = 'subscription_payment_started' THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND {source_key_filter()}
  AND event_name IN ('subscription_payment_started','subscription_activated','subscription_renewed');
            """,
            x=12,
            y=45,
            w=4,
            h=4,
            unit="percent",
        ),
        stat_panel(
            25,
            "Неуспех оплаты, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name = 'subscription_payment_failed' THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name = 'subscription_payment_started' THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND {source_key_filter()}
  AND event_name IN ('subscription_payment_started','subscription_payment_failed');
            """,
            x=16,
            y=45,
            w=4,
            h=4,
            unit="percent",
        ),
        stat_panel(26, "Новые оплаты", stage_total_sql("subscription_activated"), x=20, y=45, w=4, h=4),
        stat_panel(27, "Продления", stage_total_sql("subscription_renewed"), x=0, y=49, w=4, h=4),
        stat_panel(28, "Выручка новых", revenue_total_sql(payment_kinds=(PAYMENT_KIND_NEW,)), x=4, y=49, w=4, h=4, unit="currencyRUB"),
        stat_panel(29, "Выручка продлений", revenue_total_sql(payment_kinds=(PAYMENT_KIND_RENEWAL,)), x=8, y=49, w=4, h=4, unit="currencyRUB"),
        stat_panel(30, "Общая выручка", revenue_total_sql(payment_kinds=(PAYMENT_KIND_NEW, PAYMENT_KIND_RENEWAL)), x=12, y=49, w=4, h=4, unit="currencyRUB"),
        table_panel(
            31,
            "Причины неуспешной оплаты",
            f"""
SELECT
  CASE reason_key
    WHEN 'manual_rejected' THEN 'Ручное отклонение'
    WHEN 'expired' THEN 'Истекла'
    WHEN 'provider_error' THEN 'Ошибка провайдера'
    WHEN 'rejected' THEN 'Отклонена'
    ELSE 'Неизвестно'
  END AS "Причина ошибки",
  SUM(failures_count)::bigint AS "Количество"
FROM analytics_daily_payment_failure_reasons
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'
  AND {source_key_filter()}
GROUP BY reason_key
ORDER BY "Количество" DESC, "Причина ошибки"
LIMIT 20;
            """,
            x=16,
            y=49,
            w=8,
            h=8,
        ),
        row_panel(32, "Качество данных", y=57),
        table_panel(
            33,
            "Целостность атрибуции",
            """
WITH issues AS (
  SELECT issue_type, SUM(issue_count)::bigint AS issue_count
  FROM analytics_daily_attribution_integrity
  WHERE $__timeFilter(bucket_date::timestamp)
  GROUP BY issue_type
),
total AS (
  SELECT COALESCE(SUM(users_count), 0)::bigint AS total_bot_start
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${source_mode}'
    AND event_name = 'bot_start'
)
SELECT
  CASE issue_type
    WHEN 'null_source_key' THEN 'NULL source_key'
    WHEN 'empty_source_key' THEN 'Пустой source_key'
    WHEN 'organic_bot' THEN 'Органика'
    WHEN 'invalid_start_param' THEN 'Битый start_param'
    ELSE 'События без атрибуции'
  END AS "Тип проблемы",
  issue_count AS "Количество",
  """
            + rate_expr("issue_count", "(SELECT total_bot_start FROM total)")
            + """ AS "Доля, %"
FROM issues
ORDER BY "Количество" DESC, "Тип проблемы";
            """,
            x=0,
            y=58,
            w=24,
            h=8,
        ),
    ]
    return dashboard(
        "Воронка роста",
        "amonora-growth-funnel",
        tags=["analytics", "growth", "stage-b", "strict"],
        time_from="now-30d",
        panels=panels,
        variables=[source_mode_variable(), source_key_variable()],
    )


def build_source_performance():
    panels = [
        row_panel(1, "Ключевые показатели", y=0),
        stat_panel(2, "Переходы", stage_total_sql("link_touched"), x=0, y=1, w=4, h=4),
        stat_panel(3, "Старты", stage_total_sql("bot_start"), x=4, y=1, w=4, h=4),
        stat_panel(4, "Подписки", stage_total_sql("channel_membership_confirmed"), x=8, y=1, w=4, h=4),
        stat_panel(5, "Оплаты", stage_total_sql(("subscription_activated", "subscription_renewed")), x=12, y=1, w=4, h=4),
        stat_panel(6, "Подключения", stage_total_sql("first_connection_success"), x=16, y=1, w=4, h=4),
        stat_panel(7, "Выручка", revenue_total_sql(payment_kinds=(PAYMENT_KIND_NEW, PAYMENT_KIND_RENEWAL)), x=20, y=1, w=4, h=4, unit="currencyRUB"),
        row_panel(8, "Источники", y=5),
        table_panel(
            9,
            "Источники",
            """
WITH stage AS (
  SELECT
    source_key,
    SUM(CASE WHEN event_name = 'link_touched' THEN users_count ELSE 0 END)::bigint AS link_touched,
    SUM(CASE WHEN event_name = 'bot_start' THEN users_count ELSE 0 END)::bigint AS bot_start,
    SUM(CASE WHEN event_name = 'channel_membership_confirmed' THEN users_count ELSE 0 END)::bigint AS channel_membership_confirmed,
    SUM(CASE WHEN event_name = 'config_issued' THEN users_count ELSE 0 END)::bigint AS config_issued,
    SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)::bigint AS payment_success,
    SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END)::bigint AS first_connection_success,
    SUM(CASE WHEN event_name = 'subscription_renewed' THEN users_count ELSE 0 END)::bigint AS subscription_renewed
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${source_mode}'
    AND ('${source_key}' = '__all' OR source_key = '${source_key}')
    AND event_name IN ('link_touched','bot_start','channel_membership_confirmed','config_issued','subscription_activated','subscription_renewed','first_connection_success')
  GROUP BY source_key
),
revenue AS (
  SELECT
    source_key,
    SUM(revenue_amount_rub)::bigint AS revenue_rub
  FROM analytics_daily_revenue
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${source_mode}'
    AND ('${source_key}' = '__all' OR source_key = '${source_key}')
    AND payment_kind IN ('new', 'renewal')
  GROUP BY source_key
)
SELECT
  """
            + source_key_label("stage.source_key")
            + """ AS "Источник / start_param",
  stage.link_touched AS "Переходы",
  stage.bot_start AS "Старты",
  stage.channel_membership_confirmed AS "Подписки",
  stage.config_issued AS "Ключ выдан",
  stage.payment_success AS "Оплаты",
  stage.first_connection_success AS "Подключения",
  stage.subscription_renewed AS "Продления",
  COALESCE(revenue.revenue_rub, 0)::bigint AS "Выручка, ₽",
  """
            + rate_expr("stage.payment_success", "stage.bot_start")
            + """ AS "Конверсия в оплату, %",
  """
            + rate_expr("stage.first_connection_success", "stage.bot_start")
            + """ AS "Конверсия в подключение, %"
FROM stage
LEFT JOIN revenue ON revenue.source_key = stage.source_key
ORDER BY "Выручка, ₽" DESC, "Оплаты" DESC
LIMIT 40;
            """,
            x=0,
            y=6,
            w=24,
            h=12,
            overrides=source_key_overrides(),
        ),
        row_panel(10, "Посты и CTA", y=18),
        table_panel(
            11,
            "Посты и CTA",
            """
WITH stage AS (
  SELECT
    content_type,
    channel_item_id,
    source_key,
    SUM(CASE WHEN event_name = 'link_touched' THEN users_count ELSE 0 END)::bigint AS link_touched,
    SUM(CASE WHEN event_name = 'bot_start' THEN users_count ELSE 0 END)::bigint AS bot_start,
    SUM(CASE WHEN event_name = 'config_issued' THEN users_count ELSE 0 END)::bigint AS config_issued,
    SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)::bigint AS payment_success,
    SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END)::bigint AS first_connection_success,
    SUM(CASE WHEN event_name = 'subscription_renewed' THEN users_count ELSE 0 END)::bigint AS subscription_renewed
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${source_mode}'
    AND ('${source_key}' = '__all' OR source_key = '${source_key}')
    AND event_name IN ('link_touched','bot_start','config_issued','subscription_activated','subscription_renewed','first_connection_success')
  GROUP BY content_type, channel_item_id, source_key
),
revenue AS (
  SELECT
    source_key,
    channel_item_id,
    SUM(revenue_amount_rub)::bigint AS revenue_rub
  FROM analytics_daily_revenue
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${source_mode}'
    AND ('${source_key}' = '__all' OR source_key = '${source_key}')
    AND payment_kind IN ('new', 'renewal')
  GROUP BY source_key, channel_item_id
)
SELECT
  COALESCE(content_type, '—') AS "Тип контента",
  CASE WHEN channel_item_id IS NULL THEN '—' ELSE CONCAT('Пост #', channel_item_id::text) END AS "Пост",
  """
            + source_key_label("stage.source_key")
            + """ AS "Источник / start_param",
  stage.link_touched AS "Переходы",
  stage.bot_start AS "Старты",
  stage.config_issued AS "Ключи",
  stage.payment_success AS "Оплаты",
  stage.first_connection_success AS "Подключения",
  stage.subscription_renewed AS "Продления",
  COALESCE(revenue.revenue_rub, 0)::bigint AS "Выручка, ₽",
  """
            + rate_expr("stage.payment_success", "stage.bot_start")
            + """ AS "Конверсия в оплату, %",
  """
            + rate_expr("stage.first_connection_success", "stage.bot_start")
            + """ AS "Конверсия в подключение, %"
FROM stage
LEFT JOIN revenue
  ON revenue.source_key = stage.source_key
 AND revenue.channel_item_id IS NOT DISTINCT FROM stage.channel_item_id
ORDER BY "Выручка, ₽" DESC, "Оплаты" DESC, "Переходы" DESC
LIMIT 40;
            """,
            x=0,
            y=19,
            w=24,
            h=12,
            overrides=source_key_overrides(),
        ),
    ]
    return dashboard(
        "Источники и посты",
        "amonora-source-performance",
        tags=["analytics", "growth", "sources", "stage-b", "strict"],
        time_from="now-30d",
        panels=panels,
        variables=[source_mode_variable(), source_key_variable()],
    )


def build_revenue():
    panels = [
        row_panel(1, "Ключевые показатели", y=0),
        stat_panel(2, "Оплата начата", stage_total_sql("subscription_payment_started"), x=0, y=1, w=4, h=4),
        stat_panel(3, "Оплата успешна", stage_total_sql(("subscription_activated", "subscription_renewed")), x=4, y=1, w=4, h=4),
        stat_panel(4, "Оплата неуспешна", stage_total_sql("subscription_payment_failed"), x=8, y=1, w=4, h=4),
        stat_panel(
            5,
            "Успех оплаты, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name = 'subscription_payment_started' THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND {source_key_filter()}
  AND event_name IN ('subscription_payment_started','subscription_activated','subscription_renewed');
            """,
            x=12,
            y=1,
            w=4,
            h=4,
            unit="percent",
        ),
        stat_panel(
            6,
            "Неуспех оплаты, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name = 'subscription_payment_failed' THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name = 'subscription_payment_started' THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND {source_key_filter()}
  AND event_name IN ('subscription_payment_started','subscription_payment_failed');
            """,
            x=16,
            y=1,
            w=4,
            h=4,
            unit="percent",
        ),
        stat_panel(7, "Общая выручка", revenue_total_sql(payment_kinds=(PAYMENT_KIND_NEW, PAYMENT_KIND_RENEWAL)), x=20, y=1, w=4, h=4, unit="currencyRUB"),
        stat_panel(8, "Новые оплаты", stage_total_sql("subscription_activated"), x=0, y=5, w=5, h=4),
        stat_panel(9, "Продления", stage_total_sql("subscription_renewed"), x=5, y=5, w=5, h=4),
        stat_panel(10, "Выручка новых", revenue_total_sql(payment_kinds=(PAYMENT_KIND_NEW,)), x=10, y=5, w=5, h=4, unit="currencyRUB"),
        stat_panel(11, "Выручка продлений", revenue_total_sql(payment_kinds=(PAYMENT_KIND_RENEWAL,)), x=15, y=5, w=5, h=4, unit="currencyRUB"),
        stat_panel(12, "Всего оплат", stage_total_sql(("subscription_activated", "subscription_renewed")), x=20, y=5, w=4, h=4),
        row_panel(13, "Платежи и выручка", y=9),
        table_panel(
            14,
            "Платежи и выручка",
            """
SELECT
  'Новые оплаты' AS "Показатель",
  COALESCE(SUM(CASE WHEN event_name = 'subscription_activated' THEN users_count ELSE 0 END), 0)::bigint AS "Количество",
  COALESCE((
    SELECT SUM(revenue_amount_rub)::bigint
    FROM analytics_daily_revenue revenue
    WHERE $__timeFilter(revenue.bucket_date::timestamp)
      AND revenue.source_mode = '${source_mode}'
      AND ('${source_key}' = '__all' OR revenue.source_key = '${source_key}')
      AND revenue.payment_kind = 'new'
  ), 0)::bigint AS "Выручка, ₽"
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
  AND event_name = 'subscription_activated'
UNION ALL
SELECT
  'Продления',
  COALESCE(SUM(CASE WHEN event_name = 'subscription_renewed' THEN users_count ELSE 0 END), 0)::bigint,
  COALESCE((
    SELECT SUM(revenue_amount_rub)::bigint
    FROM analytics_daily_revenue revenue
    WHERE $__timeFilter(revenue.bucket_date::timestamp)
      AND revenue.source_mode = '${source_mode}'
      AND ('${source_key}' = '__all' OR revenue.source_key = '${source_key}')
      AND revenue.payment_kind = 'renewal'
  ), 0)::bigint
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
  AND event_name = 'subscription_renewed'
UNION ALL
SELECT
  'Итого',
  COALESCE(SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END), 0)::bigint,
  COALESCE((
    SELECT SUM(revenue_amount_rub)::bigint
    FROM analytics_daily_revenue revenue
    WHERE $__timeFilter(revenue.bucket_date::timestamp)
      AND revenue.source_mode = '${source_mode}'
      AND ('${source_key}' = '__all' OR revenue.source_key = '${source_key}')
      AND revenue.payment_kind IN ('new', 'renewal')
  ), 0)::bigint
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
  AND event_name IN ('subscription_activated','subscription_renewed');
            """,
            x=0,
            y=10,
            w=8,
            h=9,
        ),
        table_panel(
            15,
            "Причины неуспешной оплаты",
            f"""
SELECT
  CASE reason_key
    WHEN 'manual_rejected' THEN 'Ручное отклонение'
    WHEN 'expired' THEN 'Истекла'
    WHEN 'provider_error' THEN 'Ошибка провайдера'
    WHEN 'rejected' THEN 'Отклонена'
    ELSE 'Неизвестно'
  END AS "Причина ошибки",
  SUM(failures_count)::bigint AS "Количество"
FROM analytics_daily_payment_failure_reasons
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${{source_mode}}'
  AND {source_key_filter()}
GROUP BY reason_key
ORDER BY "Количество" DESC, "Причина ошибки"
LIMIT 20;
            """,
            x=8,
            y=10,
            w=8,
            h=9,
        ),
        table_panel(
            16,
            "Выручка по источникам",
            """
SELECT
  """
            + source_key_label("source_key")
            + """ AS "Источник / start_param",
  SUM(payments_count)::bigint AS "Оплаты",
  SUM(revenue_amount_rub)::bigint AS "Выручка, ₽"
FROM analytics_daily_revenue
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
  AND payment_kind IN ('new', 'renewal')
GROUP BY source_key
ORDER BY "Выручка, ₽" DESC, "Оплаты" DESC
LIMIT 20;
            """,
            x=16,
            y=10,
            w=8,
            h=9,
            overrides=source_key_overrides(),
        ),
        row_panel(17, "Срезы", y=19),
        table_panel(
            18,
            "Выручка по тарифам",
            """
SELECT
  COALESCE(tariff_code, '—') AS "Тариф",
  SUM(payments_count)::bigint AS "Оплаты",
  SUM(revenue_amount_rub)::bigint AS "Выручка, ₽"
FROM analytics_daily_revenue
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
  AND payment_kind IN ('new', 'renewal')
GROUP BY tariff_code
ORDER BY "Выручка, ₽" DESC, "Оплаты" DESC
LIMIT 20;
            """,
            x=0,
            y=20,
            w=12,
            h=9,
        ),
        table_panel(
            19,
            "Выручка по методам оплаты",
            """
SELECT
  COALESCE(payment_method, '—') AS "Метод оплаты",
  SUM(payments_count)::bigint AS "Оплаты",
  SUM(revenue_amount_rub)::bigint AS "Выручка, ₽"
FROM analytics_daily_revenue
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
  AND payment_kind IN ('new', 'renewal')
GROUP BY payment_method
ORDER BY "Выручка, ₽" DESC, "Оплаты" DESC
LIMIT 20;
            """,
            x=12,
            y=20,
            w=12,
            h=9,
        ),
    ]
    return dashboard(
        "Выручка и монетизация",
        "amonora-revenue-monetization",
        tags=["analytics", "revenue", "stage-b", "strict"],
        time_from="now-30d",
        panels=panels,
        variables=[source_mode_variable(), source_key_variable()],
    )


def build_retention():
    panels = [
        row_panel(1, "Ключевые показатели", y=0),
        stat_panel(
            2,
            "Активные подписки",
            """
SELECT COALESCE((detail_json::json ->> 'active_users')::integer, 0) AS value
FROM analytics_runtime_status
WHERE status_key = 'growth_active_users'
ORDER BY updated_at DESC
LIMIT 1;
            """,
            x=0,
            y=1,
            w=5,
            h=4,
        ),
        stat_panel(3, "Продлили", stage_total_sql("subscription_renewed", filter_source_key=False), x=5, y=1, w=5, h=4),
        stat_panel(4, "Истекли", stage_total_sql("subscription_expired", filter_source_key=False), x=10, y=1, w=5, h=4),
        stat_panel(
            5,
            "Продление, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name = 'subscription_renewed' THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name IN ('subscription_renewed','subscription_expired') THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND event_name IN ('subscription_renewed','subscription_expired');
            """,
            x=15,
            y=1,
            w=4,
            h=4,
            unit="percent",
        ),
        stat_panel(
            6,
            "Отток, %",
            f"""
SELECT {rate_expr("SUM(CASE WHEN event_name = 'subscription_expired' THEN users_count ELSE 0 END)", "SUM(CASE WHEN event_name IN ('subscription_renewed','subscription_expired') THEN users_count ELSE 0 END)")} AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND event_name IN ('subscription_renewed','subscription_expired');
            """,
            x=19,
            y=1,
            w=5,
            h=4,
            unit="percent",
        ),
        row_panel(7, "Удержание", y=5),
        table_panel(
            8,
            "Когортная таблица",
            """
SELECT
  cohort_date AS "Когорта",
  period_days AS "День",
  cohort_size AS "Размер",
  active_users AS "Активны",
  renewed_users AS "Продлили",
  expired_users AS "Истекли",
  """
            + rate_expr("active_users", "cohort_size")
            + """ AS "Активны, %",
  """
            + rate_expr("renewed_users", "cohort_size")
            + """ AS "Продлили, %"
FROM analytics_cohort_retention
WHERE cohort_type = '${cohort_type}'
ORDER BY cohort_date DESC, period_days ASC
LIMIT 120;
            """,
            x=0,
            y=6,
            w=12,
            h=12,
        ),
        table_panel(
            9,
            "Ядро удержания",
            """
SELECT
  period_days AS "День",
  AVG(cohort_size)::numeric(12,2) AS "Средний размер когорты",
  AVG(active_users)::numeric(12,2) AS "Активны",
  AVG(renewed_users)::numeric(12,2) AS "Продлили",
  AVG(expired_users)::numeric(12,2) AS "Истекли",
  ROUND(AVG(100.0 * active_users / NULLIF(cohort_size, 0)), 2) AS "Активны, %",
  ROUND(AVG(100.0 * renewed_users / NULLIF(cohort_size, 0)), 2) AS "Продлили, %"
FROM analytics_cohort_retention
WHERE cohort_type = '${cohort_type}'
GROUP BY period_days
ORDER BY period_days;
            """,
            x=12,
            y=6,
            w=12,
            h=12,
        ),
        row_panel(10, "Продления и истечения", y=18),
        timeseries_panel(
            11,
            "Продления и истечения по дням",
            """
SELECT
  bucket_date::timestamp AS time,
  CASE event_name WHEN 'subscription_renewed' THEN 'Продлили' ELSE 'Истекли' END AS metric,
  SUM(users_count)::bigint AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND event_name IN ('subscription_renewed','subscription_expired')
GROUP BY bucket_date, event_name
ORDER BY bucket_date, event_name;
            """,
            x=0,
            y=19,
            w=12,
            h=10,
        ),
        table_panel(
            12,
            "Активные пользователи по когортам",
            """
SELECT
  cohort_date AS "Когорта",
  MAX(CASE WHEN period_days = 0 THEN active_users END) AS "День 0",
  MAX(CASE WHEN period_days = 7 THEN active_users END) AS "День 7",
  MAX(CASE WHEN period_days = 30 THEN active_users END) AS "День 30",
  MAX(CASE WHEN period_days = 60 THEN active_users END) AS "День 60",
  MAX(CASE WHEN period_days = 90 THEN active_users END) AS "День 90"
FROM analytics_cohort_retention
WHERE cohort_type = '${cohort_type}'
GROUP BY cohort_date
ORDER BY cohort_date DESC
LIMIT 40;
            """,
            x=12,
            y=19,
            w=12,
            h=10,
        ),
    ]
    return dashboard(
        "Удержание и отток",
        "amonora-retention-churn",
        tags=["analytics", "retention", "stage-b"],
        time_from="now-90d",
        panels=panels,
        variables=[cohort_variable()],
    )


def build_connection():
    panels = [
        row_panel(1, "Ключевые показатели", y=0),
        stat_panel(
            2,
            "Ключи выданы",
            """
SELECT COALESCE(SUM(config_issued_count), 0)::bigint AS value
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}');
            """,
            x=0,
            y=1,
            w=4,
            h=4,
        ),
        stat_panel(
            3,
            "Ошибки выдачи",
            """
SELECT COALESCE(SUM(config_issue_failed_count), 0)::bigint AS value
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}');
            """,
            x=4,
            y=1,
            w=4,
            h=4,
        ),
        stat_panel(
            4,
            "Первые подключения",
            """
SELECT COALESCE(SUM(first_connection_success_count), 0)::bigint AS value
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}');
            """,
            x=8,
            y=1,
            w=4,
            h=4,
        ),
        stat_panel(
            5,
            "Ошибки подключения",
            """
SELECT COALESCE(SUM(connection_failed_count), 0)::bigint AS value
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}');
            """,
            x=12,
            y=1,
            w=4,
            h=4,
        ),
        stat_panel(
            6,
            "Разрыв оплата→подключение",
            f"""
WITH gap AS (
  SELECT
    COALESCE(SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END), 0)::bigint AS paid,
    COALESCE(SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END), 0)::bigint AS connected
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'
    AND {source_key_filter()}
    AND event_name IN ('subscription_activated','subscription_renewed','first_connection_success')
)
SELECT GREATEST(paid - connected, 0)::bigint AS value
FROM gap;
            """,
            x=16,
            y=1,
            w=4,
            h=4,
        ),
        stat_panel(
            7,
            "Средний лаг до первого подключения",
            """
SELECT ROUND(AVG(NULLIF(avg_first_connection_lag_minutes, 0)), 2) AS value
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}');
            """,
            x=20,
            y=1,
            w=4,
            h=4,
            unit="m",
            color_mode="value",
        ),
        row_panel(8, "Разрыв и качество", y=5),
        table_panel(
            9,
            "Оплатили, но не подключились",
            f"""
WITH by_source AS (
  SELECT
    source_key,
    SUM(CASE WHEN event_name IN ('subscription_activated','subscription_renewed') THEN users_count ELSE 0 END)::bigint AS payment_success,
    SUM(CASE WHEN event_name = 'first_connection_success' THEN users_count ELSE 0 END)::bigint AS first_connection_success
  FROM analytics_daily_stage_counts
  WHERE $__timeFilter(bucket_date::timestamp)
    AND source_mode = '${{source_mode}}'
    AND {source_key_filter()}
    AND event_name IN ('subscription_activated','subscription_renewed','first_connection_success')
  GROUP BY source_key
)
SELECT
  """
            + source_key_label("source_key")
            + """ AS "Источник / start_param",
  payment_success AS "Оплатили",
  first_connection_success AS "Подключились",
  GREATEST(payment_success - first_connection_success, 0) AS "Разрыв",
  {rate_expr("GREATEST(payment_success - first_connection_success, 0)", "payment_success")} AS "Разрыв, %"
FROM by_source
ORDER BY "Разрыв" DESC, "Оплатили" DESC
LIMIT 30;
            """,
            x=0,
            y=6,
            w=12,
            h=10,
            overrides=source_key_overrides(),
        ),
        table_panel(
            10,
            "Качество по странам",
            """
SELECT
  COALESCE(country_code, '—') AS "Страна",
  SUM(config_issued_count)::bigint AS "Ключи выданы",
  SUM(config_issue_failed_count)::bigint AS "Ошибки выдачи",
  SUM(first_connection_success_count)::bigint AS "Первые подключения",
  SUM(connection_failed_count)::bigint AS "Ошибки подключения",
  """
            + rate_expr("SUM(first_connection_success_count)", "SUM(config_issued_count)")
            + """ AS "Успех подключения, %",
  ROUND(AVG(NULLIF(avg_first_connection_lag_minutes, 0)), 2) AS "Лаг, мин"
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
GROUP BY country_code
ORDER BY "Первые подключения" DESC, "Ключи выданы" DESC
LIMIT 20;
            """,
            x=12,
            y=6,
            w=12,
            h=10,
        ),
        row_panel(11, "Динамика", y=16),
        timeseries_panel(
            12,
            "Лаг до первого подключения по дням",
            """
SELECT
  bucket_date::timestamp AS time,
  'Средний лаг' AS metric,
  ROUND(AVG(NULLIF(avg_first_connection_lag_minutes, 0)), 2) AS value
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
GROUP BY bucket_date
ORDER BY bucket_date;
            """,
            x=0,
            y=17,
            w=12,
            h=10,
            unit="m",
        ),
        table_panel(
            13,
            "Качество по источникам",
            """
SELECT
  """
            + source_key_label("source_key")
            + """ AS "Источник / start_param",
  SUM(config_issued_count)::bigint AS "Ключи",
  SUM(first_connection_success_count)::bigint AS "Подключения",
  SUM(connection_failed_count)::bigint AS "Ошибки подключения",
  """
            + rate_expr("SUM(first_connection_success_count)", "SUM(config_issued_count)")
            + """ AS "Успех, %",
  ROUND(AVG(NULLIF(avg_first_connection_lag_minutes, 0)), 2) AS "Лаг, мин"
FROM analytics_daily_connection
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
GROUP BY source_key
ORDER BY "Подключения" DESC, "Ключи" DESC
LIMIT 25;
            """,
            x=12,
            y=17,
            w=12,
            h=10,
            overrides=source_key_overrides(),
        ),
    ]
    return dashboard(
        "Качество подключения",
        "amonora-connection-quality",
        tags=["analytics", "connection", "ops", "stage-b"],
        time_from="now-30d",
        panels=panels,
        variables=[source_mode_variable(), source_key_variable()],
    )


def build_ops_repair():
    panels = [
        row_panel(1, "Операции", y=0),
        stat_panel(
            2,
            "Открытые repair",
            """
SELECT COALESCE(repair_needed_open_count, 0) AS value
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 1;
            """,
            x=0,
            y=1,
            w=6,
            h=4,
        ),
        stat_panel(
            3,
            "Открытые инциденты",
            """
SELECT COALESCE(unresolved_incident_count, 0) AS value
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 1;
            """,
            x=6,
            y=1,
            w=6,
            h=4,
        ),
        stat_panel(
            4,
            "Provisioning 24ч",
            """
SELECT COALESCE(provisioning_failure_events_24h, 0) AS value
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 1;
            """,
            x=12,
            y=1,
            w=6,
            h=4,
        ),
        stat_panel(
            5,
            "Reconcile 24ч",
            """
SELECT COALESCE(reconcile_failure_events_24h, 0) AS value
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 1;
            """,
            x=18,
            y=1,
            w=6,
            h=4,
        ),
        timeseries_panel(
            6,
            "Ремонты и инциденты по часам",
            """
SELECT bucket_hour AS time, 'Открытые ремонты' AS metric, repair_needed_open_count::bigint AS value
FROM analytics_hourly_ops_snapshots
WHERE bucket_hour >= NOW() - INTERVAL '72 hour'
UNION ALL
SELECT bucket_hour AS time, 'Открытые инциденты' AS metric, unresolved_incident_count::bigint AS value
FROM analytics_hourly_ops_snapshots
WHERE bucket_hour >= NOW() - INTERVAL '72 hour'
ORDER BY time, metric;
            """,
            x=0,
            y=5,
            w=12,
            h=10,
        ),
        table_panel(
            7,
            "Инциденты по типам",
            """
SELECT
  incident_class AS "Класс",
  category AS "Категория",
  severity AS "Серьёзность",
  event_type AS "Тип события",
  SUM(created_count)::bigint AS "Создано",
  SUM(resolved_count)::bigint AS "Решено",
  SUM(repeated_count)::bigint AS "Повторов",
  SUM(unique_entities_count)::bigint AS "Сущностей"
FROM analytics_hourly_ops_incidents
WHERE bucket_hour >= NOW() - INTERVAL '24 hour'
GROUP BY incident_class, category, severity, event_type
ORDER BY "Создано" DESC, "Повторов" DESC
LIMIT 40;
            """,
            x=12,
            y=5,
            w=12,
            h=10,
        ),
        table_panel(
            8,
            "Последний ops-срез",
            """
SELECT
  bucket_hour AS "Срез",
  repair_needed_open_count AS "Открытые ремонты",
  unresolved_incident_count AS "Инциденты",
  unresolved_warning_count AS "Предупреждения",
  unresolved_critical_count AS "Критические",
  unresolved_access_count AS "Доступ",
  unresolved_node_count AS "Ноды",
  unresolved_service_count AS "Сервисы",
  provisioning_failure_events_24h AS "Provisioning 24ч",
  reconcile_failure_events_24h AS "Reconcile 24ч"
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 12;
            """,
            x=0,
            y=15,
            w=24,
            h=10,
        ),
    ]
    return dashboard(
        "Операции и ремонты",
        "amonora-ops-repair",
        tags=["analytics", "ops", "repair", "stage-b"],
        time_from="now-72h",
        panels=panels,
    )


def build_alerts_incidents():
    panels = [
        row_panel(1, "Сигналы", y=0),
        stat_panel(
            2,
            "Критические",
            """
SELECT COALESCE(unresolved_critical_count, 0) AS value
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 1;
            """,
            x=0,
            y=1,
            w=6,
            h=4,
        ),
        stat_panel(
            3,
            "Предупреждения",
            """
SELECT COALESCE(unresolved_warning_count, 0) AS value
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 1;
            """,
            x=6,
            y=1,
            w=6,
            h=4,
        ),
        stat_panel(
            4,
            "Открытые ремонты",
            """
SELECT COALESCE(repair_needed_open_count, 0) AS value
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 1;
            """,
            x=12,
            y=1,
            w=6,
            h=4,
        ),
        stat_panel(
            5,
            "Целостность source_key, %",
            """
SELECT ROUND(COALESCE((detail_json::json ->> 'integrity_ratio')::numeric, 1.0) * 100, 2) AS value
FROM analytics_runtime_status
WHERE status_key = 'source_key_integrity'
ORDER BY updated_at DESC
LIMIT 1;
            """,
            x=18,
            y=1,
            w=6,
            h=4,
            unit="percent",
        ),
        table_panel(
            6,
            "Статусы runtime",
            """
SELECT
  status_group AS "Группа",
  status_key AS "Ключ",
  status_value AS "Статус",
  observed_at AS "Наблюдалось",
  updated_at AS "Обновлено"
FROM analytics_runtime_status
ORDER BY updated_at DESC
LIMIT 20;
            """,
            x=0,
            y=5,
            w=12,
            h=10,
        ),
        table_panel(
            7,
            "Инциденты по классам",
            """
SELECT
  incident_class AS "Класс",
  category AS "Категория",
  severity AS "Серьёзность",
  event_type AS "Тип события",
  SUM(created_count)::bigint AS "Создано",
  SUM(resolved_count)::bigint AS "Решено",
  SUM(repeated_count)::bigint AS "Повторов"
FROM analytics_hourly_ops_incidents
WHERE bucket_hour >= NOW() - INTERVAL '24 hour'
GROUP BY incident_class, category, severity, event_type
ORDER BY "Создано" DESC, "Повторов" DESC
LIMIT 40;
            """,
            x=12,
            y=5,
            w=12,
            h=10,
        ),
        table_panel(
            8,
            "Качество атрибуции по дням",
            """
WITH daily_total AS (
  SELECT bucket_date, COALESCE(SUM(users_count), 0)::bigint AS total_bot_start
  FROM analytics_daily_stage_counts
  WHERE bucket_date >= CURRENT_DATE - INTERVAL '29 day'
    AND source_mode = 'first'
    AND event_name = 'bot_start'
  GROUP BY bucket_date
)
SELECT
  integrity.bucket_date AS "Дата",
  CASE integrity.issue_type
    WHEN 'null_source_key' THEN 'NULL source_key'
    WHEN 'empty_source_key' THEN 'Пустой source_key'
    WHEN 'organic_bot' THEN 'Органика'
    WHEN 'invalid_start_param' THEN 'Битый start_param'
    ELSE 'События без атрибуции'
  END AS "Тип проблемы",
  integrity.issue_count AS "Количество",
  """
            + rate_expr("integrity.issue_count", "daily_total.total_bot_start")
            + """ AS "Доля, %"
FROM analytics_daily_attribution_integrity integrity
LEFT JOIN daily_total ON daily_total.bucket_date = integrity.bucket_date
WHERE integrity.bucket_date >= CURRENT_DATE - INTERVAL '29 day'
ORDER BY integrity.bucket_date DESC, "Количество" DESC;
            """,
            x=0,
            y=15,
            w=12,
            h=10,
        ),
        table_panel(
            9,
            "Последний срез",
            """
SELECT
  bucket_hour AS "Срез",
  repair_needed_open_count AS "Открытые ремонты",
  unresolved_incident_count AS "Инциденты",
  unresolved_warning_count AS "Предупреждения",
  unresolved_critical_count AS "Критические",
  provisioning_failure_events_24h AS "Provisioning 24ч",
  reconcile_failure_events_24h AS "Reconcile 24ч"
FROM analytics_hourly_ops_snapshots
ORDER BY bucket_hour DESC
LIMIT 12;
            """,
            x=12,
            y=15,
            w=12,
            h=10,
        ),
    ]
    return dashboard(
        "Алерты и инциденты",
        "amonora-alerts-incidents",
        tags=["analytics", "alerts", "ops", "stage-b"],
        time_from="now-72h",
        panels=panels,
    )


def write_dashboards() -> None:
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    dashboards = {
        "amonora-home.json": build_home(),
        "channel-funnel.json": build_growth(),
        "source-performance.json": build_source_performance(),
        "revenue.json": build_revenue(),
        "retention-churn.json": build_retention(),
        "connection-quality.json": build_connection(),
        "ops-repair.json": build_ops_repair(),
        "alerts-incidents.json": build_alerts_incidents(),
    }
    for name, payload in dashboards.items():
        (DASHBOARDS_DIR / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_dashboards()
