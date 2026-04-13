# FEATURES

## Зачем нужен этот документ

Этот документ фиксирует не архитектуру, а функциональные возможности текущего продукта `Amonora`.

Задача документа:

- коротко показать, что уже умеет система;
- отделить рабочие функции от будущих идей;
- дать понятную карту для команды и AI.

## Текущее состояние

На текущем этапе главный рабочий продукт экосистемы `Amonora` — это `Amonora`.

Это VPN-сервис с несколькими связанными контурами:

- основной клиентский bot;
- support bot;
- internal control bot;
- публичный landing;
- административный dashboard;
- backend-логика и база данных;
- отдельные VPN-ноды.

## Основные пользовательские функции

### 1. Вход в продукт через Telegram

Пользователь может:

- открыть `@amonora_bot`;
- если Telegram недоступен напрямую, сначала запросить на сайте бесплатный bridge-ключ на `1 день`, подключиться через него и уже затем зайти в `@amonora_bot`;
- начать работу без отдельного классического личного кабинета;
- пройти основной сценарий внутри Telegram;
- увидеть при первом `/start` единое стартовое сообщение, где trial зависит от подписки на канал, а стартовый экран одновременно несёт уведомление об акцепте пользовательского соглашения, прямую ссылку на оферту и кнопку перехода в канал;
- принимать tracked deep-link переходы из публичного канала в формате `post_<token>` без ломания текущего `ref_<code>` referral-flow и использовать их для отдельной channel-attribution цепочки;
- при повторном `/start` с уже активным доступом сразу попадать в новое главное меню без повторного trial-intro;
- использовать боевой inline/media UX того же класса, что и раньше в `@amonora_v_2_0_bot`: соглашение -> trial -> `Главное меню`, экраны `Моя подписка`, `Продлить`, `Поддержка`, `Информация` и `Бонусная система`, плюс unified-link сценарий через `Ключ` вместо старого Telegram-first reply-keyboard кабинета.

### 2. Пробный доступ

Система уже умеет:

- выдавать trial;
- отслеживать, использовался ли trial раньше;
- ограничивать повторную выдачу trial.
- активировать первый trial сразу на `/start`, если пользователь уже подписан на канал, и для неподписанного пользователя показывать кнопку перехода в канал плюс кнопку `Подписался`, которая перепроверяет подписку и открывает trial без повторного `/start`, не смешивая этот шаг с отдельным paywall-сценарием.
- считать подписку на канал обязательным условием не только для старта, но и для всего активного trial: если пользователь отписывается во время trial, trial ставится на паузу, доступ отзывается, а после повторной подписки до исходного `trial_expires_at` возвращается только оставшееся время без новой выдачи trial;
- при паузе или возобновлении такого trial отправлять пользователю отдельное объясняющее уведомление в `@amonora_bot`, а для уже поставленных на паузу пользователей уметь сделать одноразовый backfill того же уведомления без повторной выдачи trial;
- вести smart trial funnel поверх того же lifecycle: у trial есть persisted-сегмент `low / active`, который поднимается только после первого технического шага (`создание устройства / выдача ключа / QR / routing-pack`), а не после любого клика по меню;
- отправлять segment-aware trial follow-ups через существующий trigger-layer `Amonora Control`: `2 часа`, `24 часа` и финальный `<= 6 часов до конца`, не дублируя их отдельными sent-флагами в `users`;
- не считать бесплатный bridge-ключ на `1 день`, выдаваемый с landing, отдельным trial или отдельным тарифным продуктом.

### 3. Подписка и доступ

Система уже умеет:

- активировать платный доступ;
- продлевать подписку;
- хранить статус подписки;
- определять, активен ли доступ сейчас;
- показывать пользователю состояние доступа.
- выдавать из `Личного кабинета` отдельную user-level `Единую ссылку` на `client.amonoraconnect.com/<token>`;
- открывать по этой ссылке отдельную русскоязычную web-страницу подписки со статусом, сроком, install-flow и блоком `QR + copy` для Happ;
- использовать тот же `client.amonoraconnect.com/<token>` как canonical copy/QR URL для Happ: браузер получает HTML-страницу, а сам клиентский импорт получает subscription feed по client-aware ответу того же маршрута;
- сохранять `client.amonoraconnect.com/sub/<token>` как compatibility feed-route, а не как основной user-facing URL;
- использовать собственный Amonora-owned HTTPS wrapper `client.amonoraconnect.com/happ/add?sub=...` для кнопок `Подключить` в Telegram/web, чтобы открывать Happ без внешнего `happ.lavivas.org` и при этом оставлять fallback `Открыть Happ / Скопировать ссылку / Открыть страницу подписки`;
- использовать этот public subscription surface параллельно текущему device-flow, не заменяя существующие устройства, ключи, QR и add-on slots;
- ограничивать такой user-level feed реальным effective device limit пользователя, а не жёстким `3`: новый Happ-импорт server-side привязывается к slot `1..N`, где `N` совпадает с продуктовым лимитом пользователя, сохраняет реальные device metadata `модель / ОС / версия ОС` из headers/user-agent и не выдаёт рабочий bundle следующему уникальному устройству сверх этого лимита;
- показывать на client page и в Happ один и тот же human-readable server list без технических hostnames, где сейчас наружу раздаются только primary routes `#1 Германия` (`VLESS + Reality + TCP`) и `#1 Дания` (`VLESS + Reality + XHTTP`), без reserve-entries в user-facing unified-link surface;
- держать install-flow на `client.amonoraconnect.com` platform-specific: `Android`, `iOS`, `Windows`, `macOS`, `Linux`, `Apple TV`, `Android TV` получают короткое описание и собственный набор живых официальных ссылок на установку Happ прямо на странице подписки.
- показывать ту же user-level ссылку подписки и связанные с ней bound devices в `dashboard/ui` внутри карточки пользователя, чтобы оператор видел не только legacy `vpn_clients`, но и новые устройства из единой ссылки;
- использовать стандартные paid-тарифы без активной promo-надстройки: `1 / 3 / 6 / 12 месяцев` снова дают базовые `30 / 90 / 180 / 365` дней, а user-facing buy-copy больше не показывает подарочные месяцы.
- legacy Estonia activation seam больше не является рабочей функцией продукта: старый `POST /vpn/activate` переведён в compatibility `410 Gone` и не участвует в обычном user flow.

