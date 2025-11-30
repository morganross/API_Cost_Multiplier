#!/usr/bin/env python3
"""
Unit tests for eval_timeline_aggregator.py

Tests cover:
- Expected runs generation with phase gating
- Phase detection from run_id
- Target extraction from run_id
- Tiered matching logic (exact -> ordinal -> partial)
- Path validation guards
- Deduplication
- Subtotal calculations
"""

import os
import sys
import unittest
import tempfile
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.eval_timeline_aggregator import (
    EvalTimelineAggregator,
    EvalPhase,
    SourceType,
    MatchStatus,
    ExpectedRun,
    ActualRunLog,
    DbRunResult,
    TimelineRow,
    PhaseSubtotal,
    TimelineChart,
    parse_iso_ts,
    format_duration,
    format_cost,
    truncate_target,
    validate_fpf_logs_path,
)


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions."""
    
    def test_parse_iso_ts_with_z(self):
        """Test parsing ISO timestamp with Z suffix."""
        result = parse_iso_ts("2025-11-28T12:00:00Z")
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 11)
        self.assertEqual(result.day, 28)
        self.assertEqual(result.hour, 12)
    
    def test_parse_iso_ts_with_microseconds(self):
        """Test parsing ISO timestamp with microseconds."""
        result = parse_iso_ts("2025-11-28T12:00:00.123456")
        self.assertIsNotNone(result)
        self.assertEqual(result.microsecond, 123456)
    
    def test_parse_iso_ts_with_timezone(self):
        """Test parsing ISO timestamp with timezone offset."""
        result = parse_iso_ts("2025-11-28T12:00:00+00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 12)
    
    def test_parse_iso_ts_none(self):
        """Test parsing None returns None."""
        self.assertIsNone(parse_iso_ts(None))
        self.assertIsNone(parse_iso_ts(""))
    
    def test_format_duration_seconds(self):
        """Test formatting duration in seconds."""
        self.assertEqual(format_duration(90), "01:30")
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(59), "00:59")
    
    def test_format_duration_hours(self):
        """Test formatting duration with hours."""
        self.assertEqual(format_duration(3661), "01:01:01")
        self.assertEqual(format_duration(7200), "02:00:00")
    
    def test_format_duration_none(self):
        """Test formatting None duration."""
        self.assertEqual(format_duration(None), "—")
    
    def test_format_cost(self):
        """Test formatting cost."""
        self.assertEqual(format_cost(0.0123), "$0.0123")
        self.assertEqual(format_cost(1.5), "$1.5000")
    
    def test_format_cost_zero(self):
        """Test formatting zero cost."""
        self.assertEqual(format_cost(0.0), "—")
        self.assertEqual(format_cost(None), "—")
    
    def test_truncate_target_short(self):
        """Test truncating short target."""
        self.assertEqual(truncate_target("short", 30), "short")
    
    def test_truncate_target_long(self):
        """Test truncating long target."""
        result = truncate_target("this is a very long target string that should be truncated", 30)
        self.assertEqual(len(result), 30)
        self.assertTrue(result.endswith("..."))


class TestPathValidation(unittest.TestCase):
    """Test path validation guards."""
    
    def test_validate_fpf_logs_path_valid(self):
        """Test valid FPF logs path."""
        self.assertTrue(validate_fpf_logs_path(
            "C:/dev/silky/api_cost_multiplier/FilePromptForge/logs/abc123",
            "C:/dev/silky/api_cost_multiplier"
        ))
    
    def test_validate_fpf_logs_path_eval_logs(self):
        """Test valid eval_fpf_logs path."""
        self.assertTrue(validate_fpf_logs_path(
            "C:/dev/silky/api_cost_multiplier/logs/eval_fpf_logs/run_123",
            "C:/dev/silky/api_cost_multiplier"
        ))
    
    def test_validate_fpf_logs_path_invalid(self):
        """Test invalid path outside expected locations."""
        self.assertFalse(validate_fpf_logs_path(
            "C:/some/other/path/logs",
            "C:/dev/silky/api_cost_multiplier"
        ))
    
    def test_validate_fpf_logs_path_empty(self):
        """Test empty path."""
        self.assertFalse(validate_fpf_logs_path("", ""))
        self.assertFalse(validate_fpf_logs_path(None, ""))


class TestEvalPhaseEnum(unittest.TestCase):
    """Test EvalPhase enum."""
    
    def test_display_names(self):
        """Test phase display names."""
        self.assertEqual(EvalPhase.PRECOMBINE_SINGLE.display_name, "Phase 1: Pre-Combine Single Eval")
        self.assertEqual(EvalPhase.COMBINER.display_name, "Phase 3: Combiner Generation")
    
    def test_short_names(self):
        """Test phase short names."""
        self.assertEqual(EvalPhase.PRECOMBINE_SINGLE.short_name, "pre-s")
        self.assertEqual(EvalPhase.POSTCOMBINE_PAIRWISE.short_name, "post-p")


class TestExpectedRun(unittest.TestCase):
    """Test ExpectedRun dataclass."""
    
    def test_expected_id_auto_generated(self):
        """Test expected_id is auto-generated."""
        run = ExpectedRun(
            run_num=1,
            phase=EvalPhase.PRECOMBINE_SINGLE,
            judge_model="google_gemini-2.5-flash",
            target="doc1",
            expected_index=1
        )
        self.assertIsNotNone(run.expected_id)
        self.assertEqual(len(run.expected_id), 12)  # md5 hash truncated to 12 chars
    
    def test_expected_id_deterministic(self):
        """Test expected_id is deterministic for same inputs."""
        run1 = ExpectedRun(
            run_num=1,
            phase=EvalPhase.PRECOMBINE_SINGLE,
            judge_model="google_gemini-2.5-flash",
            target="doc1",
            expected_index=1
        )
        run2 = ExpectedRun(
            run_num=2,  # Different run_num
            phase=EvalPhase.PRECOMBINE_SINGLE,
            judge_model="google_gemini-2.5-flash",
            target="doc1",
            expected_index=1
        )
        # expected_id should be same (based on phase, judge, target only)
        self.assertEqual(run1.expected_id, run2.expected_id)


class TestGenerateExpectedRuns(unittest.TestCase):
    """Test expected runs generation with phase gating."""
    
    def setUp(self):
        """Create temp config files for testing."""
        self.temp_dir = tempfile.mkdtemp()
        
        # Main config
        self.config_path = os.path.join(self.temp_dir, "config.yaml")
        with open(self.config_path, "w") as f:
            f.write("""
