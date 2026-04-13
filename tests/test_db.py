import asyncio

from bot.db import activate_trial, get_or_create_user, has_active_trial


async def test() -> None:
    user, _ = await get_or_create_user(
        telegram_id=888000111,
        username="trial_test_user",
    )

    before = await has_active_trial(user.id)
    print("Active trial before activation:", before)

    updated_user = await activate_trial(user.id)

    if updated_user is None:
        print("User not found")
        return

    after = await has_active_trial(user.id)
    print("Active trial after activation:", after)
    print("Trial started at:", updated_user.trial_started_at)
    print("Trial expires at:", updated_user.trial_expires_at)


if __name__ == "__main__":
    asyncio.run(test())