### 4. Устройства

Пользователь уже может:

- создавать устройства;
- удалять устройства;
- переименовывать устройства;
- менять часть параметров устройства;
- получать ключи для `VLESS` / `Trojan`, а также QR;
- выбирать в интерфейсе бота сначала страну, а затем пользовательский режим `Стабильный`, `Мобильный` или `Резерв` вместо прямого выбора transport-терминов;
- для уже созданного устройства открывать кнопку `Режим` сразу на выборе режима текущего подключения, без повторного шага со страной, если само устройство нельзя переносить между странами;
- видеть в карточке устройства именно текущий режим подключения, без отдельного product-facing поля страны;
- использовать для новых `x-ui`-устройств ключи с panel-side лимитом `1 активный IP` на ключ, чтобы один и тот же ключ не работал одновременно как безлимитный multi-device доступ;
- видеть в `dashboard/ui` device-level IP по live `3x-ui clientIps`, если нода уже пишет IP-record, с честным fallback на сохранённую metadata, если panel-side record ещё отсутствует;
- управлять несколькими устройствами через bot.
- иметь стандартный лимит `3 устройства` на аккаунт, а для администраторов и support-admins расширенный лимит `10 устройств`;
- докупать до `5` дополнительных слотов устройства по `49 ₽` за `+1 слот`, если у пользователя уже есть активная paid-подписка;
- понимать, что такой add-on действует только до конца текущего paid-периода, не переносится автоматически на будущее продление и не выдаёт новый доступ trial/inactive пользователям;
- при достижении лимита видеть в `@amonora_bot` не только стоп-сообщение, но и текущий лимит/остаток plus CTA на покупку `+1 устройство`;
- видеть компактный список созданных устройств прямо в верхнем блоке экрана `Устройства`.

### 4.1. Операторский users-slice

В `dashboard/ui` users-surface теперь также умеет:

- искать пользователей не только по `id / telegram_id / username`, но и по текущему плану / `tariff_code`;
- фильтровать пользователей по конкретным paid-периодам `1 / 3 / 6 / 12 месяцев`, а не только по грубым bucket `trial / paid / none`;
- показывать в `Срез тарифа` явные `1 / 3 / 6 / 12 месяцев` даже как нулевые operator-visible buckets, чтобы нужные периоды не исчезали из среза при пустой выборке.
- в detail-карточке пользователя показывать ссылку подписки `client.amonoraconnect.com/<token>` с copy-action и last access hints;
- в том же detail-контексте отображать unified-link устройства как отдельные view-only карточки `Единая ссылка`, не смешивая их с управляемыми legacy device-actions `Статус / Удалить`.

### 5. Режимы и регионы

На текущем этапе продукт уже поддерживает:

- выбор региона / страны подключения;
- выбор режима подключения после выбора страны;
- режим `Стабильный` как рекомендуемый пользовательский default;
- публичный слой `Стабильный / Мобильный / Резерв`, скрывающий от пользователя реальные transport-детали;
- user-facing `Мобильный` маршрут для Germany и Denmark, который выдаётся как shared import-link без раскрытия transport-деталей в продуктовой copy;
- описание режима `Мобильный` теперь объясняет сценарий сетей, где доступна только часть направлений, без старого временного текста про "скоро появится";
- Denmark `Xray core` primary/reserve profiles как load-bearing seam для `Стабильный` и fallback-веток `Мобильный / Резерв`.
- активными пользовательскими VPN-регионами теперь считаются только Germany и Denmark;
- Estonia больше не участвует в пользовательском VPN-контура и используется как infra-host.

### 6. Оплата

Сейчас в продукте уже есть:

