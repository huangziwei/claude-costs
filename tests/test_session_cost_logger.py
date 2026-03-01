"""Tests for session-cost-logger.py.

Verifies that the logger computes correct API costs by asserting hardcoded
dollar amounts derived from Anthropic's published pricing, NOT by mirroring
the script's own constants.  If a pricing constant in the script is wrong,
these tests will catch it.

Pricing source: https://docs.anthropic.com/en/docs/about-claude/pricing
  Opus 4.6:   $5 / $25 / $0.50 / $6.25 / $10.00 per MTok (input/output/cache_read/5m_write/1h_write)
  Sonnet 4.6: $3 / $15 / $0.30 / $3.75 / $6.00  per MTok
  Haiku 4.5:  $1 / $5  / $0.10 / $1.25 / $2.00  per MTok
"""

import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path

LOGGER_SCRIPT = Path(__file__).resolve().parent.parent / "config" / "hooks" / "session-cost-logger.py"


_msg_counter = 0


def _make_assistant_entry(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_5m: int = 0,
    cache_1h: int = 0,
    msg_id: str | None = None,
) -> dict:
    global _msg_counter
    if msg_id is None:
        _msg_counter += 1
        msg_id = f"msg_{_msg_counter:04d}"
    return {
        "type": "assistant",
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_5m + cache_1h,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": cache_5m,
                    "ephemeral_1h_input_tokens": cache_1h,
                },
            },
        },
    }


