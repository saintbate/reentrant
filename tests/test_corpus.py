"""Ground-truth corpus tests: bugs found, safe files produce zero findings."""
from pathlib import Path

import pytest

from reentrant.analysis.checker import analyze
from reentrant.model.rules import ISR_BLOCKING_CALL, ISR_STALE_READ, Tier
from reentrant.parse.loader import load_repo

CORPUS = Path(__file__).parent / "corpus"
STATIC_SCOPE = CORPUS / "static_scope"


def _analyze_file(name: str):
    files = load_repo(CORPUS)
    target = [f for f in files if f.path.name == name]
    assert target, f"corpus file {name} not found"
    return analyze(target)


# ── Bug files — each must produce ≥1 finding ──────────────────────────────────

@pytest.mark.parametrize("filename,expected_var", [
    ("bug_01_basic_flag.c", "flag"),
    ("bug_02_counter.c", "tick_count"),
    ("bug_03_hal_callback.c", "rx_ready"),
    ("bug_04_indirect_call.c", "adc_value"),
    ("bug_05_struct_member.c", "msg_buf"),
    # Compound read-modify-write (|=) is a write — not protected by atomicity
    ("bug_06_compound_write.c", "event_mask"),
])
def test_bug_detected(filename: str, expected_var: str) -> None:
    findings = _analyze_file(filename)
    var_names = {f.variable for f in findings}
    assert expected_var in var_names, (
        f"{filename}: expected '{expected_var}' to be flagged, got {var_names}"
    )


# ── Safe files — must produce zero findings ────────────────────────────────────

@pytest.mark.parametrize("filename", [
    "safe_01_volatile.c",
    "safe_02_critical_section.c",
    # safe_03_readonly.c is NOT here — it's a genuine isr-stale-read Tier 2
    # candidate, see test_stale_read_detected below
    "safe_04_freertos_guard.c",
    "safe_05_isr_only.c",
    # ARM PRIMASK save/disable/restore pattern
    "safe_06_primask_guard.c",
    # FreeRTOS portDISABLE_INTERRUPTS / portENABLE_INTERRUPTS
    "safe_07_port_critical.c",
    # CMSIS __IO type alias treated as volatile
    "safe_08_cmsis_io.c",
    # malloc() called only outside ISR context — not flagged
    "safe_09_malloc_outside_isr.c",
    # xQueueSendFromISR is the ISR-safe variant — not itself flagged
    "safe_10_freertos_from_isr_variant.c",
    # CMSIS-RTOS-style inHandlerMode() dual-dispatch wrapper — real-world FP
    # found via tests/measure_fp.py, must not be flagged
    "safe_11_freertos_dual_dispatch.c",
    # volatile threshold, read-only in ISR — isr-stale-read must respect
    # the same volatile suppression as isr-shared-var
    "safe_12_volatile_threshold.c",
    # non-ISR write is guarded — isr-stale-read must respect guards too
    "safe_13_guarded_threshold.c",
])
def test_no_false_positive(filename: str) -> None:
    findings = _analyze_file(filename)
    assert findings == [], (
        f"{filename}: expected zero findings, got {[f.variable for f in findings]}"
    )


# ── isr-blocking-call rule: libc / STM32 HAL / FreeRTOS API misuse ───────────

@pytest.mark.parametrize("filename,expected_api", [
    ("bug_07_malloc_in_isr.c", "malloc"),
    ("bug_08_hal_blocking_in_isr.c", "HAL_UART_Transmit"),
    ("bug_09_freertos_non_isr_api.c", "xQueueSend"),
])
def test_blocking_call_detected(filename: str, expected_api: str) -> None:
    findings = _analyze_file(filename)
    matches = [f for f in findings if f.variable == expected_api]
    assert matches, (
        f"{filename}: expected a call to '{expected_api}' to be flagged, "
        f"got {[f.variable for f in findings]}"
    )
    assert matches[0].rule_id == ISR_BLOCKING_CALL.id
    assert matches[0].explanation, "blocking-call findings must self-explain from the API table"


# ── isr-stale-read rule (Tier 2): ISR reads what non-ISR writes ──────────────

def test_stale_read_detected() -> None:
    """threshold in safe_03_readonly.c is read-only in the ISR and written
    (unguarded, non-volatile) in set_threshold() — a genuine stale-read
    candidate. It must be Tier 2: advisory only, never blocking.
    """
    findings = _analyze_file("safe_03_readonly.c")
    matches = [f for f in findings if f.variable == "threshold"]
    assert matches, f"expected 'threshold' to be flagged, got {[f.variable for f in findings]}"
    assert matches[0].rule_id == ISR_STALE_READ.id
    assert matches[0].tier is Tier.TIER_2
    assert matches[0].can_block is False


# ── Static-scope isolation — multi-file scenarios ─────────────────────────────

def test_static_fp_not_cross_contaminated() -> None:
    """An ISR in fp_bug.c must not produce a finding attributed to fp_clean.c.

    Both files declare `static int counter`.  Without file-scoped bucketing the
    checker would mix their accesses and could flag the clean file's counter.
    """
    findings = analyze(load_repo(STATIC_SCOPE))
    counter_findings = [f for f in findings if f.variable == "counter"]
    assert counter_findings, "expected at least one finding for 'counter' in fp_bug.c"
    for f in counter_findings:
        assert f.declaring_file.name == "fp_bug.c", (
            f"'counter' finding attributed to wrong file: {f.declaring_file.name}"
        )


def test_static_volatile_in_one_file_does_not_mask_bug() -> None:
    """fn_safe.c has `static volatile int sensor`; fn_bug.c has a non-volatile
    version that IS written by an ISR.  The volatile in fn_safe.c must not
    suppress the finding for fn_bug.c's sensor.
    """
    findings = analyze(load_repo(STATIC_SCOPE))
    sensor_findings = [f for f in findings if f.variable == "sensor"]
    assert sensor_findings, "expected a finding for 'sensor' in fn_bug.c"
    for f in sensor_findings:
        assert f.declaring_file.name == "fn_bug.c", (
            f"'sensor' finding attributed to wrong file: {f.declaring_file.name}"
        )
