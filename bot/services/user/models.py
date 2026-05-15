from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TestUserSummary:
    telegram_id: int
    access_active: bool
    status_label: str
    days_left_text: str
    expires_text: str
    balance_rub: int
    tariff_title: str
    devices_count: int
    device_limit: int
    devices: tuple[dict, ...]
    single_connection_uri: str | None
    subscription_page_url: str | None = None
    subscription_feed_url: str | None = None
    subscription_extended_feed_url: str | None = None
    happ_subscription_url: str | None = None
    manual_extension_label: str | None = None


@dataclass(frozen=True)
class TestBonusSummary:
    referral_link: str
    invited_count: int
    paid_count: int
    earned_total_rub: int
    balance_available_rub: int


@dataclass(frozen=True)
class DeviceGuide:
    key: str
    button_label: str
    title: str
    instruction_title: str
    instruction_description: str
    instruction_body: tuple[str, ...]
    install_links: tuple[tuple[str, str], ...]


DEVICE_GUIDES: dict[str, DeviceGuide] = {
    "android": DeviceGuide(
        key="android",
        button_label="Android",
        title="Android",
        instruction_title="Инструкция для Android",
        instruction_description=(
            "Откройте страницу Happ в Google Play и установите приложение. "
            "Если Google Play недоступен, используйте прямую установку из APK-файла."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> и нажмите <b>+</b> в правом верхнем углу.",
            "Выберите добавление по ссылке или вставку из буфера обмена.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и продолжите подключение.",
        ),
        install_links=(
            ("Открыть в Google Play", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("Скачать APK", "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk"),
        ),
    ),
    "ios": DeviceGuide(
        key="ios",
        button_label="iOS",
        title="iOS",
        instruction_title="Инструкция для iOS",
        instruction_description=(
            "Откройте Happ в App Store и установите приложение. "
            "После первого запуска подтвердите запрос на добавление системного профиля подключения "
            "и введите пароль устройства."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> и нажмите <b>+</b> в правом верхнем углу.",
            "Добавьте ссылку подписки или вставьте ключ из буфера обмена.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и завершите подключение.",
        ),
        install_links=(
            ("App Store (RU)", "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973"),
            ("App Store (Global)", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
        ),
    ),
    "windows": DeviceGuide(
        key="windows",
        button_label="Windows",
        title="Windows",
        instruction_title="Инструкция для Windows",
        instruction_description=(
            "Скачайте установщик для Windows, запустите его и завершите установку Happ. "
            "После установки вернитесь к этой подписке и добавьте её в приложение."
        ),
        instruction_body=(
            "Запустите <b>Happ</b> и нажмите <b>+</b> для добавления подписки.",
            "Вставьте ссылку или импортируйте ключ из буфера обмена.",
            "Вернитесь в бот, откройте <b>«Ключ»</b> и продолжите подключение.",
        ),
        install_links=(
            ("Windows x64", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"),
        ),
    ),
    "macos": DeviceGuide(
        key="macos",
        button_label="macOS",
        title="macOS",
        instruction_title="Инструкция для macOS",
        instruction_description=(
            "Откройте страницу Happ в App Store, установите приложение и подтвердите "
            "разрешение на системный профиль подключения, если macOS покажет такой запрос."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> и создайте новое подключение через <b>+</b>.",
            "Добавьте ссылку подписки или вставьте ключ вручную.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и завершите настройку.",
        ),
        install_links=(
            ("App Store (RU)", "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973"),
            ("App Store (Global)", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
        ),
    ),
    "tv": DeviceGuide(
        key="tv",
        button_label="TV",
        title="TV",
        instruction_title="Инструкция для TV",
        instruction_description=(
            "Если у вас Apple TV, используйте App Store. "
            "Если у вас Android TV, откройте Google Play или установите Happ через APK."
        ),
        instruction_body=(
            "Выберите подходящий магазин приложений или установочный файл ниже.",
            "Откройте <b>Happ</b> на телевизоре и добавьте новое подключение.",
            "Введите или импортируйте ссылку подписки.",
            "Вернитесь в бот, откройте <b>«Ключ»</b> и завершите подключение.",
        ),
        install_links=(
            ("Apple TV App Store", "https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274"),
            ("Android TV Google Play", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("Android TV APK", "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk"),
        ),
    ),
    "linux": DeviceGuide(
        key="linux",
        button_label="Linux",
        title="Linux",
        instruction_title="Инструкция для Linux",
        instruction_description=(
            "Выберите пакет под вашу систему и архитектуру, установите Happ, "
            "затем вернитесь на страницу подписки и добавьте ссылку в приложение."
        ),
        instruction_body=(
            "Установите <b>Happ</b> из подходящего пакета ниже и запустите приложение.",
            "Импортируйте ссылку подписки или вставьте ключ вручную.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и завершите подключение.",
        ),
        install_links=(
            ("Linux x64 (.deb)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb"),
            ("Linux arm64 (.deb)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.deb"),
            ("Linux x64 (.rpm)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.rpm"),
            ("Linux arm64 (.rpm)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.rpm"),
            ("Arch Linux x64 (.pkg.tar.zst)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.pkg.tar.zst"),
            ("Arch Linux arm64 (.pkg.tar.zst)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.pkg.tar.zst"),
        ),
    ),
    "apple_tv": DeviceGuide(
        key="apple_tv",
        button_label="Apple TV",
        title="Apple TV",
        instruction_title="Инструкция для Apple TV",
        instruction_description=(
            "Откройте страницу Happ в App Store на Apple TV, установите приложение "
            "и при необходимости подтвердите системный запрос на подключение."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> на Apple TV после установки.",
            "Добавьте подписку по ссылке или введите её вручную.",
            "Если появится системный запрос на подключение, подтвердите его.",
            "Вернитесь в бот к кнопке <b>«Ключ»</b>, если ссылка ещё не открыта.",
        ),
        install_links=(("Магазин приложений", "https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274"),),
    ),
    "android_tv": DeviceGuide(
        key="android_tv",
        button_label="Android TV",
        title="Android TV",
        instruction_title="Инструкция для Android TV",
        instruction_description=(
            "Откройте страницу Happ в Google Play и установите приложение. "
            "Если магазин не работает, используйте прямую установку из APK."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> на Android TV после установки.",
            "Добавьте новое подключение по ссылке или через буфер обмена.",
            "Если используете APK, сначала разрешите установку из внешнего источника.",
            "Вернитесь в бот к кнопке <b>«Ключ»</b>, чтобы продолжить подключение.",
        ),
        install_links=(
            ("Открыть в Google Play", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("Скачать APK", "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk"),
        ),
    ),
}