- `Telegram Stars` как основной нативный сценарий;
- автоматическая `СБП` через `Platega`;
- автоматическая криптовалюта через `Platega`;
- скрытые manual `СБП/крипта` как emergency rollback;
- отдельный add-on продукт `+1 устройство до конца текущей подписки`, который проходит через те же `СБП / manual СБП / crypto` seams, но не через `Telegram Stars`;
- для user-side покупки тарифа `СБП` также есть явный emergency runtime fallback: при внешнем сбое provider callback оператор может принудительно увести `СБП` в manual flow без отключения остальных способов оплаты;
- старый `Crypto Pay` seam оставлен в коде как скрытый legacy-path и не считается активным пользовательским способом оплаты.

Важно:

- auto-оплаты через `Platega` должны подтверждаться без ручного review и сразу запускать обычный payment-finalization orchestration;
- `dashboard/ui` now also auto-refreshes open `Platega` records, so operators no longer depend only on a manual `Синхронизировать оплату` click to see fresh provider status;
- manual rollback-оплаты не должны автоматически давать доступ до подтверждения;
- подтверждение и отклонение manual rollback-заявок уже поддерживается через `Amonora Control` и `dashboard`.
- активный пользовательский flow на публичном сайте не должен вести в отдельную веб-оплату; сайт ведёт пользователя в Telegram-first контур.
- в RUB-сценариях теперь есть внутренний `Баланс`, который автоматически списывается до внешней оплаты;
- если Баланса хватает полностью, доступ может активироваться без внешнего платежа;
- если Баланса хватает полностью, add-on `+1 устройство` тоже может активироваться без внешнего checkout, но остаётся отдельным product-type и не продлевает подписку;
- `Telegram Stars` остаются отдельным путём и не смешиваются с Балансом.
- в `@amonora_bot` now also exists a separate `Пополнить баланс` user flow through `Platega`, so RUB can be deposited in advance and later spent on tariff purchase/renewal from the internal balance.
- user-side payment entrypoints now reuse an already open invoice/request for the same semantic product (`tariff`, `device-slot add-on`, or `balance top-up`) instead of creating a second active payment by switching methods mid-flow.

### 6.1. Рефералы и Баланс

На текущем этапе:

- система продолжает хранить денежный `Баланс` в рублях;
- первая подтверждённая оплата приглашённого пользователя теперь даёт бонус обоим участникам: пригласившему и приглашённому;
- за первую подтверждённую оплату приглашённого по обычному тарифу начисляется `50 ₽` обоим участникам, а для тарифа `12 месяцев` — `100 ₽`;
- бонус привязывается к конкретному `PaymentRecord` и начисляется только один раз на приглашённого пользователя;
- Баланс по-прежнему показывается в `Личном кабинете`;
- Баланс автоматически используется при оплате RUB-тарифов;
- внутренний ledger Баланса для начислений, резервов, списаний и release остаётся рабочим;
- user balance changes are now also visible to operators as a per-user running history in `dashboard/ui`, not only as raw payment rows;
- в `@amonora_bot` снова доступен отдельный экран `Реферальная система` со ссылкой, текущим балансом, общим заработком, счётчиками `приглашено / оплатили`, уровнем и прогресс-баром;
- `/start` поддерживает привязку по `ref_<ref_code>`, а старый формат по Telegram ID остаётся совместимым как legacy fallback;
- при переходе друга по ссылке пригласившему уходит отдельное уведомление;
- после первой подтверждённой оплаты уведомления о реферальной награде получают обе стороны.
- referral reward delivery теперь централизована на confirmed-payment seam: начисление и отправка пишутся в event log, bot/in-app уведомления антидублируются, текст приглашения стал многострочным, а дополнительный push webhook можно подключить через env без изменения payment-логики.
- в изолированном `@amonora_v_2_0_bot` бонусный раздел теперь умеет принимать промокоды и подарочные коды: процентный код ставит скидку на ближайшую оплату подписки, а коды на дни и подарочные коды сразу продлевают доступ через тот же shared subscription/access layer.
- тот же `@amonora_v_2_0_bot` теперь умеет покупать подарочную подписку через реальные user payment flows `СБП / ручная СБП / криптовалюта`, после чего покупателю выдаётся одноразовый gift-code для передачи другу.

### 7. Поддержка

Пользователь уже может:

- перейти в отдельный support bot;
- создать обращение;
- вести диалог с командой;
- получать ответы в рамках тикетного сценария.
- видеть короткий support intro-screen в основном боте до перехода в `@amonora_support_bot`.

### 7.1. Информация в боте

Основной бот уже умеет показывать отдельный раздел `📚 Информация`.

Внутри него доступны:

- краткие инструкции;
- FAQ;
- ссылки на публичные документы;
- ссылка на публичную оферту выводится прямо в единственном стартовом сообщении для нового пользователя;
- канал проекта;
- быстрый переход в поддержку.

## Support и операционные функции

### support_bot

Support-контур уже умеет:

- принимать обращения;
- создавать тикеты;
- назначать ответственного;
- передавать диалог;
- закрывать обращение;
- хранить историю;
- сохранять полную историю тикета в БД без автоматического подрезания старых сообщений и без автоудаления закрытых обращений только по возрасту;
- сохранять `file_id` и метаданные Telegram-вложений в истории тикета;
- пересылать фото, видео и аудио операторам как реальные медиа, а не только preview-текст;
- открывать эти вложения в `dashboard/ui` как inline-preview и отдельные прямые ссылки `Открыть фото / видео / аудио`;
- показывать администраторам только последние `5` обращений на экран и не раздувать inline-списки при большом числе тикетов;
- считать dashboard/support counts через SQL-агрегаты, а не через полный проход по всей очереди;
- обслуживать только клиентскую поддержку, без системных уведомлений и payment review.

