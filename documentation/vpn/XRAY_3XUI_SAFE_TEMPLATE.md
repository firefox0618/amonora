# AMONORA — SAFE XRAY/3X-UI CONFIG TEMPLATE
Дата: 19 марта 2026

---

# ЦЕЛЬ

Этот шаблон нужен не для резкого переворота продa, а для **безопасного внедрения нового inbound-профиля для новых выдач**.

Принцип:
- **старых пользователей не трогаем**
- **текущие рабочие inbound не ломаем**
- **новый inbound создаём отдельно**
- **сначала тест на себе**
- **потом только новые пользователи**

Официальная документация Xray подтверждает:
- для `VLESS` на сервере поле `decryption` должно быть `"none"`; это нельзя оставлять пустым. citeturn582078search2
- транспорт на обеих сторонах должен быть симметричным: если выбран `tcp`, то клиент и сервер должны использовать один и тот же transport. citeturn582078search0
- fallback официально поддерживается для `VLESS` и `Trojan`, но это уже следующий этап, а не первая безопасная правка. citeturn582078search7turn582078search5

---

# 1. ЧТО ДЕЛАЕМ СЕЙЧАС

Нужна **консервативная схема**:

## Germany
- оставить текущий рабочий inbound как есть
- добавить **новый отдельный inbound** только для новых клиентов
- transport: `tcp`
- security: `reality`
- отдельный `SNI`
- отдельный набор `shortId`

## Estonia
- оставить текущий рабочий inbound как есть
- добавить **новый отдельный inbound** только для новых клиентов
- transport: `tcp`
- security: `reality`
- отдельный `SNI`
- отдельный набор `shortId`

---

# 2. БЕЗОПАСНАЯ СТРАТЕГИЯ ПО НОДАМ

## Germany — основная нода
Рекомендуемый профиль:
- protocol: `VLESS`
- network: `tcp`
- security: `reality`
- decryption: `none`
- flow: без экзотики, совместимый с твоими клиентами
- отдельный SNI для Germany

### Рекомендуемые SNI для Germany
Выбери **один** для нового inbound:
- `www.microsoft.com`
- `login.microsoftonline.com`
- `www.bing.com`

Не смешивай несколько SNI в одном inbound. Делай:
> **один inbound = один SNI**

---

## Estonia — резервная нода
Рекомендуемый профиль:
- protocol: `VLESS`
- network: `tcp`
- security: `reality`
- decryption: `none`
- отдельный SNI, отличный от Germany
- отдельный набор `shortId`

### Рекомендуемые SNI для Estonia
Выбери **один** для нового inbound:
- `www.cloudflare.com`
- `www.apple.com`
- `www.amazon.com`

---

# 3. ЧЕГО НЕ ДЕЛАТЬ

❌ не переводить существующий Germany inbound на новый SNI  
❌ не менять shortId у уже выданных клиентов  
❌ не трогать массово рабочие UUID  
❌ не включать `xhttp` прямо сейчас  
❌ не включать PQ-режим, если уже был кейс клиентской несовместимости  
❌ не обновлять 3x-ui/Xray перед этой правкой  

---

# 4. ШАБЛОН ПАРАМЕТРОВ ДЛЯ 3X-UI

Ниже — **не команда для слепой вставки**, а эталон параметров, по которым надо создать **новый inbound** в 3x-ui.

---

## Germany — новый inbound для новых клиентов

### Идея имени
`vless-reality-tcp-de-new`

### Параметры
```json
{
  "listen": "",
  "port": 443,
  "protocol": "vless",
  "settings": {
    "clients": [],
    "decryption": "none"
  },
  "streamSettings": {
    "network": "tcp",
    "security": "reality",
    "realitySettings": {
      "show": false,
      "dest": "www.microsoft.com:443",
      "xver": 0,
      "serverNames": [
        "www.microsoft.com"
      ],
      "privateKey": "REPLACE_WITH_GERMANY_PRIVATE_KEY",
      "minClientVer": "",
      "maxClientVer": "",
      "maxTimeDiff": 0,
      "shortIds": [
        "a1b2c3d4",
        "b2c3d4e5",
        "c3d4e5f6",
        "d4e5f607"
      ]
    },
    "tcpSettings": {
      "acceptProxyProtocol": false,
      "header": {
        "type": "none"
      }
    }
  },
  "sniffing": {
    "enabled": true,
    "destOverride": [
      "http",
      "tls"
    ]
  }
}
```

### Пояснение
- `decryption: "none"` — это корректное серверное значение для VLESS. citeturn582078search2
- `network: "tcp"` — это совпадает с твоим текущим стабильным продовым transport.
- `serverNames` и `dest` должны совпадать по логике маскировки Reality. Это следует из официальной схемы transport/reality. citeturn582078search0
- `shortIds` должны быть **другими**, не как на Estonia.

---

## Estonia — новый inbound для новых клиентов

### Идея имени
`vless-reality-tcp-ee-new`

### Параметры
```json
{
  "listen": "",
  "port": 443,
  "protocol": "vless",
  "settings": {
    "clients": [],
    "decryption": "none"
  },
  "streamSettings": {
    "network": "tcp",
    "security": "reality",
    "realitySettings": {
      "show": false,
      "dest": "www.cloudflare.com:443",
      "xver": 0,
      "serverNames": [
        "www.cloudflare.com"
      ],
      "privateKey": "REPLACE_WITH_ESTONIA_PRIVATE_KEY",
      "minClientVer": "",
      "maxClientVer": "",
      "maxTimeDiff": 0,
      "shortIds": [
        "1a2b3c4d",
        "2b3c4d5e",
        "3c4d5e6f",
        "4d5e6f70"
      ]
    },
    "tcpSettings": {
      "acceptProxyProtocol": false,
      "header": {
        "type": "none"
      }
    }
  },
  "sniffing": {
    "enabled": true,
    "destOverride": [
      "http",
      "tls"
    ]
  }
}
```

