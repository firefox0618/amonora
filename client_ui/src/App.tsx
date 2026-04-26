import { useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  Loader,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  ArrowUpRight,
  Check,
  Copy,
  QrCode,
  Rocket,
  Send,
  Shield,
  Smartphone,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

type InstallLink = {
  key: string;
  title: string;
  description: string;
  links: {
    label: string;
    url: string;
  }[];
};

type BoundDevice = {
  kind: string;
  id: number;
  slot_index: number;
  title: string;
  device_model: string;
  device_type: string;
  os_name: string;
  os_version: string;
  app_version: string | null;
  source_ip: string | null;
  bound_at: string | null;
  country_name?: string | null;
  source_label?: string | null;
  status_key?: "active" | "inactive" | "expired" | string;
  status_label?: string | null;
  connection_uri?: string | null;
};

type SubscriptionServer = {
  label: string;
};

type SubscriptionSummary = {
  display_name: string;
  telegram_id: number | null;
  status: "active" | "inactive" | "expired";
  status_label: string;
  expires_at: string | null;
  days_left: number | null;
  traffic_used: string;
  traffic_limit: string;
  feed_url: string;
  page_url: string;
  bot_url: string;
  is_active: boolean;
  channel_url: string;
  support_url: string;
  install_links: InstallLink[];
  devices_limit: number;
  servers: SubscriptionServer[];
  bound_devices: BoundDevice[];
  bound_devices_count: number;
  account_devices?: BoundDevice[];
  account_devices_count?: number;
};

const messages = {
  ru: {
    brand: "Amonora",
    subtitle: "Единая ссылка на подписку",
    invalidTitle: "Ссылка недействительна",
    invalidText: "Похоже, ссылка больше не активна или была указана с ошибкой.",
    retryText: "Проверьте ссылку заново или запросите новую в боте Amonora.",
    statusBlock: "Статус подписки",
    active: "Активна",
    inactive: "Не активна",
    expired: "Истекла",
    expiresLabel: "Действует до",
    daysLeftLabel: "Осталось",
    telegramIdLabel: "Telegram ID",
    trafficLabel: "Трафик",
    unlimitedSymbol: "∞",
    devicesCountLabel: "Устройств",
    installBlock: "Установка",
    installTitle: "Установите Happ",
    installText: "Откройте эту страницу на нужном устройстве через",
    installTextSuffix: "затем выберите платформу ниже и установите Happ из официального источника.",
    installSourcesLabel: "Ссылки для установки",
    addBlock: "Добавление подписки",
    addTitle: "Добавьте общую подписку",
    addText: "Покажите QR или скопируйте subscription feed. На разных устройствах выбирайте разные номера серверов.",
    qrButton: "Показать QR",
    copyButton: "Скопировать ссылку",
    copied: "Ссылка скопирована",
    copyFallback: "Скопируйте ссылку вручную",
    qrTitle: "QR для Happ",
    qrText: "Отсканируйте код в приложении или скопируйте ссылку ниже.",
    copyHint: "Для нескольких устройств выбирайте разные номера серверов внутри Happ.",
    support: "Поддержка",
    channel: "Канал",
    load: "Загружаем страницу подписки…",
    devices: "Подключено устройств",
    serversBlock: "Серверы для подключения",
    serversListTitle: "Серверы в подписке",
    serversListText: "Это те же названия серверов, которые Happ покажет после импорта ссылки.",
    serversEmpty: "Серверы появятся после подготовки маршрутов.",
    devicesListTitle: "Устройства аккаунта",
    devicesListText: "Здесь видно все устройства, которые сейчас занимают лимит аккаунта: и по единой ссылке, и через классические ключи.",
    devicesEmpty: "Пока ни одно устройство не занимает лимит аккаунта.",
    deviceSlotLabel: "Слот",
    deviceLegacyLabel: "Классический ключ",
    qrLinkButton: "QR для Happ + скопировать ссылку",
    noExpiry: "Без ограничения",
    daySingle: "день",
    dayFew: "дня",
    dayMany: "дней",
  },
} as const;

const locale = messages.ru;

function pluralizeDays(value: number): string {
  const mod10 = value % 10;
  const mod100 = value % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return locale.daySingle;
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) {
    return locale.dayFew;
  }
  return locale.dayMany;
}

function formatExpiry(isoValue: string | null): string {
  if (!isoValue) {
    return locale.noExpiry;
  }
  const value = new Date(isoValue);
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(value);
}

