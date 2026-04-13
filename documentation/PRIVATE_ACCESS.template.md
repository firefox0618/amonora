# PRIVATE ACCESS TEMPLATE

## Зачем нужен этот документ

Этот файл нужен как шаблон для приватного документа с доступами.

Реальные секреты, логины, ключи, пароли, токены и инструкции входа нужно хранить в:

- `documentation/PRIVATE_ACCESS.md`

Этот файл добавлен в `.gitignore` и не должен коммититься в репозиторий.

## Что хранить в PRIVATE_ACCESS.md

- SSH-доступы к серверам
- логины и роли
- IP и хосты
- путь к SSH-ключам
- порядок входа на backend и VPN-ноды
- доступы к панелям
- доступы к инфраструктурным сервисам
- особые замечания по безопасности

## Рекомендуемая структура

### Backend server

- роль:
- IP:
- SSH user:
- SSH port:
- auth type: `ssh key` / `password`
- key path:
- example command:
- notes:

### VPN node: Germany

- роль:
- IP:
- домен:
- SSH user:
- SSH port:
- auth type:
- key path:
- example command:
- notes:

### VPN node: Estonia

- роль:
- IP:
- домен:
- SSH user:
- SSH port:
- auth type:
- key path:
- example command:
- notes:

### Admin web access

- dashboard url:
- dashboard/ui url:
- admin usernames:
- 2FA / Telegram code flow:
- notes:

### Payment access

- SBP related notes:
- external providers:
- who owns access:
- notes:

### Internal bots

- test bot username:
- test bot token location:
- support bot username:
- support bot token location:
- control bot username:
- control bot token location:
- rotation note:
  - если токен когда-либо попал в переписку, тикет, лог или commit, он должен быть ротирован до production rollout
- who can update BotFather settings:
- notes:

### Security notes

- где лежат ключи
- кто имеет доступ
- как выдаётся новый доступ
- как отзывать доступ
- что нельзя хранить в git
