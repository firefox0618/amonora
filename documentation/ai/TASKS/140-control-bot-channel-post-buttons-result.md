# TASK 140 RESULT — control bot channel post buttons

## Summary
`@amonora_control_bot` can now edit the inline keyboard of an existing Telegram channel post after an owner/admin forwards that post into the bot.

## What changed
- added forwarded channel-post target extraction and URL-button parsing helpers
- added a control-bot FSM flow that:
  - accepts a forwarded channel post
  - asks for buttons in `Текст | URL` format
  - supports `||` for multiple buttons in one row
  - supports `очистить` to remove the current keyboard
- added focused unit tests for channel-origin extraction and button parsing
- updated internal feature/state docs

## Validation
- `./venv/bin/python -m unittest tests.test_control_channel_posts tests.test_control_router tests.test_control_queries`

## Notes
- this flow currently supports URL buttons only
- the control bot still needs channel admin rights with `can_edit_messages` to update posts