### Amonora Control

Internal контур уже умеет:

- принимать typed системные события через единый dispatcher;
- доставлять уведомления в личные сообщения разрешённым admin ID;
- показывать новый operational shell `/dashboard`, `/status`, `/nodes`, `/payments`, `/users`, `/user`, `/problems`, `/support`, `/login_codes`, `/notifications`, `/events`, `/settings`, `/broadcast`, `/help`;
- делать review ручных оплат через `confirm / reject`;
- присылать 5-минутные коды входа в Панель управления вместо support-бота;
- показывать masked историю auth-кодов и активные dashboard sessions прямо в Telegram;
- открывать карточку пользователя по `/user`, показывать devices/payment/support context и выполнять `sync / deep repair / trial / extend / block / clear-access`;
- считать аудиторию `device_limit_reached` и user/payment/support device context по реальному effective limit пользователя, а не по старому жёсткому `x/3`;
- открывать support-диалоги, брать обращение, отвечать, передавать и закрывать их через те же backend/storage seams, что использует Панель управления;
- показывать блок `Проблемы` по цепочке `payments -> repair -> support -> nodes` с быстрыми переходами в нужный объект;
- открывать ноды в detail-focus и выполнять `health check / restart / maintenance / обновить статус(refresh)` без перехода в веб-панель, не маскируя обычный refresh под “глубокий resync”;
- антидублировать node / infra alerts через dedupe + cooldown;
- автоматически поднимать control-events по деградации/падению нод, по не-`active` состоянию ключевых локальных сервисов и по user-access инцидентам `vpn_repair_needed`, с recovery-событием при восстановлении;
- хранить masked auth-коды и event log в PostgreSQL как `ControlNotificationEvent`;
- держать per-admin notification preferences в БД и применять их поверх глобальных env category toggles, включая новые buckets `support`, `security`, plus finer-grained toggles for `new users / trials / access keys`;
- показывать активные dashboard sessions и owner-only `terminate all`;
- принимать пересланный пост из Telegram-канала и навешивать на исходный channel post inline URL-кнопки по простому текстовому формату, включая сценарий очистки текущих кнопок без переотправки самого поста;
- давать owner/admin-only `/channel` surface для контент-плана канала: `Новая тема`, `Ближайшие`, `Черновики`, `Одобрить`, `Редактировать текст`, `Отклонить`, `Повторить генерацию`, `Опубликовать сейчас`, `Статистика`;
- использовать channel-content MVP через PostgreSQL как source of truth: `channel_content_items`, `channel_post_touches`, OpenAI-generated drafts с safety-validator, scheduled generate/publish через internal dashboard endpoints и tracked CTA-конверсии `post -> bot start -> trial/payment`;
- держать отдельный experimental `daily_news` автоконтур в `n8n`: три слота в день по `Europe/Moscow`, OpenRouter-generated HTML-посты про интернет/приватность/технологии, автопубликация через внутренний dashboard publish-endpoint и резервный evergreen fallback, если релевантной новости на слот не нашлось;
- давать owner-only блок `Рассылка / Триггеры` с:
  - admin push;
  - manual user campaigns;
  - DB-driven automatic triggers;
  - template management;
  - delivery/click/conversion stats без fake open-rate метрик;
- использовать `amonora-access-reminders.service/.timer` как общий 5-минутный worker для scheduled campaigns, user triggers и periodic incident scan по `nodes / services / users`;
- использовать `users.last_activity_at` как источник истины для inactivity-сегментов и inactivity-trigger sends.
- использовать тот же worker и `ControlTriggerDeliveryLog` для smart trial funnel: `trial_hours_since_start` и `trial_hours_before_expiry` работают поверх `trial_started_at / trial_expires_at`, channel-pause правил и persisted trial-сегмента без отдельного `n8n`-оркестратора.
- во время ограниченных promo-окон подменять trial-expiry conversion copy в user reminders / trigger sends на акционный оффер с конкретным диапазоном дат вместо постоянного evergreen текста.
- держать сокращённый operational shell без лишних back/duplicate кнопок, с компактным `/start`, короткими node/payment notifications, support/problem screens и review ручных оплат прямо в Telegram без panel deep-links.

### dashboard / Панель управления

Административный контур уже умеет:

