import json
import unittest

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GRAFANA_ROOT = REPO_ROOT / "ops/grafana"


class GrafanaAnalyticsConfigTests(unittest.TestCase):
    def _dashboard_payload(self, name: str) -> dict:
        return json.loads((GRAFANA_ROOT / "dashboards" / name).read_text(encoding="utf-8"))

    def test_grafana_service_is_local_and_limited(self) -> None:
        source = (REPO_ROOT / "ops/systemd/amonora-grafana.service").read_text(encoding="utf-8")
        self.assertIn("/usr/sbin/grafana-server", source)
        self.assertIn("MemoryMax=512M", source)
        self.assertIn("CPUQuota=30%", source)
        self.assertIn("cfg:default.paths.provisioning=/opt/amonora_bot/ops/grafana/provisioning", source)
        self.assertIn("Requires=amonora-grafana-db-tunnel.service", source)

        ini = (GRAFANA_ROOT / "grafana.ini").read_text(encoding="utf-8")
        self.assertIn("http_addr = 127.0.0.1", ini)
        self.assertIn("http_port = 3002", ini)
        self.assertIn("serve_from_sub_path = false", ini)
        self.assertIn("root_url = https://grafana.amonoraconnect.com/", ini)
        self.assertIn("default_home_dashboard_path = /opt/amonora_bot/ops/grafana/dashboards/amonora-home.json", ini)
        self.assertIn("default_theme = dark", ini)

    def test_estonia_nginx_grafana_vhost_is_basic_auth_protected(self) -> None:
        source = (REPO_ROOT / "ops/nginx/amonora-grafana-estonia.server.conf").read_text(encoding="utf-8")
        self.assertIn("server_name grafana.amonoraconnect.com;", source)
        self.assertIn('auth_basic "Amonora Grafana";', source)
        self.assertIn("auth_basic_user_file /etc/nginx/.htpasswd-grafana;", source)
        self.assertIn("proxy_pass http://127.0.0.1:3002;", source)
        self.assertIn("proxy_hide_header Content-Security-Policy;", source)
        self.assertIn("'unsafe-eval'", source)

    def test_core_nginx_redirects_legacy_grafana_route(self) -> None:
        source = (REPO_ROOT / "ops/nginx/amonora-dashboard.server.conf").read_text(encoding="utf-8")
        self.assertIn("location = /grafana", source)
        self.assertIn("https://grafana.amonoraconnect.com/", source)
        self.assertIn("location ~ ^/grafana/(.*)$", source)

    def test_tunnel_env_and_service_keep_postgres_private(self) -> None:
        env_template = (REPO_ROOT / "ops/env/amonora-grafana.env.template").read_text(encoding="utf-8")
        self.assertIn("GRAFANA_ANALYTICS_DB_HOST=127.0.0.1", env_template)
        self.assertIn("GRAFANA_ANALYTICS_DB_PORT=15432", env_template)

        tunnel_env = (REPO_ROOT / "ops/env/amonora-grafana-db-tunnel.env.template").read_text(encoding="utf-8")
        self.assertIn("GRAFANA_ANALYTICS_TUNNEL_CORE_HOST=46.21.81.186", tunnel_env)
        self.assertIn("GRAFANA_ANALYTICS_TUNNEL_LOCAL_PORT=15432", tunnel_env)

        tunnel_service = (REPO_ROOT / "ops/systemd/amonora-grafana-db-tunnel.service").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:5432", tunnel_service)
        self.assertIn("/usr/bin/ssh -N", tunnel_service)

    def test_datasource_and_dashboards_use_analytics_only(self) -> None:
        datasource = (GRAFANA_ROOT / "provisioning/datasources/amonora-analytics-postgres.yaml").read_text(encoding="utf-8")
        self.assertIn("prune: true", datasource)
        self.assertIn("deleteDatasources:", datasource)
        self.assertIn("name: Amonora Analytics", datasource)
        self.assertIn("uid: amonora-analytics", datasource)
        self.assertIn("user: $__env{GRAFANA_ANALYTICS_DB_USER}", datasource)
        self.assertIn("minTimeInterval: 5m", datasource)
        grants = (GRAFANA_ROOT / "sql/grant_grafana_reader.sql.template").read_text(encoding="utf-8")
        self.assertIn("analytics_daily_payment_failure_reasons", grants)
        self.assertIn("analytics_daily_attribution_integrity", grants)
        provider = (GRAFANA_ROOT / "provisioning/dashboards/amonora-analytics.yaml").read_text(encoding="utf-8")
        self.assertIn("folder: Amonora Suite", provider)

        forbidden_table_patterns = (
            " from users",
            " join users",
            " from payment_records",
            " join payment_records",
            " from vpn_client_activations",
            " join vpn_client_activations",
            " from channel_post_touches",
            " join channel_post_touches",
            " from finance_entries",
            " join finance_entries",
        )
        dashboards = sorted((GRAFANA_ROOT / "dashboards").glob("*.json"))
        self.assertEqual(len(dashboards), 8)

        for path in dashboards:
            payload = json.loads(path.read_text(encoding="utf-8"))
            serialized = json.dumps(payload, ensure_ascii=False).lower()
            self.assertIn("analytics_", serialized, msg=path.name)
            for forbidden in forbidden_table_patterns:
                self.assertNotIn(forbidden, serialized, msg=f"{path.name} should not query operational table via `{forbidden}`")

        serialized_dashboards = "\n".join(path.read_text(encoding="utf-8") for path in dashboards).lower()
        self.assertIn("analytics_daily_stage_counts", serialized_dashboards)
        self.assertIn("analytics_daily_revenue", serialized_dashboards)
        self.assertIn("analytics_daily_payment_failure_reasons", serialized_dashboards)
        self.assertIn("analytics_daily_attribution_integrity", serialized_dashboards)
        self.assertIn("source_key_integrity", serialized_dashboards)
        self.assertIn("\"name\": \"source_key\"", serialized_dashboards)
        self.assertIn("growth_active_users", serialized_dashboards)
        self.assertNotIn(":sqlstring", serialized_dashboards)
        self.assertIn("'${source_mode}'", serialized_dashboards)
        self.assertIn("'${source_key}'", serialized_dashboards)

    def test_home_dashboard_is_short_russian_overview(self) -> None:
        payload = self._dashboard_payload("amonora-home.json")
        self.assertEqual(payload["title"], "Главная Amonora")
        templating = {item.get("name"): item for item in payload.get("templating", {}).get("list", [])}
        self.assertEqual(templating["source_mode"]["current"]["value"], "last")

        panel_titles = {panel.get("title") for panel in payload["panels"] if panel.get("title")}
        self.assertTrue(
            {
                "Ключевые показатели",
                "Обзор окна",
                "Короткая воронка",
                "Сегодня / 7д / 30д",
                "Целостность атрибуции",
                "Свежесть данных",
                "Активные алерты",
            }.issubset(panel_titles)
        )
        self.assertTrue(
            {
                "Полная воронка",
                "Потери воронки",
                "Оплатили, но не подключились по источникам",
                "Новые и возвращающиеся",
                "Эффективность постов / CTA",
            }.isdisjoint(panel_titles)
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertIn("\"label\": \"Источник / start_param\"", serialized)
        self.assertIn("\"text\": \"Все\"", serialized)
        self.assertIn("var-source_mode=${source_mode}", serialized)
        self.assertIn("var-source_key=${source_key}", serialized)
        self.assertIn("${__url_time_range}", serialized)
        self.assertIn("Переходы по ссылке", serialized)
        self.assertIn("Активные подписки", serialized)
        self.assertIn("Контроль", serialized)
        self.assertIn("Начало подключения", serialized)
        self.assertIn("Готов к подключению", serialized)
        self.assertNotIn("Онбординг", serialized)
        self.assertNotIn("Полная воронка", serialized)

    def test_growth_dashboard_contains_stage_b_core_blocks(self) -> None:
        payload = self._dashboard_payload("channel-funnel.json")
        self.assertEqual(payload["title"], "Воронка роста")
        templating = {item.get("name"): item for item in payload.get("templating", {}).get("list", [])}
        self.assertEqual(templating["source_mode"]["current"]["value"], "last")
        panel_titles = {panel.get("title") for panel in payload["panels"] if panel.get("title")}
        self.assertTrue(
            {
                "Воронка подключения",
                "Потери по этапам",
                "Источники",
                "Причины неуспешной оплаты",
                "Качество данных",
                "Целостность атрибуции",
            }.issubset(panel_titles)
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertIn("Переход по ссылке", serialized)
        self.assertIn("Подтвердили подписку", serialized)
        self.assertIn("Начало подключения", serialized)
        self.assertIn("Готов к подключению", serialized)
        self.assertIn("Разрыв, %", serialized)
        self.assertIn("Продление", serialized)
        self.assertIn("Новые оплаты", serialized)
        self.assertIn("Выручка продлений", serialized)
        self.assertNotIn("Онбординг", serialized)

    def test_source_revenue_retention_connection_and_alert_dashboards_match_thematic_split(self) -> None:
        source_payload = self._dashboard_payload("source-performance.json")
        self.assertEqual(source_payload["title"], "Источники и посты")
        source_serialized = json.dumps(source_payload, ensure_ascii=False)
        self.assertIn("Конверсия в оплату, %", source_serialized)
        self.assertIn("Конверсия в подключение, %", source_serialized)
        self.assertIn("Источник / start_param", source_serialized)
        self.assertIn("Тип контента", source_serialized)
        self.assertIn("Посты и CTA", source_serialized)
        self.assertIn("var-source_key=${__value.raw}", source_serialized)
        self.assertNotIn("ARPPU", source_serialized)

        revenue_payload = self._dashboard_payload("revenue.json")
        self.assertEqual(revenue_payload["title"], "Выручка и монетизация")
        revenue_serialized = json.dumps(revenue_payload, ensure_ascii=False)
        self.assertIn("Новые оплаты", revenue_serialized)
        self.assertIn("Продления", revenue_serialized)
        self.assertIn("Выручка новых", revenue_serialized)
        self.assertIn("Выручка продлений", revenue_serialized)
        self.assertIn("Общая выручка", revenue_serialized)
        self.assertIn("Причины неуспешной оплаты", revenue_serialized)
        self.assertIn("Выручка по тарифам", revenue_serialized)
        self.assertIn("Выручка по методам оплаты", revenue_serialized)
        self.assertNotIn("Новые и возвращающиеся", revenue_serialized)

        retention_payload = self._dashboard_payload("retention-churn.json")
        self.assertEqual(retention_payload["title"], "Удержание и отток")
        retention_serialized = json.dumps(retention_payload, ensure_ascii=False)
        self.assertIn("Ядро удержания", retention_serialized)
        self.assertIn("Активные пользователи по когортам", retention_serialized)
        self.assertIn("Продление, %", retention_serialized)
        self.assertIn("Отток, %", retention_serialized)

        connection_payload = self._dashboard_payload("connection-quality.json")
        self.assertEqual(connection_payload["title"], "Качество подключения")
        connection_serialized = json.dumps(connection_payload, ensure_ascii=False)
        self.assertIn("Оплатили, но не подключились", connection_serialized)
        self.assertIn("Качество по странам", connection_serialized)
        self.assertIn("Качество по источникам", connection_serialized)
        self.assertIn("Средний лаг до первого подключения", connection_serialized)

        alerts_payload = self._dashboard_payload("alerts-incidents.json")
        self.assertEqual(alerts_payload["title"], "Алерты и инциденты")
        alerts_serialized = json.dumps(alerts_payload, ensure_ascii=False)
        self.assertIn("Статусы runtime", alerts_serialized)
        self.assertIn("Качество атрибуции по дням", alerts_serialized)
        self.assertIn("Предупреждения", alerts_serialized)
        self.assertIn("Открытые ремонты", alerts_serialized)
        self.assertIn("Целостность source_key, %", alerts_serialized)

    def test_alerting_provisioning_and_webhook_contract_exist(self) -> None:
        env_template = (REPO_ROOT / "ops/env/amonora-grafana.env.template").read_text(encoding="utf-8")
        self.assertIn("GRAFANA_ALERTS_WEBHOOK_URL=https://amonoraconnect.com/dashboard/api/internal/grafana/alerts/change-me", env_template)

        alerting_dir = GRAFANA_ROOT / "provisioning/alerting"
        contact_points = (alerting_dir / "amonora-contact-points.yaml").read_text(encoding="utf-8")
        policies = (alerting_dir / "amonora-notification-policies.yaml").read_text(encoding="utf-8")
        rules = (alerting_dir / "amonora-rules.yaml").read_text(encoding="utf-8")

        self.assertIn("Amonora Control Telegram", contact_points)
        self.assertIn("$__env{GRAFANA_ALERTS_WEBHOOK_URL}", contact_points)
        self.assertIn("group_by", policies)
        self.assertIn("alert_class", policies)
        self.assertIn("dashboard/api/internal/grafana/alerts", (REPO_ROOT / "dashboard/main.py").read_text(encoding="utf-8"))
        self.assertIn("alert_class: revenue", rules)
        self.assertIn("alert_class: growth", rules)
        self.assertIn("alert_class: ops", rules)
        self.assertIn("analytics_runtime_status", rules)
        self.assertIn("analytics_hourly_ops_snapshots", rules)
        self.assertIn("bot_start → config", rules)
        self.assertIn("config → payment", rules)
        self.assertIn("paid → connected gap", rules)
        self.assertIn("payment_started → payment_success", rules)
        self.assertIn("source_key_integrity", rules)

        forbidden_table_patterns = (
            " from users",
            " join users",
            " from payment_records",
            " join payment_records",
            " from vpn_client_activations",
            " join vpn_client_activations",
            " from control_notification_events",
            " join control_notification_events",
        )
        rules_lower = rules.lower()
        for forbidden in forbidden_table_patterns:
            self.assertNotIn(forbidden, rules_lower)


if __name__ == "__main__":
    unittest.main()
