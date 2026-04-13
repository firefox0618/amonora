import asyncio
import time
from datetime import timedelta

from bot.db import create_vpn_client, get_or_create_user
from bot.utils.access import utcnow
from bot.vpn_api import XUIClient


async def main() -> None:
    client = XUIClient()

    try:
        success = await client.login()
        print("XUI login:", success)

        if not success:
            return

        user, _ = await get_or_create_user(
            telegram_id=777000111,
            username="provision_test_user",
        )

        email = f"provision_{int(time.time())}"

        result = await client.provision_vless_client(
            user_id=user.id,
            email=email,
            access_expires_at=utcnow() + timedelta(days=3),
            save_callback=create_vpn_client,
        )

        print("Provision result:")
        print(result)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