- вход по логину, паролю и Telegram-коду;
- работать как новый `Amonora Control` shell в `dashboard/ui`, где старый backend-rendered `dashboard` page-shell больше не используется как рабочий интерфейс;
- соблюдать роль-модель `Владелец / Тех. администратор / Менеджер` не только по кнопкам, но и по navigation/API read/action boundaries;
- просмотр пользователей;
- просмотр доступа и подписок;
- показывать user-status слой control center: `Активен`, `Пробный`, `Без доступа`, `Заблокирован`, `Ожидает оплату`, `Ошибка синхронизации`, `Требует ремонта`;
- показывать в user detail баланс, лимит устройств и расширенную device-карту с `тип / IP / регион / нода / last seen`;
- обновлять user detail по явной кнопке `Обновить` без ожидания обычного `15s` detail-cache и одновременно подтягивать свежую строку пользователя и верхние users-метрики;
- показывать в device-карточке отдельный человекочитаемый `Режим` (`Стабильный / Мобильный / Резерв`), не смешивая его с техническим `Профилем`;
- показывать в users/detail не только итоговый device limit, но и `base limit / active extra slots / ближайшее истечение add-on`;
- видеть пользователей, у которых VPN-состояние требует ручного ремонта;
- запускать точечную server-side проверку `Статус` для одного устройства и видеть в той же карточке упрощённый статус исправности ключа `🟢 Исправен / 🔴 Сломан` с причиной и временем проверки;
- запускать `Синхронизировать` и `Глубокий ремонт` из user detail, payment context и support context;
- видеть последние попытки ручного VPN repair в user detail;
- видеть user-level repair issues прямо на overview в блоке `Needs attention`;
- видеть минимальный `System status` блок на overview для backup/support/manual payments, включая stale pending confirmations;
- видеть payment-related repair cases в overview attention, если post-payment flow дошёл до `vpn_repair_needed`;
- видеть на overview самые старые pending manual payments с быстрым переходом в нужный payment record;
- видеть в payment detail связанный user/access/support context без отдельного ручного поиска по трём экранам;
- отправлять из `payments` отдельное напоминание пользователю по открытой заявке `Ручная СБП`, если он создал/отправил заявку, но не завершил оплату: reminder ведёт в поддержку за реквизитами и даёт прямую отмену заявки;
- держать отдельную вкладку `Аналитика` в `dashboard/ui`, где оператор может создать marketing/campaign `start`-ссылку для оффера, сразу получить tracking URL для Telegram и видеть по каждой кампании быстрый funnel `переходы -> start -> пробный -> ключ -> оплаты -> продления`;
- открывать ту же аналитику по старому compatibility route `/dashboard/analytics`, который мягко редиректит в новый UI `/analytics`, не ломая старые operator bookmarks;
- держать отдельную вкладку `Промокоды` в `dashboard/ui`, где оператор видит таблицу кодов, их тип (`скидка / дни доступа / подарочный`), лимит и фактические активации, покупателя подарка и срок действия;
- создавать там же новые промокоды через встроенный генератор: можно задать собственный код или auto-code, выбрать процент скидки либо количество дней доступа, лимит активаций и срок жизни кода;
- обрабатывать payment-status flow `ожидает оплату / ожидает подтверждения / подтверждён / отклонён / истёк / спорный / ошибка` прямо из control center;
- показывать add-on оплаты `+1 устройство` в `payments` с product-aware label вместо маскировки под обычный tariff code;
- после payment confirm запускать тот же payment-finalization orchestration, что и основной payment flow, с продлением доступа, post-payment sync, repair-marker логикой и пользовательским уведомлением;
- дополнительно прогонять product-aware payment reconcile в `amonora-access-reminders`, чтобы confirmed-платёж, переживший partial failure между confirm и side effect, мог сам восстановить access/add-on/top-up эффект без ручной магии;
- не позволять создавать из панели уже `confirmed` не-ручные платежи в обход нормального review/provider lifecycle;
- держать owner-only guard на ручное создание, подтверждение, отклонение и жёсткую смену статуса платежей, а также на изменение `.env` через control center;
- держать `support_admin` только в support-операциях без dashboard-доступа к users/payments;
- ограничивать runtime role-permission overrides allowlist-матрицей, чтобы toggles в settings не могли эскалировать `support_admin` или `tech_admin` за пределы их базового контракта;
- писать в audit для смены `.env` и admin-access не только сам факт действия, но и `before / after`, а при смене роли или деактивации администратора сразу отзывать его активные dashboard sessions;
- возвращать пользователю обычное меню после разблокировки и отправлять user-facing push при `блокировке / разблокировке / оплате / продлении`;
- держать finance-ledger внутри payments surface, но скрывать его для роли менеджера;
- показывать в user detail не только последние платежи, но и running balance history пользователя с начислениями, резервами и списаниями;
- видеть backup health в overview не только как один freshness flag, но и как per-source срез по `core / vpn-de / vpn-ee`, если локальные backup roots доступны;
- управление устройствами;
- работу с платежами;
- работу с support-очередью, включая `назначить / передать / ответить / закрыть`;
- открывать вложения из support history через backend attachment-route;
- сохранять многострочный формат support-сообщений в `dashboard/ui` и позволять операторам отвечать через многострочное поле, где `Enter` создаёт новую строку;
- держать отдельный экран `Audit log` в `dashboard/ui` для реальных административных действий по пользователям, платежам, support и серверам;
- показывать `Audit log` в компактном table-first виде с русскими label'ами действий и целей вместо длинной card-ленты;
- показывать в topbar `dashboard/ui` роль администратора и текущее время/дату в часовом поясе `Asia/Yekaterinburg`;
- хранить очищенные уведомления `dashboard/ui` в browser-side persistence, чтобы они не возвращались сразу после reload/refetch того же notification feed;
- открывать из support detail реальный профиль пользователя по внутреннему `users.id`, а не по ticket-side идентификатору, и запускать оттуда safe quick actions `Синхронизировать`, `Глубокий ремонт`, `Выдать trial`, `Продлить 30 дней`;
- держать новый визуальный shell `Amonora Control` в `dashboard/ui` с full-screen mobile drawer, обновлённым auth-flow, более выраженным mission-control overview и операционной навигацией без возврата в старый Jinja-shell;
- считать backend-rendered `dashboard` page-shell выведенным из активного использования: исторические `GET /dashboard/*` page-routes теперь должны работать только как compatibility redirects в новый UI;
- просмотр серверов и сервисов;
- выполнять по нодам `restart / health check / maintenance / migration`;
- выполнять migration консервативно: только для устройств с явной привязкой к исходной ноде, без автоперевода сервера в `maintenance`, если часть устройств требует ручного разбора;
- показывать 24-часовой traffic layer по нодам, странам, протоколам и нагрузке;
- автоматически сбрасывать накопленный traffic baseline с 1-го числа месяца через активный watchdog/runtime seam, не затрагивая live throughput и текущую нагрузку нод;
- держать лёгкий analytics contour для `Telegram channel -> bot -> access -> payment` через PostgreSQL `analytics_*` tables и 10-минутный refresh worker, а не через отдельный clickstream/telemetry stack на core;
- публиковать repo-managed Grafana suite на `https://grafana.amonoraconnect.com/` с полностью русскоязычными каноническими dashboards `Главная Amonora`, `Воронка роста`, `Источники и посты`, `Выручка и монетизация`, `Удержание и отток`, `Качество подключения`, `Операции и ремонты`, `Алерты и инциденты`;
- держать strict growth-money contour внутри того же suite: `Главная` остаётся коротким обзором, `Воронка роста` работает как компактная `Воронка подключения`, слово `onboarding` из UI убрано в пользу `Начало подключения / Готов к подключению`, а полный путь `переход по ссылке -> бот -> подписка на канал -> ключ -> оплата -> подключение -> продление` и quality/integrity вынесен в тематические вкладки без перегруженного home-экрана;
- давать owner/operator drill-down по `source_key` / `start_param` только через rollup tables, а не через live joins к operational tables;
- показывать в Grafana machine-readable `source_key_integrity` и `growth_active_users` как часть свежести/quality слоя;
- держать owner/growth и ops/reliability аналитику в одном operator-only suite, не смешивая её с raw operational queries;
- разделять в analytics и в Grafana первые paid-активации и настоящие продления: `subscription_activated`, `subscription_renewed`, `payment_kind = new / renewal`, `Выручка новых`, `Выручка продлений`, `Общая выручка`;
- использовать для operator Grafana надёжные rollups `analytics_daily_stage_counts`, `analytics_daily_revenue`, `analytics_daily_connection`, `analytics_daily_payment_failure_reasons`, `analytics_daily_attribution_integrity`, `analytics_cohort_retention` и ops-only rollups `analytics_hourly_ops_incidents`, `analytics_hourly_ops_snapshots`, `analytics_runtime_status`, чтобы panels не ходили напрямую в `users`, `payment_records`, `vpn_client_activations`, `finance_entries` или `control_notification_events`;
- доставлять Grafana alerting в привычный Telegram control path через внутренний guarded webhook на core вместо отдельного внешнего paging-stack;
- отправлять новые growth/revenue anomaly alerts (`bot_start -> config`, `config -> payment`, `payment_started -> payment_success`, `paid -> connected gap`, `source_key_integrity`) через тот же guarded Grafana bridge без отдельного alert stack.
- не подменять пользовательский IP device-hostname'ом в user detail: если реальный IP не найден, панель теперь показывает `—`, а не misleading host fallback;
- изменение тарифов;
- доступ к документации;
- базовый операционный контроль.

