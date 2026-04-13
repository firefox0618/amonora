# TASK 118 — terms acceptance and start offer notice

## Status
Completed

## Goal
Add a narrow legal-use clause to the public terms and make the main bot `/start` flow explicitly notify new users that continuing to use the service constitutes acceptance of the terms, with a direct link to the public offer.

## Why
The public legal surface needs a clearer rule against using the service for access to legally restricted resources, and the main user entry flow should reference the offer at the moment of onboarding instead of requiring the user to find it later in the info section.

## Context
Relevant docs and code areas:
- `documentation/terms-of-service.md`
- `bot/handlers/start.py`
- `bot/utils/texts.py`
- `bot/keyboards/info.py`
- `tests/test_bot_copy_updates.py`

## Current behavior
The terms contained only broad legality wording without a narrower clause about legally restricted resources. The bot `/start` flow created users and showed the welcome text and menu, but did not explicitly mention acceptance of the offer or provide a direct legal-link button in the entry message.

## Desired behavior
The public terms should contain one non-duplicative clause covering access to legally restricted resources. New users entering through `/start` should see an explicit acceptance notice and a direct button to the public offer, while the rest of the onboarding flow remains unchanged.

## Scope
Included:
- update the terms wording in the legal document source
- update the new-user `/start` copy
- add a direct offer button to the first-start message
- keep the existing info/documents section link consistent
- add focused regression tests

## Out of scope
- introducing a DB field or migration for persisted terms acceptance
- changing payment, trial, access, or device logic
- changing the landing runtime route structure

## Constraints
Important limitations:
- preserve the existing `/start` onboarding path
- avoid duplicating the same legal rule in multiple clauses
- do not introduce tracked secrets or server credentials
- keep the change small and reversible

## Risks
Potential regressions or sensitive areas:
- changing the first-start reply markup could accidentally hide the main menu if not re-sent explicitly
- legal wording must avoid risky marketing language about bypassing blocks while still imposing a clear usage restriction

## Acceptance criteria
Concrete conditions for completion:
- `documentation/terms-of-service.md` includes a narrow clause about legally restricted resources
- new users see an explicit acceptance notice on `/start`
- the first-start flow includes a button linking to `https://amonoraconnect.com/legal/terms`
- the existing info/documents keyboard still links to the same terms URL
- focused tests cover the updated text and link

## Validation
Tests and manual checks required:
- `python3 -m pytest tests/test_bot_copy_updates.py`
- `python3 -m compileall bot documentation`
- manual `/start` check in Telegram after deploy

## Deliverables
- code changes
- docs updates
- short implementation summary
