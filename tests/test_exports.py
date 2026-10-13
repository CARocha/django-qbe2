import csv
import io
import json
from decimal import Decimal
from unittest.mock import patch

from django.db import DatabaseError, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from tests import test_engine
from tests.test_validation import order_payload


class ExportTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    @override_settings(QBE2_MAX_ROWS=1)
    def test_all_bounded_rows_not_current_page(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("django_qbe2:export"),
            {
                "definition": json.dumps(order_payload(columns=["number", "total"])),
                "page": "2",
                "page_size": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(response["X-QBE-Truncated"], "true")
        rows = list(
            csv.reader(io.StringIO(b"".join(response.streaming_content).decode()))
        )
        self.assertEqual(rows[1:], [["A100", "100.01"]])

    def test_text_formula_and_numeric_sign(self):
        from django_qbe2.exports import csv_cell

        for text in ("=1+1", " +1", "\t@SUM(1)", "-value"):
            with self.subTest(text=text):
                self.assertEqual(csv_cell(text), "'" + text)
        self.assertEqual(csv_cell(Decimal("-1.20")), "-1.20")
        self.assertEqual(csv_cell('Café, "quoted"\ntext'), 'Café, "quoted"\ntext')
        self.assertEqual(csv_cell(None), "")

    def test_export_never_includes_other_owners(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("django_qbe2:export"),
            {
                "definition": json.dumps(
                    order_payload(columns=["number", "customer__name"])
                ),
            },
        )
        body = b"".join(response.streaming_content)
        self.assertIn(b"A100", body)
        self.assertNotIn(b"Bob", body)
        self.assertNotIn("X-QBE-Truncated", response)
        self.assertEqual(
            self.client.get(reverse("django_qbe2:export")).status_code, 405
        )


class StreamResourceTests(TransactionTestCase):
    setUp = test_engine.EngineTests.setUp
    query = test_engine.EngineTests.query

    def active_cursors(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM pg_cursors")
            return {row[0] for row in cursor.fetchall()}

    def assert_resources_restored(self):
        self.assertFalse(connection.in_atomic_block)
        if connection.vendor == "postgresql":
            self.assertEqual(self.active_cursors(), set())
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                self.assertEqual(cursor.fetchone()[0], "0")
                cursor.execute("SELECT 1")
                self.assertEqual(cursor.fetchone()[0], 1)

    def test_early_close_restores_timeout(self):
        from django_qbe2.exports import csv_response
        from django_qbe2.validation import validate_definition

        definition = validate_definition(order_payload(), self.catalog)
        response = csv_response(self.query(), definition, self.catalog)
        stream = iter(response.streaming_content)
        next(stream)
        self.assertIn(b"A100", next(stream))
        if connection.vendor == "postgresql":
            self.assertTrue(self.active_cursors())
        response.close()
        self.assert_resources_restored()

    def test_failure_after_a_row_propagates_and_closes_resources(self):
        from django_qbe2.exports import csv_cell, csv_response
        from django_qbe2.validation import validate_definition

        definition = validate_definition(order_payload(), self.catalog)
        response = csv_response(self.query(), definition, self.catalog)
        received = []

        def fail_on_second_row(value):
            if value == "A200":
                if connection.vendor == "postgresql":
                    self.assertTrue(self.active_cursors())
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_sleep(0.2)")
                raise RuntimeError("Interrupted export")
            return csv_cell(value)

        error_class = (
            DatabaseError if connection.vendor == "postgresql" else RuntimeError
        )
        with (
            patch("django_qbe2.execution.STATEMENT_TIMEOUT_MS", 50),
            patch("django_qbe2.exports.csv_cell", side_effect=fail_on_second_row),
            self.assertLogs("django_qbe2.exports", level="ERROR") as logs,
        ):
            stream = iter(response.streaming_content)
            received.extend((next(stream), next(stream)))
            with self.assertRaises(error_class):
                next(stream)
        response.close()
        self.assertIn(b"A100", received[1])
        self.assertNotIn(b"<html", b"".join(received).lower())
        self.assertNotIn(b"A200", b"".join(received))
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn("pg_sleep", logs.output[0])
        self.assertNotIn("Interrupted export", logs.output[0])
        self.assert_resources_restored()