## Публичный контур

### landing

Публичный сайт уже решает такие задачи:

- объясняет продукт;
- выдаёт бесплатный временный ключ подключения на `24 часа` как bridge-access сценарий для случаев, когда пользователю сначала нужно открыть Telegram;
- показывает текущие тарифы доступа прямо на главной странице, синхронизированные с рабочими ценами Telegram-first контура;
- использует тарифный блок как витрину и ведёт к покупке только через `@amonora_bot`, без отдельной веб-кассы в активном landing-flow;
- принимает provider webhook для auto-платежей `Platega`, не превращаясь в отдельную публичную веб-кассу;
- показывает cookie controls не только на главной, но и на `/manual` и legal-страницах того же runtime seam;
- отвечает на частые вопросы в компактном FAQ-блоке прямо на главной странице;
- показывает Германию и Данию как две основные пользовательские точки подключения;
- подаёт `Amonora` как основной пользовательский продукт экосистемы, а не как отдельный сайт для разовой выдачи конфигов;
- использует CTA-first cinematic landing с короткими технологичными текстами, космическим visual hook и акцентом на Telegram control;
- скрывает публичные технические детали подключения за формулировкой `Автоматическая система подключения`;
- ведёт в bot и support;
- содержит правовые страницы;
- публикует контакты владельца и email для обратной связи;
- показывает кнопку на `/manual` после успешной выдачи bridge-ключа и при этом не выносит инструкцию в основную публичную навигацию;
- обслуживает отдельный tokenized host `client.amonoraconnect.com` для user-level страницы подписки и feed-импорта в клиент;
- поддерживает часть публичного web-контура.