runs:
  - type: fpf
    provider: google
    model: gemini-2.5-flash
  - type: gptr
    provider: openai
    model: gpt-4o
eval:
  mode: both
  pairwise_top_n: 2
combine:
  enabled: true
  models:
    - provider: google
      model: gemini-2.5-flash
""")
        
        # Eval config
        self.eval_config_path = os.path.join(self.temp_dir, "eval_config.yaml")
        with open(self.eval_config_path, "w") as f:
            f.write("""
models:
  google_gemini-2.5-flash:
    provider: google
    model: gemini-2.5-flash
""")
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_expected_runs_mode_both(self):
        """Test expected runs with mode=both."""
        aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
        )
        runs = aggregator.generate_expected_runs()
        
        # Should have runs from all 5 phases
        phases = set(r.phase for r in runs)
        self.assertIn(EvalPhase.PRECOMBINE_SINGLE, phases)
        self.assertIn(EvalPhase.PRECOMBINE_PAIRWISE, phases)
        self.assertIn(EvalPhase.COMBINER, phases)
        self.assertIn(EvalPhase.POSTCOMBINE_SINGLE, phases)
        self.assertIn(EvalPhase.POSTCOMBINE_PAIRWISE, phases)
    
    def test_generate_expected_runs_mode_single(self):
        """Test expected runs with mode=single."""
        # Modify config
        with open(self.config_path, "w") as f:
            f.write("""
runs:
  - type: fpf
    provider: google
    model: gemini-2.5-flash
eval:
  mode: single
  pairwise_top_n: 2
combine:
  enabled: false
""")
        
        aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
        )
        runs = aggregator.generate_expected_runs()
        
        # Should only have pre-combine single phase
        phases = set(r.phase for r in runs)
        self.assertIn(EvalPhase.PRECOMBINE_SINGLE, phases)
        self.assertNotIn(EvalPhase.PRECOMBINE_PAIRWISE, phases)
        self.assertNotIn(EvalPhase.COMBINER, phases)
    
    def test_generate_expected_runs_combine_disabled(self):
        """Test expected runs with combine disabled."""
        with open(self.config_path, "w") as f:
            f.write("""
