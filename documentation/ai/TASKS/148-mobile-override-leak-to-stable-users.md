# TASK 148 — Mobile override leak to stable users

Дата: 31 марта 2026

## Контекст

После rollout `MOBILE_MODE_OVERRIDE_LINK_DE` / `MOBILE_MODE_OVERRIDE_LINK_DK` fixed shared override link начал попадать не только в admin-only experimental `Мобильный` режим, но и в обычную mobile delivery ветку `stable` устройств с `delivery_mode = mobile_happ`.

Это приводило к тому, что обычный Germany/Denmark пользователь мог получить shared override-link вместо собственного live per-device ключа.

## Что нужно

- оставить env-based mobile override только для реального experimental `mode = mobile`;
- вернуть обычной mobile delivery ветке `stable / reserve` live per-device VLESS/Trojan payload;
- добавить regression test на gating логики;
- после rollout почистить уже выданные Germany/DK stable mobile metadata от fixed override-link.

## Критерии приёмки

- `stable` mobile device больше не получает `link_delivery_source = mobile_mode_override`;
- `mobile` experimental device всё ещё может получать env override-link;
- existing stable mobile users после repair/sync снова видят собственный live ключ.