### Telegram-канал

У проекта есть Telegram-канал [`@amonora_new`](https://t.me/amonora_new).

Он нужен для:

- обновлений;
- анонсов;
- новостей проекта;
- усиления доверия через публичное присутствие бренда.

## Внутренние и системные функции

Система уже поддерживает:

- PostgreSQL как единый data-layer;
- административные сессии;
- аудит действий;
- отдельный internal event log для `Amonora Control`;
- финансовые записи;
- считать operator-facing `Выручку` как подтверждённые `Platega` оплаты только по `СБП` и `крипте`, не смешивая этот показатель с manual rollback-платежами и legacy `Crypto Bot`;
- управляемые серверы;
- базовые server/watchdog сценарии;
- безопасный одиночный auto-retry для свежих VPN sync failure после оплаты и ручного repair;
- видимость restore-readiness в overview только на основе machine-readable restore proof status-file; `healthy` допустим только при явном `proof_kind / proof_status / proof_scope`, а legacy validation JSON без proof-полей должен считаться `unknown`;
- нормализованные repair reasons для payment/access/VPN слоёв (`post_payment_*`, `manual_repair_*`);
- human-readable labels for repair reasons in overview, user detail and payment context;
- нормализованные `repair source / outcome` поля в user detail и payment-linked repair history, чтобы история repair не была чёрным ящиком;
- в support admin-bot список диалогов теперь ограничен коротким безопасным slice вместо длинной клавиатуры на десятки обращений;
- в панели управления users-surface теперь есть кешированный признак подписки на канал `@amonora_new`, показывающий `подписан / не подписан / не проверено` без жёсткой зависимости от Telegram API на каждом клике;
- actionable support slice в overview с коротким списком старейших open tickets;
- compact user issue summary inside payment detail for repair/access context;
- лёгкий priority-layer в overview (`high / medium / low`) для repair, support, payments, backup и restore signals;
- лёгкий auto-escalation слой в overview для старых repair/payment/support проблем без notifications и фоновой infra;
- быстрые operator shortcuts из overview/payment/support contexts, включая inline `Repair VPN` там, где уже есть safe API;
- very limited batch repair from overview for a small visible slice of repair-needed users;
- lightweight guardrails now disable obviously invalid repair actions (`no access` / `no devices`) before execution;
- repair actions now return clearer operator-facing feedback (`succeeded` / `skipped` / `failed`) across overview, user detail and payment context;
- both admin UIs now include a frontend-quality pass that:
  - delays chart rendering until containers have a real size;
  - removes percentage-height Recharts usage from the main `dashboard/ui` chart pages;
  - gives visible form fields explicit `id` / `name` coverage across `dashboard/ui` and legacy `dashboard`;
- a standalone Denmark VPN runtime now exists at `dk.amonoraconnect.com` as a clean `Xray core` host with `VLESS + Reality + XHTTP`;
- VLESS provisioning is now provider-aware:
  - `de` continues through `3x-ui` / `XUIClient`;
  - `dk` now uses a standalone `Xray core` provisioner instead of pretending to be a panel-backed region;
- Denmark now also operates as the current golden anti-DPI node with:
  - `www.apple.com` camouflage;
  - primary `443` profile on `XHTTP packet-up`;
  - reserve `8443` profile on `XHTTP packet-up`;
  - explicit DoH upstreams (`cloudflare-dns.com`, `dns.sb`, `localhost`) and `loglevel = none`;
  - documented `fingerprint = chrome` and distinct primary/reserve `shortId` values;
- Germany and Denmark are the only active product VPN runtimes:
  - Germany stays on `3x-ui` / `XUIClient`;
  - Denmark stays on standalone `Xray core`;
  - Estonia is retired from the product VPN contour and reused as infra-host;
- official client routing artifacts now exist for `v2rayNG`, `Nekoray`, and `Streisand`, including split/full-tunnel policy, JSON import packs, QR/onboarding references, and MTU guidance (`1400` default / `1420` fallback);
- the main bot can now send a device-matched `Маршруты РФ` JSON pack so clients with split-routing support keep Russian destinations direct and route foreign traffic through VPN;
- Estonia is no longer part of the active user-facing region choice and remains only as retired legacy metadata plus infra-host role;
- Denmark is part of the normal user-facing region choice alongside Germany;
- user-facing device region labels now deliberately remain short and clean (`Германия`, `Дания`) without `stable/test` suffixes;
- active admin naming on the main visible surfaces now uses `Панель управления` instead of the older `Dashboard` wording;
- the active control-center settings now visibly cover `Роли`, `Уведомления`, and `Интеграции`, instead of leaving those `TZ v5` slices implicit in backend-only payloads;
- `@amonora_control_bot` now works as an operational shell for `Dashboard / Users / Payments / Problems / Nodes / Support / Login codes / Notifications`, with role-aware notification defaults and mandatory categories that cannot be disabled for critical duties;
- user access actions now report partial sync failure truthfully, so an operator is no longer told that `trial / extend / clear access` fully succeeded when part of the node state stayed broken;
- the standard `Синхронизировать` action is now a soft access sync that updates remote access state without reissuing device keys; destructive key/config regeneration remains limited to `Глубокий ремонт`;
- deep repair now includes a post-repair verification pass and can finish in a visible `needs repair` state instead of a false-clean success;
- key anti-sharing is now capability-driven instead of pretending every region uses the same runtime seam: Germany still enforces `VPN_MAX_DEVICES_PER_KEY` via `3x-ui limitIp`, Denmark `xray_core` uses a log-driven lease worker that supports `N active IPs`, per-key whitelist entries and soft-limit telemetry, while Estonia is treated as retired infrastructure and no longer participates in product anti-sharing logic.
- dashboard user detail now exposes available device technical data (`OS`, model, MAC, live/stored IP, transport/profile, anti-sharing scope`) through a stable `technical` payload and additionally includes an operator-facing anti-sharing policy summary so staff can see which enforcement model is actually behind a given device/runtime;
- manual-payment delete/status paths now protect confirmed records and release reserved balance on terminal non-confirmed outcomes;
- node health now treats runtime service failure (`xray / 3x-ui`) as part of the overall state instead of only reflecting host metrics;
- `ops/server_watchdog.py` no longer opens `node_offline` incidents for pure SSH-monitoring gaps when the real VPN runtime is still healthy, reducing false admin paging during node-side `ufw limit 22/tcp` throttling;
- the support surface now avoids claiming guaranteed client notification on close when Telegram delivery cannot be proven end-to-end;
- dashboard support reply now also returns a structured operator-facing error when Telegram rejects delivery (for example, the user blocked `@amonora_support_bot`), instead of bubbling an HTML 500 page into the Next.js control center;
- the traffic page now explicitly distinguishes server throughput from synthetic operational activity for the last-24h event curve;
- документацию, доступную из админки.

## Что уже рабочее, но ещё не финализировано

На текущем этапе уже видны рабочие, но не полностью финализированные зоны:

- `dashboard` и `dashboard/ui` работают как backend + основной UI Панели управления;
- финансовый контур уже есть, но ещё не выделен как отдельный зрелый модуль;
- отзывы пользователей как отдельный поток ещё не закреплены в одной канонической точке;
- платёжный контур уже рабочий, но часть сценариев всё ещё остаётся ручной.

## Что относится к следующему этапу роста

С учётом текущего позиционирования `Amonora` как экосистемы, следующий слой развития уже просматривается:

- усиление автоматизации;
- развитие AI-направлений;
- расширение внутренних сервисов;
- расширение публичного продуктового слоя вокруг текущего VPN-контура.

## Planned / future modules

Ниже перечислены не текущие реализованные функции, а модули следующего этапа роста.

### Automations

Первый production-slice automation уже появился внутри текущего продукта.

Что уже есть:

- local-only `n8n` runtime на core host;
- repo-managed workflows для `generate_due_channel_drafts`, `publish_approved_channel_posts` и `remind_missing_channel_content`;
- internal dashboard endpoints `POST /dashboard/api/internal/channel/generate` и `POST /dashboard/api/internal/channel/publish`;
- Python-side OpenAI generation для канал-черновиков, а не AI-логика внутри `n8n`.

Следующее направление роста:

- Telegram automation;
- business-боты;
- автоответы и простые AI-сценарии.

### Data

Будущий слой для:

- мониторинга;
- сбора данных;
- парсинга;
- алертов и data-driven сценариев.

### AI

Будущий слой для:

- AI-помощников;
- AI-ботов;
- поддержки;
- контентных и классификационных сценариев.

Важно:

более широкий слой automations/AI всё ещё относится к direction of growth и не должен восприниматься как полностью реализованная часть текущего продукта `Amonora`.

## Итог

Если описать продукт совсем кратко:

`Amonora` уже умеет выдавать доступ, управлять устройствами, обрабатывать оплаты, принимать обращения, поддерживать работу команды через админку и обслуживать публичный контур через сайт и Telegram-канал.

Это уже рабочая система, а не прототип, но часть контуров всё ещё находится в переходной фазе между текущей боевой реализацией и целевой зрелой структурой.

Актуально для `Amonora Control`:

- активный control-center использует компактный matte/glass UI в светлой пепельной и тёмной пепельной темах;
- `users / payments / servers` работают в табличном операторском виде с компактными overlay-анкетами;
- knowledge/docs markdown в `dashboard/ui` проходит server-side HTML sanitization: raw `script/style/iframe`, inline event handlers и `javascript:` / `data:` URLs не должны попадать в операторскую панель;
- `support` показывает медиа-вложения прямо в диалоге, а не только ссылками;
- `settings` умеет менять роли админов, персональные notification preferences и runtime-permission overrides для `tech_admin` и `manager`;
- dropdown уведомлений в shell можно локально очистить, а toast-уведомления отображаются как отдельные bottom-right push cards.