runs:
  - type: fpf
    provider: google
    model: gemini-2.5-flash
eval:
  mode: both
  pairwise_top_n: 2
combine:
  enabled: false
""")
        
        aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
        )
        runs = aggregator.generate_expected_runs()
        
        # Should not have combiner or post-combine phases
        phases = set(r.phase for r in runs)
        self.assertNotIn(EvalPhase.COMBINER, phases)
        self.assertNotIn(EvalPhase.POSTCOMBINE_SINGLE, phases)
        self.assertNotIn(EvalPhase.POSTCOMBINE_PAIRWISE, phases)
    
    def test_expected_runs_sequential_numbering(self):
        """Test that run numbers are sequential."""
        aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
        )
        runs = aggregator.generate_expected_runs()
        
        run_nums = [r.run_num for r in runs]
        expected_nums = list(range(1, len(runs) + 1))
        self.assertEqual(run_nums, expected_nums)
    
    def test_eval_phase_set_precombine(self):
        """Test that eval_phase_set='precombine' only includes phases 1-2."""
        aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
            eval_phase_set="precombine",
        )
        runs = aggregator.generate_expected_runs()
        
        # Should only have pre-combine phases
        phases = set(r.phase for r in runs)
        self.assertIn(EvalPhase.PRECOMBINE_SINGLE, phases)
        self.assertIn(EvalPhase.PRECOMBINE_PAIRWISE, phases)
        # Should NOT have post-combine phases
        self.assertNotIn(EvalPhase.COMBINER, phases)
        self.assertNotIn(EvalPhase.POSTCOMBINE_SINGLE, phases)
        self.assertNotIn(EvalPhase.POSTCOMBINE_PAIRWISE, phases)
    
    def test_eval_phase_set_postcombine(self):
        """Test that eval_phase_set='postcombine' only includes phases 3-5."""
        aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
            eval_phase_set="postcombine",
        )
        runs = aggregator.generate_expected_runs()
        
        # Should NOT have pre-combine phases
        phases = set(r.phase for r in runs)
        self.assertNotIn(EvalPhase.PRECOMBINE_SINGLE, phases)
        self.assertNotIn(EvalPhase.PRECOMBINE_PAIRWISE, phases)
        # Should have post-combine phases (if combine enabled)
        self.assertIn(EvalPhase.COMBINER, phases)
        self.assertIn(EvalPhase.POSTCOMBINE_SINGLE, phases)
        self.assertIn(EvalPhase.POSTCOMBINE_PAIRWISE, phases)
    
    def test_eval_phase_set_none(self):
        """Test that eval_phase_set=None includes all phases."""
        aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
            eval_phase_set=None,  # Default
        )
        runs = aggregator.generate_expected_runs()
        
        # Should have all phases
        phases = set(r.phase for r in runs)
        self.assertIn(EvalPhase.PRECOMBINE_SINGLE, phases)
        self.assertIn(EvalPhase.PRECOMBINE_PAIRWISE, phases)
        self.assertIn(EvalPhase.COMBINER, phases)
        self.assertIn(EvalPhase.POSTCOMBINE_SINGLE, phases)
        self.assertIn(EvalPhase.POSTCOMBINE_PAIRWISE, phases)


class TestPhaseDetection(unittest.TestCase):
    """Test phase detection from run_id."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config.yaml")
        self.eval_config_path = os.path.join(self.temp_dir, "eval_config.yaml")
        
        with open(self.config_path, "w") as f:
            f.write("runs: []\neval:\n  mode: both\ncombine:\n  enabled: false\n")
        with open(self.eval_config_path, "w") as f:
            f.write("models: {}\n")
        
        self.aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
        )
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_detect_single_phase(self):
        """Test detecting single eval phase."""
        phase = self.aggregator._detect_phase_from_run_id("single-google-gemini-doc1-abc123")
        self.assertEqual(phase, EvalPhase.PRECOMBINE_SINGLE)
    
    def test_detect_pairwise_phase(self):
        """Test detecting pairwise eval phase."""
        phase = self.aggregator._detect_phase_from_run_id("pairwise-google-gemini-doc1-vs-doc2-abc")
        self.assertEqual(phase, EvalPhase.PRECOMBINE_PAIRWISE)
    
    def test_detect_post_single_phase(self):
        """Test detecting post-combine single phase."""
        phase = self.aggregator._detect_phase_from_run_id("post-single-google-gemini-doc1-abc")
        self.assertEqual(phase, EvalPhase.POSTCOMBINE_SINGLE)
    
    def test_detect_post_pairwise_phase(self):
        """Test detecting post-combine pairwise phase."""
        phase = self.aggregator._detect_phase_from_run_id("post-pairwise-google-gemini-doc1-vs-doc2")
        self.assertEqual(phase, EvalPhase.POSTCOMBINE_PAIRWISE)
    
    def test_detect_combiner_phase(self):
        """Test detecting combiner phase."""
        phase = self.aggregator._detect_phase_from_run_id("combine-google-gemini-top2-abc")
        self.assertEqual(phase, EvalPhase.COMBINER)
    
    def test_detect_unknown_phase(self):
        """Test unknown run_id returns None."""
        phase = self.aggregator._detect_phase_from_run_id("unknown-format-run-id")
        self.assertIsNone(phase)


