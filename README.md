# reentrant

Static analysis for **ISR-safety bugs** in STM32 firmware written in C.

Reentrant catches the class of bug where a global variable is written inside an interrupt service routine and also accessed in main-loop code without `volatile` or a critical-section guard — a data race that can cause silent corruption on ARM Cortex-M.

```
$ reentrant analyze ./my-firmware/

Analyzing 47 file(s)…
LLM explanation skipped — set ANTHROPIC_API_KEY to enable.
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┓
┃ Variable   ┃ Declared at    ┃ ISR context        ┃ Non-ISR access     ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
│ rx_ready   │ uart.c:12      │ HAL_UART_RxCpltC…  │ main.c:44          │
│ tick_count │ timers.c:8     │ TIM2_IRQHandler    │ main.c:61          │
└────────────┴────────────────┴────────────────────┴────────────────────┘
2 potential ISR-safety issue(s). Add 'volatile' or wrap non-ISR accesses
in a critical section.
```

## What it detects

**`isr-shared-var`** — a global/static variable is written in an ISR and accessed
in main-loop code without `volatile` or a critical-section guard.

| Pattern | Detected |
|---|---|
| Global/static written in `*_IRQHandler`, read in main | ✓ |
| HAL weak callbacks (`HAL_UART_RxCpltCallback`, etc.) | ✓ |
| Transitive ISR context via call graph | ✓ |
| Compound writes (`\|=`, `&=`, `++`, `--`) | ✓ |

**`isr-blocking-call`** — a call to a known blocking/non-reentrant API from ISR
context (or a function transitively reachable from one), checked against a
curated table ([`reentrant/data/isr_unsafe_apis.toml`](reentrant/data/isr_unsafe_apis.toml)):

| Category | Examples |
|---|---|
| libc | `malloc`, `free`, `printf` |
| STM32 HAL blocking variants | `HAL_Delay`, `HAL_UART_Transmit`, `HAL_SPI_Transmit`, `HAL_I2C_Master_Transmit` |
| FreeRTOS APIs missing their `FromISR` counterpart | `xQueueSend`, `xQueueReceive`, `xSemaphoreGive`, `xSemaphoreTake`, `vTaskDelay` |

A call is *not* flagged if the same function also calls the ISR-safe counterpart
(e.g. `xSemaphoreGiveFromISR`) — that's the CMSIS-RTOS `inHandlerMode()` runtime-dispatch
pattern every STM32Cube + FreeRTOS project ships, not a bug.

**`isr-stale-read`** (Tier 2, advisory) — the inverse of `isr-shared-var`: an ISR only
*reads* a variable that non-ISR code writes without `volatile` or a guard. The ISR may
see a stale or torn value, but this pattern is common and mostly benign for
write-once-at-init config/threshold variables, so it's advisory only rather than
blocking — see [Tiers](#tiers).

## What it does NOT flag (safe patterns recognised)

| Guard | Example |
|---|---|
| `volatile` qualifier | `volatile int flag` |
| CMSIS `__IO` alias | `__IO uint32_t reg` |
| `__disable_irq` / `__enable_irq` | CMSIS bare-metal |
| PRIMASK save/restore | `uint32_t p = __get_PRIMASK(); __disable_irq(); … __set_PRIMASK(p);` |
| FreeRTOS `taskENTER_CRITICAL` / `taskEXIT_CRITICAL` | |
| FreeRTOS `portDISABLE_INTERRUPTS` / `portENABLE_INTERRUPTS` | |
| ISR-only variables (no non-ISR access) | |

## Install

Requires Python 3.11+.

```bash
pip install reentrant
```

## Usage

```bash
# Analyse a whole firmware directory
reentrant analyze ./path/to/firmware/

# Single file
reentrant analyze src/main.c

# PR-scoped: only report findings that touch lines changed since origin/main
reentrant analyze . --diff-base origin/main

# SARIF output for GitHub Code Scanning
reentrant analyze . --sarif --no-explain > reentrant.sarif

# JSON output
reentrant analyze . --json --no-explain

# Skip LLM explanation layer
reentrant analyze . --no-explain
```

Exit code `0` — no blocking findings (or all suppressed by LLM). Exit code `1` — at
least one Tier 1 finding present. See [Tiers](#tiers) below.

### Tiers

Every rule is Tier 1 (precise enough to fail CI) or Tier 2 (advisory — shown as a PR
comment, never blocks). The exit code depends **only** on Tier 1: a noisy heuristic
can never fail your build, no matter how it's classified internally.

`isr-shared-var` and `isr-blocking-call` are Tier 1, validated at 0% false positives
against the real-world benchmark corpus. `isr-stale-read` is the first Tier 2 rule —
by design it's noisier (config/threshold variables written once at init produce many
candidates that look identical to real bugs from a purely syntactic view), which is
why it's advisory-only. Run against the real-world benchmark: 49 raw candidates, of
which LLM triage (see below) suppressed 31 (63%) as implausible, leaving 18 for
review — a working demonstration of the Tier 2 + LLM-triage design, not just a plan.

### Diff-aware scoping

`--diff-base <ref>` scopes findings to a PR: analysis still runs whole-repo (ISR
reachability genuinely needs the full call graph), but the reported findings are
filtered to ones where the declaration, the ISR access, or the non-ISR access falls
on a line the diff touched. A finding surfaces if the PR introduced the unsafe ISR
write *or* the unguarded read *or* changed the declaration (e.g. dropped `volatile`) —
pre-existing bugs the PR didn't touch are suppressed, so a PR doesn't get buried under
issues it had nothing to do with.

## LLM explanation layer (Tier 2 triage)

Set `ANTHROPIC_API_KEY` to enable a post-analysis pass using Claude Haiku that:

- Generates a plain-English description of the race condition and a one-line fix suggestion
- Suppresses likely false positives it can identify from full function context

This is also how Tier 2 candidates get triaged before showing up as advisory findings
— the same pass runs on every finding. Rules that already self-explain deterministically
(`isr-blocking-call`, from its curated table) are skipped: there's nothing for the LLM
to add, and re-triaging a rule that's precise by construction only risks an incorrect
suppression.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
reentrant analyze ./my-firmware/
```

Skip it with `--no-explain` for CI pipelines where cost or latency matters.

## GitHub Actions

Add `.github/workflows/reentrant.yml` to your firmware repo:

```yaml
name: ISR Safety

on:
  push:
    branches: [main]
  pull_request:

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history — required for --diff-base to work
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install reentrant
      - name: Run ISR safety analysis
        id: reentrant
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            DIFF_ARGS="--diff-base origin/${{ github.base_ref }}"
          else
            DIFF_ARGS=""
          fi
          reentrant analyze . --sarif --no-explain $DIFF_ARGS > reentrant.sarif
        continue-on-error: true
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: reentrant.sarif
          category: reentrant
      - if: steps.reentrant.outcome == 'failure'
        run: exit 1
```

Findings appear as inline annotations on the PR diff in the **Security** tab.

> The SARIF upload requires GitHub Advanced Security. This is free for all public repositories; private repositories need a GHAS licence.

## Limitations

- C only (no C++)
- Single-core Cortex-M — does not model multi-core shared memory (STM32H7 M4/M7)
- Does not model OS-level mutual exclusion (mutexes, semaphores) — only interrupt-disable guards
- Does not detect ABA / lock-free algorithmic correctness issues

## Development

```bash
git clone https://github.com/saintbate/reentrant
cd reentrant
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # corpus + diff-scoping + tier-system tests
python tests/measure_fp.py   # real-world FP measurement
```