def _run_logger(transcript_lines: list[dict], cwd: str = "/tmp/test") -> list[dict]:
    """Write a transcript, run the logger, return parsed CSV rows."""
    with tempfile.TemporaryDirectory() as tmp:
        transcript_path = os.path.join(tmp, "transcript.jsonl")

        with open(transcript_path, "w") as f:
            for entry in transcript_lines:
                f.write(json.dumps(entry) + "\n")

        hook_input = json.dumps({
            "session_id": "test-session",
            "transcript_path": transcript_path,
            "cwd": cwd,
            "reason": "test",
        })

        env = os.environ.copy()
        env["HOME"] = tmp  # Override HOME so CSV_PATH writes to tmp/.claude/
        os.makedirs(os.path.join(tmp, ".claude"))

        result = subprocess.run(
            ["python3", str(LOGGER_SCRIPT)],
            input=hook_input,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"Logger failed: {result.stderr}"

        csv_file = os.path.join(tmp, ".claude", "session-costs.csv")
        assert os.path.exists(csv_file), "CSV file was not created"

        with open(csv_file) as f:
            return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Per-model pricing (hardcoded expected dollar amounts)
# ---------------------------------------------------------------------------

class TestOpusPricing:
    """Opus 4.6: $5/$25/$0.50/$6.25/$10.00 per MTok."""

    def test_input_tokens(self):
        rows = _run_logger([_make_assistant_entry("claude-opus-4-6", input_tokens=1_000_000, output_tokens=0)])
        assert float(rows[0]["cost_usd"]) == 5.0

    def test_output_tokens(self):
        rows = _run_logger([_make_assistant_entry("claude-opus-4-6", input_tokens=0, output_tokens=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 25.0

    def test_cache_read(self):
        rows = _run_logger([_make_assistant_entry("claude-opus-4-6", input_tokens=0, output_tokens=0, cache_read=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 0.5

    def test_cache_write_5m(self):
        rows = _run_logger([_make_assistant_entry("claude-opus-4-6", input_tokens=0, output_tokens=0, cache_5m=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 6.25

    def test_cache_write_1h(self):
        rows = _run_logger([_make_assistant_entry("claude-opus-4-6", input_tokens=0, output_tokens=0, cache_1h=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 10.0

    def test_all_token_types_combined(self):
        """10K input + 5K output + 200K cache_read + 50K cache_5m + 30K cache_1h."""
        rows = _run_logger([_make_assistant_entry(
            "claude-opus-4-6",
            input_tokens=10_000, output_tokens=5_000,
            cache_read=200_000, cache_5m=50_000, cache_1h=30_000,
        )])
        # (10K*5 + 5K*25 + 200K*0.50 + 50K*6.25 + 30K*10) / 1M
        # = (50000 + 125000 + 100000 + 312500 + 300000) / 1M = 0.8875
        assert float(rows[0]["cost_usd"]) == 0.8875


class TestSonnetPricing:
    """Sonnet 4.6: $3/$15/$0.30/$3.75/$6.00 per MTok."""

    def test_input_tokens(self):
        rows = _run_logger([_make_assistant_entry("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)])
        assert float(rows[0]["cost_usd"]) == 3.0

    def test_output_tokens(self):
        rows = _run_logger([_make_assistant_entry("claude-sonnet-4-6", input_tokens=0, output_tokens=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 15.0

    def test_cache_read(self):
        rows = _run_logger([_make_assistant_entry("claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_read=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 0.3

    def test_cache_write_5m(self):
        rows = _run_logger([_make_assistant_entry("claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_5m=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 3.75

    def test_cache_write_1h(self):
        rows = _run_logger([_make_assistant_entry("claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_1h=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 6.0

    def test_all_token_types_combined(self):
        """100K input + 50K output + 500K cache_read + 100K cache_5m + 50K cache_1h."""
        rows = _run_logger([_make_assistant_entry(
            "claude-sonnet-4-6",
            input_tokens=100_000, output_tokens=50_000,
            cache_read=500_000, cache_5m=100_000, cache_1h=50_000,
        )])
        # (100K*3 + 50K*15 + 500K*0.30 + 100K*3.75 + 50K*6) / 1M
        # = (300000 + 750000 + 150000 + 375000 + 300000) / 1M = 1.875
        assert float(rows[0]["cost_usd"]) == 1.875


class TestHaikuPricing:
    """Haiku 4.5: $1/$5/$0.10/$1.25/$2.00 per MTok."""

    def test_input_tokens(self):
        rows = _run_logger([_make_assistant_entry("claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=0)])
        assert float(rows[0]["cost_usd"]) == 1.0

    def test_output_tokens(self):
        rows = _run_logger([_make_assistant_entry("claude-haiku-4-5-20251001", input_tokens=0, output_tokens=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 5.0

    def test_cache_read(self):
        rows = _run_logger([_make_assistant_entry("claude-haiku-4-5-20251001", input_tokens=0, output_tokens=0, cache_read=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 0.1

    def test_cache_write_5m(self):
        rows = _run_logger([_make_assistant_entry("claude-haiku-4-5-20251001", input_tokens=0, output_tokens=0, cache_5m=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 1.25

    def test_cache_write_1h(self):
        rows = _run_logger([_make_assistant_entry("claude-haiku-4-5-20251001", input_tokens=0, output_tokens=0, cache_1h=1_000_000)])
        assert float(rows[0]["cost_usd"]) == 2.0


class TestFallbackPricing:
    """Unknown models should fall back to Sonnet pricing."""

    def test_unknown_model_uses_sonnet_rates(self):
        rows = _run_logger([_make_assistant_entry("some-future-model", input_tokens=1_000_000, output_tokens=0)])
        # Sonnet input rate: $3/MTok
        assert float(rows[0]["cost_usd"]) == 3.0


# ---------------------------------------------------------------------------
# No double-counting (the aggregate field must NOT add to the cost)
# ---------------------------------------------------------------------------

class TestNoDoubleCounting:
    """Ensure cache_creation_input_tokens (aggregate) is not added on top of
    the per-TTL breakdown.  See: github.com/anthropics/claude-code/issues/5904"""

    def test_only_breakdown_is_billed(self):
        """The aggregate field is 200K but the breakdown is 100K 5m + 100K 1h.
        Cost should reflect only the breakdown, not the aggregate."""
        entry = {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 200_000,  # aggregate — must be ignored
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 100_000,
                        "ephemeral_1h_input_tokens": 100_000,
                    },
                },
            },
        }
        rows = _run_logger([entry])
        # 100K*$6.25 + 100K*$10.00 = $625000 + $1000000 = $1625000 / 1M = $1.625
        assert float(rows[0]["cost_usd"]) == 1.625

    def test_flat_cache_creation_falls_back_to_5m(self):
        """If only aggregate cache_creation_input_tokens is present, bill as 5m."""
        entry = {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 1_000_000,
                },
            },
        }
        rows = _run_logger([entry])
        assert int(rows[0]["cache_create_5m_tokens"]) == 1_000_000
        assert int(rows[0]["cache_create_1h_tokens"]) == 0
        assert float(rows[0]["cost_usd"]) == 6.25


# ---------------------------------------------------------------------------
# Deduplication (transcript logs multiple entries per API call)
# ---------------------------------------------------------------------------

def test_duplicate_entries_are_deduplicated():
    """Multiple transcript entries with the same message ID should be counted once.
    The last entry (with final output_tokens) wins."""
    entries = [
        # Streaming updates for a single API call — same msg_id, growing output
        _make_assistant_entry("claude-opus-4-6", input_tokens=3, output_tokens=9,
                              cache_read=20000, cache_1h=5000, msg_id="msg_AAA"),
        _make_assistant_entry("claude-opus-4-6", input_tokens=3, output_tokens=9,
                              cache_read=20000, cache_1h=5000, msg_id="msg_AAA"),
        _make_assistant_entry("claude-opus-4-6", input_tokens=3, output_tokens=500,
                              cache_read=20000, cache_1h=5000, msg_id="msg_AAA"),
    ]
    rows = _run_logger(entries)
    assert len(rows) == 1
    row = rows[0]

    # Should count the LAST entry only, not sum all three
    assert int(row["input_tokens"]) == 3
    assert int(row["output_tokens"]) == 500
    assert int(row["cache_read_tokens"]) == 20000
    assert int(row["cache_create_1h_tokens"]) == 5000
    assert int(row["turns"]) == 1

    # (3*5 + 500*25 + 20000*0.50 + 5000*10) / 1M = (15 + 12500 + 10000 + 50000) / 1M
    assert float(row["cost_usd"]) == 0.0725


def test_different_message_ids_not_deduplicated():
    """Entries with different message IDs are separate API calls."""
    entries = [
        _make_assistant_entry("claude-opus-4-6", input_tokens=100, output_tokens=200, msg_id="msg_A"),
        _make_assistant_entry("claude-opus-4-6", input_tokens=100, output_tokens=200, msg_id="msg_B"),
    ]
    rows = _run_logger(entries)
    assert len(rows) == 1
    assert int(rows[0]["input_tokens"]) == 200
    assert int(rows[0]["output_tokens"]) == 400
    assert int(rows[0]["turns"]) == 2


# ---------------------------------------------------------------------------
# Accumulation, filtering, and CSV structure
# ---------------------------------------------------------------------------

def test_multiple_turns_accumulate():
    """Token counts should sum across turns for the same model."""
    entries = [
        _make_assistant_entry("claude-opus-4-6", input_tokens=100, output_tokens=200),
        _make_assistant_entry("claude-opus-4-6", input_tokens=300, output_tokens=400),
    ]
    rows = _run_logger(entries)
    assert len(rows) == 1
    assert int(rows[0]["input_tokens"]) == 400
    assert int(rows[0]["output_tokens"]) == 600
    assert int(rows[0]["turns"]) == 2


def test_multiple_models_separate_rows_with_correct_costs():
    """Different models produce separate rows, each priced correctly."""
    entries = [
        _make_assistant_entry("claude-opus-4-6", input_tokens=1000, output_tokens=500),
        _make_assistant_entry("claude-haiku-4-5-20251001", input_tokens=500, output_tokens=1000),
    ]
    rows = _run_logger(entries)
    assert len(rows) == 2

    by_model = {r["model"]: r for r in rows}

    # Opus: (1000*5 + 500*25) / 1M = 17500 / 1M = $0.0175
    assert float(by_model["claude-opus-4-6"]["cost_usd"]) == 0.0175

    # Haiku: (500*1 + 1000*5) / 1M = 5500 / 1M = $0.0055
    assert float(by_model["claude-haiku-4-5-20251001"]["cost_usd"]) == 0.0055


def test_non_assistant_entries_ignored():
    """Non-assistant entries in transcript should be skipped."""
    entries = [
        {"type": "queue-operation", "operation": "enqueue"},
        {"type": "human", "message": {"content": "hello"}},
        _make_assistant_entry("claude-opus-4-6", input_tokens=100, output_tokens=200),
        {"type": "tool_result", "content": "ok"},
    ]
    rows = _run_logger(entries)
    assert len(rows) == 1
    assert int(rows[0]["turns"]) == 1
    assert int(rows[0]["input_tokens"]) == 100


def test_empty_transcript():
    """Empty transcript should produce no CSV."""
    with tempfile.TemporaryDirectory() as tmp:
        transcript_path = os.path.join(tmp, "transcript.jsonl")
        Path(transcript_path).write_text("")

        env = os.environ.copy()
        env["HOME"] = tmp
        os.makedirs(os.path.join(tmp, ".claude"))

        result = subprocess.run(
            ["python3", str(LOGGER_SCRIPT)],
            input=json.dumps({
                "session_id": "test",
                "transcript_path": transcript_path,
                "cwd": "/tmp",
                "reason": "test",
            }),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert not os.path.exists(os.path.join(tmp, ".claude", "session-costs.csv"))


def test_project_derived_from_cwd():
    """Project name should be the last component of cwd."""
    entries = [
        _make_assistant_entry("claude-opus-4-6", input_tokens=100, output_tokens=100),
    ]
    rows = _run_logger(entries, cwd="/Users/someone/projects/my-cool-app")
    assert rows[0]["project"] == "my-cool-app"


# ---------------------------------------------------------------------------
# Realistic multi-turn session
# ---------------------------------------------------------------------------

def test_realistic_session():
    """Simulate a realistic Opus session and verify against a hand-calculated cost."""
    entries = [
        _make_assistant_entry("claude-opus-4-6", input_tokens=3, output_tokens=14, cache_read=18914, cache_1h=1654),
        _make_assistant_entry("claude-opus-4-6", input_tokens=3, output_tokens=271, cache_read=18914, cache_1h=1654),
        _make_assistant_entry("claude-opus-4-6", input_tokens=3, output_tokens=5000, cache_read=25000, cache_1h=2000),
    ]
    rows = _run_logger(entries)
    row = rows[0]

    assert int(row["input_tokens"]) == 9
    assert int(row["output_tokens"]) == 5285
    assert int(row["cache_read_tokens"]) == 62828
    assert int(row["cache_create_1h_tokens"]) == 5308
    assert int(row["turns"]) == 3

    # Hand calculation:
    #   9 * $5  +  5285 * $25  +  62828 * $0.50  +  5308 * $10  = per-MTok
    #   45      +  132125      +  31414           +  53080       = 216664
    #   216664 / 1_000_000 = $0.216664 → rounded to $0.2167
    assert float(row["cost_usd"]) == 0.2167


# ---------------------------------------------------------------------------
# CSV sanitization
# ---------------------------------------------------------------------------

def test_formula_like_project_name_is_sanitized():
    """Directory names starting with = + - @ should be prefixed with '."""
    entries = [
        _make_assistant_entry("claude-opus-4-6", input_tokens=100, output_tokens=100),
    ]
    rows = _run_logger(entries, cwd="/tmp/=malicious")
    assert rows[0]["project"] == "'=malicious"