class TestTargetExtraction(unittest.TestCase):
    """Test target extraction from run_id."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config.yaml")
        self.eval_config_path = os.path.join(self.temp_dir, "eval_config.yaml")
        
        with open(self.config_path, "w") as f:
            f.write("runs: []\neval:\n  mode: both\ncombine:\n  enabled: false\n")
        with open(self.eval_config_path, "w") as f:
            f.write("models: {}\n")
        
        self.aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
        )
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_extract_single_target(self):
        """Test extracting target from single eval run_id."""
        target = self.aggregator._extract_target_from_run_id("single-google-gemini-mydoc-abc123")
        self.assertEqual(target, "mydoc")
    
    def test_extract_pairwise_target(self):
        """Test extracting target from pairwise run_id."""
        target = self.aggregator._extract_target_from_run_id("pairwise-google-gemini-doc1-vs-doc2-abc")
        self.assertIsNotNone(target)
        self.assertIn("vs", target)


class TestMatchingLogic(unittest.TestCase):
    """Test tiered matching logic."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config.yaml")
        self.eval_config_path = os.path.join(self.temp_dir, "eval_config.yaml")
        
        with open(self.config_path, "w") as f:
            f.write("""
runs:
  - type: fpf
    provider: google
    model: gemini-2.5-flash
eval:
  mode: single
  pairwise_top_n: 2
combine:
  enabled: false
""")
        with open(self.eval_config_path, "w") as f:
            f.write("""
models:
  google_gemini-2.5-flash:
    provider: google
    model: gemini-2.5-flash
""")
        
        self.aggregator = EvalTimelineAggregator(
            config_path=self.config_path,
            eval_config_path=self.eval_config_path,
        )
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_match_exact(self):
        """Test exact matching by (phase, judge, target)."""
        expected = [ExpectedRun(
            run_num=1,
            phase=EvalPhase.PRECOMBINE_SINGLE,
            judge_model="google_gemini-2.5-flash",
            target="fpf-google-gemini-2.5-flash",
            expected_index=1
        )]
        
        actual_log = ActualRunLog(
            run_id="single-google-gemini-fpf-google-gemini-2.5-flash-abc",
            run_group_id="group1",
            model="gemini-2.5-flash",
            provider="google",
            started_at=datetime.now(),
            finished_at=datetime.now() + timedelta(seconds=30),
            duration_seconds=30.0,
            total_tokens=1000,
            total_cost_usd=0.01,
        )
        actual_log.detected_phase = EvalPhase.PRECOMBINE_SINGLE
        actual_log.detected_target = "fpf-google-gemini-2.5-flash"
        
        rows, unplanned = self.aggregator.match_expected_to_actual(
            expected,
            {actual_log.dedup_key: actual_log},
            {}
        )
        
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].matched)
        self.assertEqual(rows[0].match_status, "exact")
    
    def test_match_ordinal_fallback(self):
        """Test ordinal matching when exact fails."""
        expected = [ExpectedRun(
            run_num=1,
            phase=EvalPhase.PRECOMBINE_SINGLE,
            judge_model="google_gemini-2.5-flash",
            target="fpf-google-gemini-2.5-flash",
            expected_index=1
        )]
        
        # Actual log with different target (won't exact match)
        actual_log = ActualRunLog(
            run_id="single-google-gemini-different-target-abc",
            run_group_id="group1",
            model="gemini-2.5-flash",
            provider="google",
            started_at=datetime.now(),
            finished_at=datetime.now() + timedelta(seconds=30),
            duration_seconds=30.0,
            total_tokens=1000,
            total_cost_usd=0.01,
        )
        actual_log.detected_phase = EvalPhase.PRECOMBINE_SINGLE
        actual_log.detected_target = "different-target"
        
        rows, unplanned = self.aggregator.match_expected_to_actual(
            expected,
            {actual_log.dedup_key: actual_log},
            {}
        )
        
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].matched)
        self.assertEqual(rows[0].match_status, "ordinal")
    
    def test_no_match_returns_missing(self):
        """Test unmatched expected returns missing status."""
        expected = [ExpectedRun(
            run_num=1,
            phase=EvalPhase.PRECOMBINE_SINGLE,
            judge_model="google_gemini-2.5-flash",
            target="fpf-google-gemini-2.5-flash",
            expected_index=1
        )]
        
        # No actual logs
        rows, unplanned = self.aggregator.match_expected_to_actual(
            expected,
            {},
            {}
        )
        
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].matched)
        self.assertEqual(rows[0].match_status, "missing")
        self.assertEqual(rows[0].status_icon, "✗")


