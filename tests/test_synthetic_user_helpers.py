import unittest

from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from backend.core.models import User
from backend.core.synthetic_users import is_synthetic_user, real_user_sql_clause


class SyntheticUserHelperTests(unittest.TestCase):
    def test_is_synthetic_user_uses_explicit_flag_even_without_prefix(self) -> None:
        user = SimpleNamespace(username="ordinary_user", is_synthetic=True)

        self.assertTrue(is_synthetic_user(user))

    def test_real_user_sql_clause_checks_flag_and_legacy_prefixes(self) -> None:
        clause = real_user_sql_clause(User)
        compiled = str(
            clause.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()

        self.assertIn("is_synthetic", compiled)
        self.assertIn("bridge_", compiled)
        self.assertIn("manual_payment_", compiled)


if __name__ == "__main__":
    unittest.main()
