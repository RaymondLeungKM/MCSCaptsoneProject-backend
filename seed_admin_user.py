"""Seed or update an admin user."""

import argparse
import asyncio
import uuid

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models import analytics  # noqa: F401
from app.models import community  # noqa: F401
from app.models import content  # noqa: F401
from app.models import daily_words  # noqa: F401
from app.models import generated_sentences  # noqa: F401
from app.models import parent_analytics  # noqa: F401
from app.models import phase8  # noqa: F401
from app.models import vocabulary  # noqa: F401
from app.models.user import User, UserRole

async def seed_admin_user(*, email: str, password: str, full_name: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        created = user is None

        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                full_name=full_name,
                hashed_password=get_password_hash(password),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
        else:
            user.full_name = full_name
            user.hashed_password = get_password_hash(password)
            user.role = UserRole.ADMIN
            user.is_active = True

        await db.commit()
        await db.refresh(user)

        action = "Created" if created else "Updated"
        print(f"{action} admin user: {user.email} ({user.role.value})")
        print(f"User ID: {user.id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed or update an admin user")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")
    parser.add_argument(
        "--full-name",
        default="Platform Admin",
        help="Display name for the admin account",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        seed_admin_user(
            email=args.email,
            password=args.password,
            full_name=args.full_name,
        )
    )