class TestSubtotalCalculation(unittest.TestCase):
    """Test phase subtotal calculations."""
    
    def test_calculate_subtotals(self):
        """Test subtotal calculation by phase."""
        rows = [
            TimelineRow(
                run_num=1,
                phase=EvalPhase.PRECOMBINE_SINGLE.value,
                phase_display="Phase 1",
                phase_short="pre-s",
                judge_model="model1",
                target="doc1",
                target_short="doc1",
                matched=True,
                log_duration_seconds=30.0,
                total_tokens=1000,
                total_cost_usd=0.01,
                db_row_count=4,
            ),
            TimelineRow(
                run_num=2,
                phase=EvalPhase.PRECOMBINE_SINGLE.value,
                phase_display="Phase 1",
                phase_short="pre-s",
                judge_model="model1",
                target="doc2",
                target_short="doc2",
                matched=True,
                log_duration_seconds=45.0,
                total_tokens=1500,
                total_cost_usd=0.02,
                db_row_count=4,
            ),
        ]
        
        temp_dir = tempfile.mkdtemp()
        config_path = os.path.join(temp_dir, "config.yaml")
        eval_config_path = os.path.join(temp_dir, "eval_config.yaml")
        
        with open(config_path, "w") as f:
            f.write("runs: []\neval:\n  mode: both\ncombine:\n  enabled: false\n")
        with open(eval_config_path, "w") as f:
            f.write("models: {}\n")
        
        aggregator = EvalTimelineAggregator(
            config_path=config_path,
            eval_config_path=eval_config_path,
        )
        
        subtotals = aggregator.calculate_subtotals(rows)
        
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        self.assertEqual(len(subtotals), 1)
        self.assertEqual(subtotals[0].run_count, 2)
        self.assertEqual(subtotals[0].matched_count, 2)
        self.assertEqual(subtotals[0].total_duration_seconds, 75.0)
        self.assertEqual(subtotals[0].total_tokens, 2500)
        self.assertEqual(subtotals[0].total_cost_usd, 0.03)
        self.assertEqual(subtotals[0].total_db_rows, 8)


class TestDeduplication(unittest.TestCase):
    """Test deduplication logic."""
    
    def test_dedup_key_generation(self):
        """Test dedup key is generated correctly."""
        log = ActualRunLog(
            run_id="run123",
            run_group_id="group456",
            model="gemini",
            provider="google",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            duration_seconds=0,
            log_file_path="/path/to/log.json"
        )
        
        self.assertEqual(log.dedup_key, "group456:run123:/path/to/log.json")
    
    def test_dedup_key_without_group(self):
        """Test dedup key with no run_group_id."""
        log = ActualRunLog(
            run_id="run123",
            run_group_id=None,
            model="gemini",
            provider="google",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            duration_seconds=0,
            log_file_path="/path/to/log.json"
        )
        
        self.assertEqual(log.dedup_key, ":run123:/path/to/log.json")


if __name__ == "__main__":
    unittest.main()
