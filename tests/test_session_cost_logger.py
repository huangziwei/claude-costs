"""Tests for claude_costs data functions and statusline CSV upsert."""

import csv
import os
import tempfile
from unittest.mock import patch

from claude_costs import aggregate, load_rows, period_key, _cost_style, _sess, _tok


# ---------------------------------------------------------------------------
# period_key
# ---------------------------------------------------------------------------

class TestPeriodKey:
    def test_monthly(self):
        assert period_key("2026-03-07T16:00:20Z", "monthly") == "2026-03"

    def test_daily(self):
        assert period_key("2026-03-07T16:00:20Z", "daily") == "2026-03-07"

    def test_weekly(self):
        result = period_key("2026-03-07T16:00:20Z", "weekly")
        assert result.startswith("2026-W")

    def test_invalid_timestamp(self):
        assert period_key("not-a-date", "monthly") == "unknown"

    def test_utc_suffix(self):
        assert period_key("2026-01-15T00:00:00Z", "monthly") == "2026-01"

    def test_offset_timezone(self):
        assert period_key("2026-06-15T12:00:00+08:00", "daily") == "2026-06-15"


# ---------------------------------------------------------------------------
# _cost_style
# ---------------------------------------------------------------------------

class TestCostStyle:
    def test_high_cost(self):
        assert _cost_style(50) == "bold red"
        assert _cost_style(100) == "bold red"

    def test_medium_cost(self):
        assert _cost_style(10) == "yellow"
        assert _cost_style(49.99) == "yellow"

    def test_low_cost(self):
        assert _cost_style(0) == "green"
        assert _cost_style(9.99) == "green"


# ---------------------------------------------------------------------------
# _sess (pluralization)
# ---------------------------------------------------------------------------

class TestSess:
    def test_singular(self):
        assert _sess(1) == "1 session"

    def test_plural(self):
        assert _sess(0) == "0 sessions"
        assert _sess(2) == "2 sessions"
        assert _sess(100) == "100 sessions"


# ---------------------------------------------------------------------------
# _tok (token formatting)
# ---------------------------------------------------------------------------

class TestTok:
    def test_small(self):
        assert _tok(0) == "0"
        assert _tok(999) == "999"

    def test_thousands(self):
        assert _tok(1_000) == "1.0k"
        assert _tok(28_059) == "28.1k"

    def test_millions(self):
        assert _tok(1_000_000) == "1.0M"
        assert _tok(2_500_000) == "2.5M"


# ---------------------------------------------------------------------------
# load_rows
# ---------------------------------------------------------------------------

class TestLoadRows:
    def test_loads_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,session_id,project,model,cost_usd,input_tokens,output_tokens\n")
            f.write("2026-03-01T17:00:33Z,abc123,myproj,claude-opus-4-6,4.15,1000,2000\n")
            f.write("2026-03-01T18:00:00Z,def456,other,claude-opus-4-6,1.00,500,600\n")
            path = f.name
        try:
            with patch("claude_costs.CSV_PATH", __import__("pathlib").Path(path)):
                rows = load_rows()
                assert len(rows) == 2
                assert rows[0]["project"] == "myproj"
                assert rows[0]["cost_usd"] == "4.15"
        finally:
            os.unlink(path)

    def test_project_filter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,session_id,project,model,cost_usd,input_tokens,output_tokens\n")
            f.write("2026-03-01T17:00:33Z,abc,projA,opus,1.00,,\n")
            f.write("2026-03-01T18:00:00Z,def,projB,opus,2.00,,\n")
            f.write("2026-03-01T19:00:00Z,ghi,projA,opus,3.00,,\n")
            path = f.name
        try:
            with patch("claude_costs.CSV_PATH", __import__("pathlib").Path(path)):
                rows = load_rows(project_filter="projA")
                assert len(rows) == 2
                assert all(r["project"] == "projA" for r in rows)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        with patch("claude_costs.CSV_PATH", __import__("pathlib").Path("/nonexistent/path.csv")):
            assert load_rows() == []

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            path = f.name
        try:
            with patch("claude_costs.CSV_PATH", __import__("pathlib").Path(path)):
                assert load_rows() == []
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