function formatDeviceDate(isoValue: string | null): string {
  if (!isoValue) {
    return "—";
  }
  const value = new Date(isoValue);
  if (Number.isNaN(value.getTime())) {
    return isoValue;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

function statusTone(status: SubscriptionSummary["status"]): "green" | "orange" | "red" {
  if (status === "active") {
    return "green";
  }
  if (status === "expired") {
    return "orange";
  }
  return "red";
}

function deviceStatusTone(status: BoundDevice["status_key"]): "green" | "orange" | "red" | "gray" {
  if (status === "active") {
    return "green";
  }
  if (status === "expired") {
    return "orange";
  }
  if (status === "inactive") {
    return "red";
  }
  return "gray";
}

function App() {
  const token = String(window.__AMONORA_CLIENT_TOKEN__ || "").trim();
  const apiBase = String(window.__AMONORA_CLIENT_API_BASE__ || "").trim();
  const [summary, setSummary] = useState<SubscriptionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [error, setError] = useState(false);
  const [platform, setPlatform] = useState("android");
  const petals = useMemo(
    () =>
      Array.from({ length: 40 }, () => ({
        size: 6 + Math.random() * 16,
        duration: 14 + Math.random() * 20,
        delay: -Math.random() * 20,
        x: Math.random() * 100,
        drift: Math.random() * 80 - 40,
        opacity: 0.3 + Math.random() * 0.5,
        blur: Math.random() > 0.7 ? 0.8 + Math.random() * 1.6 : 0,
        rotate: Math.random() * 140 - 70,
      })),
    []
  );
  const dust = useMemo(
    () =>
      Array.from({ length: 20 }, () => ({
        size: 1 + Math.random() * 3,
        duration: 10 + Math.random() * 12,
        delay: -Math.random() * 12,
        x: Math.random() * 100,
        y: Math.random() * 90,
        opacity: 0.25 + Math.random() * 0.45,
      })),
    []
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${apiBase}/api/public/subscriptions/${token}/summary`, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error("summary_not_found");
        }
        const payload = await response.json();
        if (cancelled) {
          return;
        }
        setSummary(payload.subscription);
        setPlatform(payload.subscription.install_links[0]?.key || "android");
        setLoading(false);
        void fetch(`${apiBase}/api/public/subscriptions/${token}/touch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event: "view" }),
          credentials: "same-origin",
        }).catch(() => undefined);
      } catch {
        if (cancelled) {
          return;
        }
        setError(true);
        setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [apiBase, token]);

  const selectedInstall = useMemo(
    () => summary?.install_links.find((item) => item.key === platform) || summary?.install_links[0] || null,
    [platform, summary],
  );
  const clientHostUrl = useMemo(() => {
    try {
      return summary?.page_url ? new URL(summary.page_url).origin : "https://client.amonoraconnect.com";
    } catch {
      return "https://client.amonoraconnect.com";
    }
  }, [summary]);
  const accountDevices = useMemo(
    () => summary?.account_devices ?? summary?.bound_devices ?? [],
    [summary],
  );
  const deviceCountText = useMemo(
    () => (summary ? `${summary.account_devices_count ?? summary.bound_devices_count} из ${summary.devices_limit}` : "0 из 0"),
    [summary],
  );

  async function handleCopy() {
    if (!summary) {
      return;
    }
    try {
      await navigator.clipboard.writeText(summary.feed_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
      void fetch(`${apiBase}/api/public/subscriptions/${token}/touch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event: "copy" }),
        credentials: "same-origin",
      }).catch(() => undefined);
    } catch {
      setCopied(false);
    }
  }

  if (loading) {
    return (
      <Box className="client-shell">
        <div className="sakura-backdrop">
          <div className="sakura-glow" />
          <div className="sakura-bokeh" />
          <div className="sakura-grain" />
          <div className="sakura-vignette" />
        </div>
        <div className="sakura-petals">
          {petals.map((petal, index) => (
            <span
              key={`petal-${index}`}
              className="sakura-petal"
              style={
                {
                  "--petal-size": `${petal.size.toFixed(1)}px`,
                  "--petal-duration": `${petal.duration.toFixed(1)}s`,
                  "--petal-delay": `${petal.delay.toFixed(1)}s`,
                  "--petal-x": `${petal.x.toFixed(1)}%`,
                  "--petal-drift": `${petal.drift.toFixed(0)}px`,
                  "--petal-opacity": petal.opacity.toFixed(2),
                  "--petal-blur": `${petal.blur.toFixed(2)}px`,
                  "--petal-rotate": `${petal.rotate.toFixed(0)}deg`,
                } as CSSProperties
              }
            />
          ))}
        </div>
        <div className="sakura-dust">
          {dust.map((particle, index) => (
            <span
              key={`dust-${index}`}
              className="sakura-dust-particle"
              style={
                {
                  "--dust-size": `${particle.size.toFixed(1)}px`,
                  "--dust-duration": `${particle.duration.toFixed(1)}s`,
                  "--dust-delay": `${particle.delay.toFixed(1)}s`,
                  "--dust-x": `${particle.x.toFixed(1)}%`,
                  "--dust-y": `${particle.y.toFixed(1)}%`,
                  "--dust-opacity": particle.opacity.toFixed(2),
                } as CSSProperties
              }
            />
          ))}
        </div>
        <Container size={980} className="client-container">
          <Paper className="client-loading" radius={28}>
            <Loader color="grape" size="lg" />
            <Text c="dimmed">{locale.load}</Text>
          </Paper>
        </Container>
      </Box>
    );
  }

  if (error || !summary) {
    return (
      <Box className="client-shell">
        <div className="sakura-backdrop">
          <div className="sakura-glow" />
          <div className="sakura-bokeh" />
          <div className="sakura-grain" />
          <div className="sakura-vignette" />
        </div>
        <div className="sakura-petals">
          {petals.map((petal, index) => (
            <span
              key={`petal-${index}`}
              className="sakura-petal"
              style={
                {
                  "--petal-size": `${petal.size.toFixed(1)}px`,
                  "--petal-duration": `${petal.duration.toFixed(1)}s`,
                  "--petal-delay": `${petal.delay.toFixed(1)}s`,
                  "--petal-x": `${petal.x.toFixed(1)}%`,
                  "--petal-drift": `${petal.drift.toFixed(0)}px`,
                  "--petal-opacity": petal.opacity.toFixed(2),
                  "--petal-blur": `${petal.blur.toFixed(2)}px`,
                  "--petal-rotate": `${petal.rotate.toFixed(0)}deg`,
                } as CSSProperties
              }
            />
          ))}
        </div>
        <div className="sakura-dust">
          {dust.map((particle, index) => (
            <span
              key={`dust-${index}`}
              className="sakura-dust-particle"
              style={
                {
                  "--dust-size": `${particle.size.toFixed(1)}px`,
                  "--dust-duration": `${particle.duration.toFixed(1)}s`,
                  "--dust-delay": `${particle.delay.toFixed(1)}s`,
                  "--dust-x": `${particle.x.toFixed(1)}%`,
                  "--dust-y": `${particle.y.toFixed(1)}%`,
                  "--dust-opacity": particle.opacity.toFixed(2),
                } as CSSProperties
              }
            />
          ))}
        </div>
        <Container size={980} className="client-container">
          <Paper className="client-invalid" radius={28}>
            <ThemeIcon size={72} radius="xl" variant="light" color="red">
              <Shield size={34} />
            </ThemeIcon>
            <Title order={1}>{locale.invalidTitle}</Title>
            <Text c="dimmed" maw={520}>
              {locale.invalidText}
            </Text>
            <Text c="dimmed" maw={520}>
              {locale.retryText}
            </Text>
            <Group justify="center">
              <Button component="a" href="https://t.me/amonora_bot" rightSection={<ArrowUpRight size={16} />}>
                Открыть бота
              </Button>
            </Group>
          </Paper>
        </Container>
      </Box>
    );
  }

  return (
    <Box className="client-shell">
      <div className="sakura-backdrop">
        <div className="sakura-glow" />
        <div className="sakura-bokeh" />
        <div className="sakura-grain" />
        <div className="sakura-vignette" />
      </div>
      <div className="sakura-petals">
        {petals.map((petal, index) => (
          <span
            key={`petal-${index}`}
            className="sakura-petal"
            style={
              {
                "--petal-size": `${petal.size.toFixed(1)}px`,
                "--petal-duration": `${petal.duration.toFixed(1)}s`,
                "--petal-delay": `${petal.delay.toFixed(1)}s`,
                "--petal-x": `${petal.x.toFixed(1)}%`,
                "--petal-drift": `${petal.drift.toFixed(0)}px`,
                "--petal-opacity": petal.opacity.toFixed(2),
                "--petal-blur": `${petal.blur.toFixed(2)}px`,
                "--petal-rotate": `${petal.rotate.toFixed(0)}deg`,
                } as CSSProperties
            }
          />
        ))}
      </div>
      <div className="sakura-dust">
        {dust.map((particle, index) => (
          <span
            key={`dust-${index}`}
            className="sakura-dust-particle"
            style={
              {
                "--dust-size": `${particle.size.toFixed(1)}px`,
                "--dust-duration": `${particle.duration.toFixed(1)}s`,
                "--dust-delay": `${particle.delay.toFixed(1)}s`,
                "--dust-x": `${particle.x.toFixed(1)}%`,
                "--dust-y": `${particle.y.toFixed(1)}%`,
                "--dust-opacity": particle.opacity.toFixed(2),
                } as CSSProperties
            }
          />
        ))}
      </div>
      <Container size={980} className="client-container">
        <Stack gap={28}>
          <Card className="client-hero" radius={30} padding={28}>
            <Group justify="space-between" align="flex-start" gap="lg" wrap="wrap">
              <Stack gap={14}>
                <Group gap="xs" className="client-kicker">
                  <div className="client-pulse" />
                  <Text fw={700}>{locale.brand}</Text>
                </Group>
                <div>
                  <Title order={1} className="client-title">
                    {summary.display_name}
                  </Title>
                  <Text className="client-subtitle">{locale.subtitle}</Text>
                </div>
              </Stack>
              <Group gap="sm">
                <Button
                  onClick={() => setQrOpen(true)}
                  variant="light"
                  radius="xl"
                  color="grape"
                  leftSection={<QrCode size={16} />}
                >
                  {locale.qrLinkButton}
                </Button>
                <ActionIcon
                  component="a"
                  href={summary.bot_url}
                  variant="light"
                  radius="xl"
                  size={48}
                  color="grape"
                >
                  <Send size={20} />
                </ActionIcon>
              </Group>
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" mt="xl">
              <Card className="client-status-card client-status-card--identity" radius={22} padding={20}>
                <Group justify="space-between" align="center">
                  <Text c="dimmed" size="sm">
                    {locale.statusBlock}
                  </Text>
                  <Badge color={statusTone(summary.status)} variant="light" size="lg" radius="xl">
                    {summary.status_label}
                  </Badge>
                </Group>
                <Text mt={10} fw={700} size="xl">
                  {summary.display_name}
                </Text>
                <Text mt={10} className="client-hero-id">
                  {locale.telegramIdLabel}: {summary.telegram_id ?? "—"}
                </Text>
              </Card>
              <Card className="client-status-card client-status-card--metrics" radius={22} padding={20}>
                <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="md">
                  <div>
                    <Text c="dimmed" size="md">
                      {locale.expiresLabel}
                    </Text>
                    <Text mt={8} fw={700} size="lg">
                      {formatExpiry(summary.expires_at)}
                    </Text>
                  </div>
                  <div>
                    <Text c="dimmed" size="md">
                      {locale.daysLeftLabel}
                    </Text>
                    <Text mt={8} fw={700} size="lg">
                      {summary.days_left == null
                        ? locale.noExpiry
                        : `${summary.days_left} ${pluralizeDays(summary.days_left)}`}
                    </Text>
                  </div>
                  <div>
                    <Text c="dimmed" size="md">
                      {locale.trafficLabel}
                    </Text>
                    <Text mt={8} fw={700} size="lg">
                      {summary.traffic_used} / {summary.traffic_limit || locale.unlimitedSymbol}
                    </Text>
                  </div>
                  <div>
                    <Text c="dimmed" size="md">
                      {locale.devicesCountLabel}
                    </Text>
                    <Text mt={8} fw={700} size="lg">
                      {deviceCountText}
                    </Text>
                  </div>
                </SimpleGrid>
              </Card>
            </SimpleGrid>
          </Card>

          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
            <Card className="client-section-card" radius={26} padding={24}>
              <Stack gap={22}>
                <Group justify="space-between" align="flex-start" gap="md">
                  <div>
                    <Text className="client-section-kicker">{locale.installBlock}</Text>
                    <Title order={2}>{locale.installTitle}</Title>
                  </div>
                  <ThemeIcon size={50} radius="xl" color="grape" variant="light">
                    <Rocket size={22} />
                  </ThemeIcon>
                </Group>
                <Text c="dimmed">
                  {locale.installText}{" "}
                  <Text
                    component="a"
                    href={clientHostUrl}
                    target="_blank"
                    rel="noreferrer"
                    inherit
                    c="var(--accent)"
                  >
                    {clientHostUrl}
                  </Text>{" "}
                  {locale.installTextSuffix}
                </Text>
                <SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }} spacing="sm">
                  {summary.install_links.map((item) => (
                    <Button
                      key={item.key}
                      radius="xl"
                      variant={platform === item.key ? "filled" : "light"}
                      onClick={() => setPlatform(item.key)}
                    >
                      {item.title}
                    </Button>
                  ))}
                </SimpleGrid>
                {selectedInstall ? (
                  <Paper className="client-install-card" radius={22} p="lg">
                    <Stack gap="md">
                      <Group justify="space-between" align="center">
                        <Group gap="sm">
                          <ThemeIcon size={42} radius="xl" variant="light" color="grape">
                            <Smartphone size={18} />
                          </ThemeIcon>
                          <div>
                            <Text fw={700}>{selectedInstall.title}</Text>
                          </div>
                        </Group>
                      </Group>
                      <Text c="dimmed">{selectedInstall.description}</Text>
                      <Stack gap="sm">
                        <Text fw={600} size="sm">
                          {locale.installSourcesLabel}
                        </Text>
                        {selectedInstall.links.map((link) => (
                          <Group
                            key={`${selectedInstall.key}-${link.label}`}
                            justify="space-between"
                            align="center"
                            gap="sm"
                            className="client-install-link"
                          >
                            <Text size="sm" fw={600}>
                              {link.label}
                            </Text>
                            <Button
                              component="a"
                              href={link.url}
                              target="_blank"
                              rel="noreferrer"
                              radius="xl"
                              variant="subtle"
                              rightSection={<ArrowUpRight size={16} />}
                            >
                              Открыть
                            </Button>
                          </Group>
                        ))}
                      </Stack>
                    </Stack>
                  </Paper>
                ) : null}
              </Stack>
            </Card>

            <Card className="client-section-card client-section-card--accent" radius={26} padding={24}>
              <Stack gap={22}>
                <Group justify="space-between" align="flex-start" gap="md">
                  <div>
                    <Text className="client-section-kicker">{locale.addBlock}</Text>
                    <Title order={2}>{locale.addTitle}</Title>
                  </div>
                  <ThemeIcon size={50} radius="xl" color="green" variant="light">
                    <Check size={22} />
                  </ThemeIcon>
                </Group>
                <Text c="dimmed">{locale.addText}</Text>
                <Group grow>
                  <Button radius="xl" variant="light" leftSection={<QrCode size={16} />} onClick={() => setQrOpen(true)}>
                    {locale.qrButton}
                  </Button>
                  <Button radius="xl" leftSection={<Copy size={16} />} onClick={() => void handleCopy()}>
                    {copied ? locale.copied : locale.copyButton}
                  </Button>
                </Group>
                <Paper className="client-feed-preview" radius={22} p="md">
                  <Text c="dimmed" size="sm">
                    Feed URL
                  </Text>
                  <Text className="client-feed-url">{summary.feed_url}</Text>
                </Paper>
                <SimpleGrid cols={2} spacing="md">
                  <Paper className="client-mini-stat" radius={18} p="md">
                    <Text c="dimmed" size="sm">
                      {locale.devices}
                    </Text>
                    <Text mt={8} fw={700}>
                      {deviceCountText}
                    </Text>
                  </Paper>
                  <Paper className="client-mini-stat" radius={18} p="md">
                    <Text c="dimmed" size="sm">
                      {locale.channel}
                    </Text>
                    <Button
                      component="a"
                      href={summary.channel_url}
                      target="_blank"
                      rel="noreferrer"
                      variant="subtle"
                      radius="xl"
                      rightSection={<ArrowUpRight size={14} />}
                      mt={6}
                      p={0}
                    >
                      Открыть
                    </Button>
                  </Paper>
                </SimpleGrid>
              </Stack>
            </Card>
          </SimpleGrid>

          <Card className="client-section-card" radius={26} padding={24}>
            <Stack gap={18}>
              <Group justify="space-between" align="flex-start" gap="md">
                <div>
                  <Text className="client-section-kicker">{locale.serversBlock}</Text>
                  <Title order={2}>{locale.serversListTitle}</Title>
                  <Text c="dimmed" mt={8}>
                    {locale.serversListText}
                  </Text>
                </div>
                <Badge color="grape" variant="light" radius="xl" size="lg">
                  {summary.servers.length}
                </Badge>
              </Group>
              {summary.servers.length ? (
                <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="md">
                  {summary.servers.map((server) => (
                    <Paper key={server.label} className="client-server-item" radius={22} p="lg">
                      <Text fw={700} size="lg">
                        {server.label}
                      </Text>
                    </Paper>
                  ))}
                </SimpleGrid>
              ) : (
                <Text c="dimmed">{locale.serversEmpty}</Text>
              )}
            </Stack>
          </Card>

          <Card className="client-section-card" radius={26} padding={24}>
            <Stack gap={18}>
              <Group justify="space-between" align="flex-start" gap="md">
                <div>
                  <Text className="client-section-kicker">{locale.devices}</Text>
                  <Title order={2}>{locale.devicesListTitle}</Title>
                  <Text c="dimmed" mt={8}>
                    {locale.devicesListText}
                  </Text>
                </div>
                <Badge color="grape" variant="light" radius="xl" size="lg">
                  {deviceCountText}
                </Badge>
              </Group>
              {accountDevices.length ? (
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                  {accountDevices.map((device) => (
                    <Paper key={`${device.kind}-${device.id}`} className="client-device-item" radius={22} p="lg">
                      <Stack gap={14}>
                        <Group justify="space-between" align="flex-start" gap="md">
                          <div>
                            <Text fw={700} size="lg">
                              {device.device_model || device.title}
                            </Text>
                            <Text c="dimmed" size="md" mt={4}>
                              {device.os_name || "Устройство"} {device.os_version && device.os_version !== "—" ? `• ${device.os_version}` : ""}
                            </Text>
                          </div>
                          <Stack gap={8} align="flex-end">
                            <Badge variant="light" color={deviceStatusTone(device.status_key)} radius="xl">
                              {device.status_label || (device.kind === "public_slot" ? locale.active : locale.active)}
                            </Badge>
                            {device.kind === "public_slot" ? (
                              <Badge variant="light" color="grape" radius="xl">
                                {locale.deviceSlotLabel} {device.slot_index}
                              </Badge>
                            ) : (
                              <Badge variant="light" color="gray" radius="xl">
                                {locale.deviceLegacyLabel}
                              </Badge>
                            )}
                          </Stack>
                        </Group>
                        <div className="client-device-meta">
                          <div className="client-device-meta__item">
                            <Text className="client-device-meta__label">Источник</Text>
                            <Text className="client-device-meta__value">{device.source_label || (device.kind === "public_slot" ? "Happ / единая ссылка" : "Классический ключ")}</Text>
                          </div>
                          <div className="client-device-meta__item">
                            <Text className="client-device-meta__label">Регион</Text>
                            <Text className="client-device-meta__value">{device.country_name || "—"}</Text>
                          </div>
                          <div className="client-device-meta__item">
                            <Text className="client-device-meta__label">Добавлено</Text>
                            <Text className="client-device-meta__value">{formatDeviceDate(device.bound_at)}</Text>
                          </div>
                          <div className="client-device-meta__item">
                            <Text className="client-device-meta__label">IP</Text>
                            <Text className="client-device-meta__value">{device.source_ip || "—"}</Text>
                          </div>
                        </div>
                      </Stack>
                    </Paper>
                  ))}
                </SimpleGrid>
              ) : (
                <Paper className="client-device-item" radius={22} p="lg">
                  <Text c="dimmed" size="lg">
                    {locale.devicesEmpty}
                  </Text>
                </Paper>
              )}
            </Stack>
          </Card>
        </Stack>
      </Container>

      <Modal
        opened={qrOpen}
        onClose={() => setQrOpen(false)}
        centered
        radius={26}
        size="md"
        overlayProps={{ blur: 5, opacity: 0.3 }}
        title={<Text fw={700}>{locale.qrLinkButton}</Text>}
      >
        <Stack gap="lg" align="center">
          <Box className="client-qr-frame">
            <QRCodeSVG value={summary.feed_url} size={280} bgColor="transparent" fgColor="#f6c2db" />
          </Box>
          <Text c="dimmed" ta="center">
            {locale.qrText}
          </Text>
          <Button fullWidth radius="xl" leftSection={<Copy size={16} />} onClick={() => void handleCopy()}>
            {copied ? locale.copied : locale.copyButton}
          </Button>
          <Text c="dimmed" size="sm" ta="center">
            {locale.copyHint}
          </Text>
        </Stack>
      </Modal>
    </Box>
  );
}

export default App;
