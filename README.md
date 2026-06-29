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

| Pattern | Detected |
|---|---|
| Global/static written in `*_IRQHandler`, read in main | ✓ |
| HAL weak callbacks (`HAL_UART_RxCpltCallback`, etc.) | ✓ |
| Transitive ISR context via call graph | ✓ |
| Compound writes (`\|=`, `&=`, `++`, `--`) | ✓ |

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
| Variables only read by ISR, never written | |

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

# SARIF output for GitHub Code Scanning
reentrant analyze . --sarif --no-explain > reentrant.sarif

# JSON output
reentrant analyze . --json --no-explain

# Skip LLM explanation layer
reentrant analyze . --no-explain
```

Exit code `0` — no findings (or all suppressed by LLM). Exit code `1` — findings present.

## LLM explanation layer

Set `ANTHROPIC_API_KEY` to enable a post-analysis pass using Claude Haiku that:

- Generates a plain-English description of the race condition and a one-line fix suggestion
- Suppresses likely false positives it can identify from context

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
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install reentrant
      - name: Run ISR safety analysis
        id: reentrant
        run: reentrant analyze . --sarif --no-explain > reentrant.sarif
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
- `static` variables with the same name in different translation units share a symbol table entry; the checker may miss bugs or produce false positives in that case
- Does not model OS-level mutual exclusion (mutexes, semaphores) — only interrupt-disable guards
- Does not detect ABA / lock-free algorithmic correctness issues

## Development

```bash
git clone https://github.com/saintbate/reentrant
cd reentrant
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                  # 14 corpus tests
python tests/measure_fp.py  # real-world FP measurement
```