class TestAggregate:
    def _make_rows(self):
        return [
            {"timestamp": "2026-03-01T10:00:00Z", "project": "alpha", "cost_usd": "5.00", "input_tokens": "1000", "output_tokens": "2000"},
            {"timestamp": "2026-03-01T12:00:00Z", "project": "alpha", "cost_usd": "3.00", "input_tokens": "500", "output_tokens": "800"},
            {"timestamp": "2026-03-01T14:00:00Z", "project": "beta", "cost_usd": "2.00", "input_tokens": "200", "output_tokens": "300"},
            {"timestamp": "2026-04-01T10:00:00Z", "project": "alpha", "cost_usd": "1.00", "input_tokens": "100", "output_tokens": "100"},
        ]

    def test_monthly_grouping(self):
        data = aggregate(self._make_rows(), "monthly")
        assert "2026-03" in data
        assert "2026-04" in data
        assert "alpha" in data["2026-03"]
        assert "beta" in data["2026-03"]

    def test_daily_grouping(self):
        data = aggregate(self._make_rows(), "daily")
        assert "2026-03-01" in data
        assert "2026-04-01" in data

    def test_cost_aggregation(self):
        data = aggregate(self._make_rows(), "monthly")
        alpha_mar = data["2026-03"]["alpha"]
        assert alpha_mar["cost"] == 8.0
        assert alpha_mar["sessions"] == 2
        assert alpha_mar["in_tok"] == 1500
        assert alpha_mar["out_tok"] == 2800

    def test_rows_preserved(self):
        rows = self._make_rows()
        data = aggregate(rows, "monthly")
        alpha_mar = data["2026-03"]["alpha"]
        assert len(alpha_mar["rows"]) == 2
        assert alpha_mar["rows"][0]["cost_usd"] == "5.00"
        assert alpha_mar["rows"][1]["cost_usd"] == "3.00"

    def test_empty_tokens_handled(self):
        rows = [
            {"timestamp": "2026-03-01T10:00:00Z", "project": "x", "cost_usd": "1.00", "input_tokens": "", "output_tokens": ""},
        ]
        data = aggregate(rows, "monthly")
        assert data["2026-03"]["x"]["in_tok"] == 0
        assert data["2026-03"]["x"]["out_tok"] == 0

    def test_empty_input(self):
        assert aggregate([], "monthly") == {}


# ---------------------------------------------------------------------------
# statusline _upsert_csv
# ---------------------------------------------------------------------------

class TestUpsertCsv:
    def test_insert_new_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "session-costs.csv")
            # Import and patch CSV_PATH in statusline module
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "statusline", os.path.join(os.path.dirname(__file__), "..", "config", "statusline-command.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            from pathlib import Path
            original = mod.CSV_PATH
            mod.CSV_PATH = Path(csv_path)
            try:
                mod._upsert_csv("sess1", "myproj", "opus", 4.15, "2026-03-01T10:00:00Z", 1000, 2000)
                with open(csv_path) as f:
                    rows = list(csv.DictReader(f))
                assert len(rows) == 1
                assert rows[0]["session_id"] == "sess1"
                assert rows[0]["project"] == "myproj"
                assert rows[0]["cost_usd"] == "4.1500"
                assert rows[0]["input_tokens"] == "1000"
                assert rows[0]["output_tokens"] == "2000"
            finally:
                mod.CSV_PATH = original

    def test_update_existing_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "session-costs.csv")
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "statusline", os.path.join(os.path.dirname(__file__), "..", "config", "statusline-command.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            from pathlib import Path
            original = mod.CSV_PATH
            mod.CSV_PATH = Path(csv_path)
            try:
                mod._upsert_csv("sess1", "proj", "opus", 1.00, "2026-03-01T10:00:00Z", 100, 200)
                mod._upsert_csv("sess1", "proj", "opus", 5.00, "2026-03-01T11:00:00Z", 500, 800)
                with open(csv_path) as f:
                    rows = list(csv.DictReader(f))
                assert len(rows) == 1
                assert rows[0]["cost_usd"] == "5.0000"
                assert rows[0]["input_tokens"] == "500"
                assert rows[0]["output_tokens"] == "800"
            finally:
                mod.CSV_PATH = original

    def test_multiple_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "session-costs.csv")
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "statusline", os.path.join(os.path.dirname(__file__), "..", "config", "statusline-command.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            from pathlib import Path
            original = mod.CSV_PATH
            mod.CSV_PATH = Path(csv_path)
            try:
                mod._upsert_csv("sess1", "projA", "opus", 1.00, "2026-03-01T10:00:00Z", 100, 200)
                mod._upsert_csv("sess2", "projB", "opus", 2.00, "2026-03-01T11:00:00Z", 300, 400)
                with open(csv_path) as f:
                    rows = list(csv.DictReader(f))
                assert len(rows) == 2
                assert rows[0]["session_id"] == "sess1"
                assert rows[1]["session_id"] == "sess2"
            finally:
                mod.CSV_PATH = original
