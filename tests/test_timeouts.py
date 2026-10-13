from unittest.mock import patch

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase


class TimeoutTests(TransactionTestCase):
    def test_timeout_restored_on_exception(self):
        from django_qbe2.execution import query_timeout

        if connection.vendor != "postgresql":
            with self.assertNumQueries(0), query_timeout():
                pass
            return
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            original = cursor.fetchone()[0]
        with transaction.atomic():
            with query_timeout(), connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                self.assertEqual(cursor.fetchone()[0], "5s")
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                self.assertEqual(cursor.fetchone()[0], original)
            with self.assertRaises(RuntimeError), query_timeout():
                raise RuntimeError("Interrupted export")
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                self.assertEqual(cursor.fetchone()[0], original)

    def test_postgres_cancels_long_statements(self):
        from django_qbe2.execution import query_timeout

        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only statement cancellation; required in PG job.")
        with patch("django_qbe2.execution.STATEMENT_TIMEOUT_MS", 50):
            with self.assertRaises(DatabaseError), query_timeout():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_sleep(0.2)")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
