Date: 2026-03-22
Server: Core / backend (`46.21.81.186`)
Component: Bot / referral balance / referral UI
Change:
- fixed double referral credit path where a first paid referral could produce `100 RUB` instead of `50 RUB`
- removed the `Друзей с начисленным бонусом` line from the referral screen
- synced canonical referral-screen docs with the current UI
Reason:
- referral reward must stay `50 RUB` per first paid referral as documented
- the extra referral-screen line was no longer useful in the user-facing summary
Risk: medium
Checks:
- `./venv/bin/python -m unittest -q tests.test_referral_balance`
- `./venv/bin/python -m unittest -q tests.test_payment_finalization tests.test_confirm_external_payment_record`
- `./venv/bin/python -m unittest -q tests.test_referral_ui tests.test_bot_copy_updates`
- `git diff --check -- bot/db.py bot/utils/texts.py tests/test_referral_balance.py tests/test_referral_ui.py tests/test_bot_copy_updates.py documentation/FEATURES.md documentation/supporting/user-guide.md`
- server pre-change backup:
  - `/opt/amonora_bot_backup/referral-fix-20260322-211205`
- server validation:
  - `/opt/amonora_bot/venv/bin/python -m py_compile /opt/amonora_bot/bot/db.py /opt/amonora_bot/bot/utils/texts.py`
  - `systemctl restart amonora-bot.service`
  - `systemctl is-active amonora-bot.service` -> `active`
  - `journalctl -u amonora-bot.service -n 12 --no-pager` -> clean restart, no traceback in the captured tail
Rollback:
- restore previous versions of `bot/db.py`, `bot/utils/texts.py`, referral tests, and referral docs
- sync restored files back to `/opt/amonora_bot`
- restart `amonora-bot.service`
Status: OK