---

# 5. TROJAN ШАБЛОН — НЕ ТРОГАТЬ, НО ДЕРЖАТЬ КАК FALLBACK

Trojan у тебя уже полезен как запасной путь. Официально fallback-функция поддерживается и для Trojan, но это отдельный этап. citeturn582078search7

Сейчас логика такая:
- Germany Trojan оставить на `8443/tcp`
- Estonia Trojan оставить на `8443/tcp`
- не менять сертификаты/поведение без причины
- использовать как fallback для проблемных клиентов

---

# 6. ЧТО ДЕЛАТЬ С КЛИЕНТСКОЙ ССЫЛКОЙ

Для новых VLESS Reality ссылок держи принципы:

- `type=tcp`
- `security=reality`
- `encryption=none`
- **не включать** PQ-параметры, если панель пытается их автоматически протолкнуть
- `fp=chrome` как базовый совместимый fingerprint
- `sni` должен совпадать с выбранным inbound SNI
- `sid` должен соответствовать одному из `shortId`
- имя импорта — ASCII-safe

---

## Пример ссылки для Germany
```text
vless://UUID@ffconnect.amonoraconnect.com:443?type=tcp&security=reality&pbk=GERMANY_PUBLIC_KEY&fp=chrome&sni=www.microsoft.com&sid=a1b2c3d4&encryption=none#AMONORA-GERMANY
```

## Пример ссылки для Estonia
```text
vless://UUID@connect.amonoraconnect.com:443?type=tcp&security=reality&pbk=ESTONIA_PUBLIC_KEY&fp=chrome&sni=www.cloudflare.com&sid=1a2b3c4d&encryption=none#AMONORA-ESTONIA
```

---

# 7. ЧТО МОЖНО ОСТАВИТЬ ОБЩИМ, А ЧТО НЕЛЬЗЯ

## Можно оставить общим
- общий подход `VLESS + Reality + TCP`
- порт `443`
- общий клиентский fingerprint `chrome`
- общую логику выдачи через бот

## Нельзя оставлять одинаковым
- набор `shortId`
- SNI на обеих нодах
- import labels, если хочешь лучше разделять маршруты в саппорте
- новый inbound-идентификатор в панели

---

# 8. КАК ВНЕДРЯТЬ БЕЗ ЛОМКИ

## Шаг 1
Сделать backup:
- экспорт inbound Germany
- экспорт inbound Estonia
- SQL dump
- env backup

## Шаг 2
Создать **новый inbound** на Germany  
Старый inbound не трогать.

## Шаг 3
Выдать тестовый конфиг **себе**
Проверить:
- импорт ссылки
- соединение
- открытие нескольких сайтов
- поведение на мобильном клиенте
- поведение на desktop-клиенте

## Шаг 4
Создать **новый inbound** на Estonia  
Старый inbound не трогать.

## Шаг 5
Повторить тест на себе.

## Шаг 6
Начать выдавать **только новым пользователям**:
- сначала 1–2 новым
- потом, если нет жалоб, расширять

## Шаг 7
Старых пользователей переводить только:
- при ручной проблеме
- при осознанном запросе
- после индивидуального теста

---

# 9. ЧЕКЛИСТ ПРОВЕРКИ Germany inbound

- [ ] Старый inbound не изменён
- [ ] Создан новый inbound с новым названием
- [ ] Указан отдельный SNI
- [ ] Указан новый набор shortId
- [ ] `decryption=none`
- [ ] `type=tcp`
- [ ] `security=reality`
- [ ] Ссылка импортируется
- [ ] Happ/клиент не ругается на handshake
- [ ] Открываются сайты
- [ ] Нет жалоб на EOF/TLS handshake

---

# 10. ЧЕКЛИСТ ПРОВЕРКИ Estonia inbound

- [ ] Старый inbound не изменён
- [ ] Создан новый inbound с новым названием
- [ ] Указан отдельный SNI, отличный от Germany
- [ ] Указан отдельный набор shortId
- [ ] `decryption=none`
- [ ] `type=tcp`
- [ ] `security=reality`
- [ ] Ссылка импортируется
- [ ] Клиент не падает на handshake
- [ ] Нет повторения старого XHTTP-сценария

---

# 11. КАК Я БЫ ВЫБРАЛ ПРЯМО СЕЙЧАС

Чтобы не усложнять:

## Germany
- оставить текущий старый inbound как legacy-stable
- новый inbound:
  - SNI: `login.microsoftonline.com`
  - новый набор shortId
  - только для новых клиентов

## Estonia
- оставить текущий старый inbound как legacy-stable
- новый inbound:
  - SNI: `www.cloudflare.com`
  - новый набор shortId
  - только для новых клиентов

Это даст:
- меньше зеркальности между нодами
- более чистую сегментацию
- минимальный риск поломки существующей базы

---

# 12. ЧТО ДАЛЬШЕ ПОСЛЕ ЭТОГО

Когда оба новых inbound стабильно проживут:
- 3–5 тестовых выдач
- несколько дней без жалоб
- нормальный импорт в клиентах

Только тогда можно обсуждать:
- fallback через VLESS/Trojan глубже
- migration plan старых клиентов
- второй anti-DPI слой
- более сложную ротацию профилей

---

# 13. ГЛАВНОЕ ПРАВИЛО

> Не оптимизируй то, что уже в проде работает, пока не создал безопасную параллельную замену.

---

# END
