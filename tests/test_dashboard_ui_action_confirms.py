from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class DashboardUiActionConfirmTests(unittest.TestCase):
    def test_servers_page_confirms_high_impact_actions(self) -> None:
        source = _read("dashboard/ui/src/app/(dashboard)/servers/page.tsx")
        self.assertIn("function confirmAction(message: string): boolean", source)
        self.assertIn("Запустить health check для ${selectedNode.name}?", source)
        self.assertIn("Перезапустить ноду ${selectedNode.name}?", source)
        self.assertIn("Переключить maintenance-режим для ${selectedNode.name}?", source)
        self.assertIn("Запустить миграцию ${selectedNode.name} на ${targetLabel}?", source)

    def test_settings_page_confirms_dangerous_mutations(self) -> None:
        source = _read("dashboard/ui/src/app/(dashboard)/settings/page.tsx")
        self.assertIn("function confirmAction(message: string): boolean", source)
        self.assertIn("Обновить тарифы для бота и лендинга?", source)
        self.assertIn("Перезапустить сервис ${serviceName}?", source)
        self.assertIn("Сохранить переменную ${envForm.key || \"KEY\"} в .env и сразу применить её через restart+verify?", source)
        self.assertIn("применить её через restart+verify", source)
        self.assertIn("разрешение «${row.label || row.permission}» для техадмина", source)
        self.assertIn("разрешение «${row.label || row.permission}» для менеджера", source)
        self.assertIn("Обновить администратора ${admin.display_name}: роль ${nextRole}, статус ${stateLabel}?", source)
        self.assertIn("уведомления «${category.label}» для ${profile.display_name}", source)

    def test_overview_and_traffic_confirm_side_effect_actions(self) -> None:
        overview_source = _read("dashboard/ui/src/app/(dashboard)/overview/page.tsx")
        traffic_source = _read("dashboard/ui/src/app/(dashboard)/traffic/page.tsx")
        self.assertIn("Запустить синхронизацию доступа для ${item.title}?", overview_source)
        self.assertIn("Сбросить накопленный baseline трафика? Live throughput при этом не обнулится.", traffic_source)

    def test_support_page_confirms_assign_transfer_and_repairs(self) -> None:
        source = _read("dashboard/ui/src/app/(dashboard)/support/page.tsx")
        self.assertIn("Отправить этот ответ пользователю?", source)
        self.assertIn("Закрепить этот диалог за собой?", source)
        self.assertIn("Передать это обращение другому администратору?", source)
        self.assertIn("Запустить синхронизацию доступа для этого пользователя из обращения?", source)
        self.assertIn("Запустить глубокий ремонт доступа для этого пользователя из обращения?", source)

    def test_payments_page_confirms_reminder_provider_sync_and_repairs(self) -> None:
        source = _read("dashboard/ui/src/app/(dashboard)/payments/page.tsx")
        self.assertIn("Создать новую ручную заявку для пользователя #${paymentForm.user_id || \"?\"}?", source)
        self.assertIn("Добавить операционную запись на ${financeForm.amount || \"0\"} ₽ в категорию «${financeForm.category}»?", source)
        self.assertIn("Отправить напоминание пользователю по платежу #${selectedRecord.id}?", source)
        self.assertIn("Синхронизировать платёж #${selectedRecord.id} с провайдером прямо сейчас?", source)
        self.assertIn("Запустить синхронизацию доступа для пользователя этого платежа?", source)
        self.assertIn("Запустить глубокий ремонт доступа для пользователя этого платежа?", source)

    def test_knowledge_page_confirms_report_generation(self) -> None:
        source = _read("dashboard/ui/src/app/(dashboard)/knowledge/page.tsx")
        self.assertIn("function confirmAction(message: string): boolean", source)
        self.assertIn("Сгенерировать новый операционный отчёт и перезаписать текущую версию?", source)

    def test_users_page_confirms_high_impact_actions(self) -> None:
        source = _read("dashboard/ui/src/app/(dashboard)/users/page.tsx")
        self.assertIn("Создать устройство «${deviceForm.device_name || \"Новое устройство\"}» в регионе ${deviceForm.country_code.toUpperCase()}?", source)
        self.assertIn("Продлить доступ пользователю на ${safeDays} дн.?", source)
        self.assertIn("Запустить синхронизацию доступа для этого пользователя?", source)
        self.assertIn("Запустить глубокий ремонт доступа для этого пользователя?", source)
        self.assertIn("Удалить устройство «${device.metadata.device_name}»?", source)
        self.assertIn("Убрать тариф и отключить доступ пользователю?", source)
        self.assertIn("Заблокировать пользователя и остановить доступ?", source)
        self.assertIn("Снять блокировку с пользователя?", source)
        self.assertIn("Сохранить предпочитаемый протокол: ${protocolLabel(currentProtocol)}?", source)
        self.assertIn("Удалить пользователя вместе с данными доступа?", source)


if __name__ == "__main__":
    unittest.main()
