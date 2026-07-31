# tradefabe

A doctrine-governed lab for testing trading strategies honestly, plus a **paper-trading
engine** that runs the survivors as autonomous simulated books. **Paper only — no real money
is connected, and nothing here is investment advice.**

## What this project learned (the short version)
Every predictive approach tested has come out dead or overfit against pre-registered kill
rules: price patterns, congress-copying, insider-following, thematic picking, candlestick
wicks, a pretrained OHLCV foundation model, and an automated factory of parametrized variants.
**139 unique strategies in `graveyard.csv` as of 2026-07-29, 0 ALIVE.**

Two things survived scrutiny: **diversified buy-and-hold**, and **delta-neutral crypto
funding carry** (~12%/yr in the 2023–26 window, paid for bearing real crypto-infrastructure
tail risk). Being machine-generated is not a lower bar — same doctrine, same kill rules.

Receipts in `graveyard.csv`, verdicts and family taxonomy in [STRATEGIES.md](STRATEGIES.md),
rules in [DOCTRINE.md](DOCTRINE.md), agent orientation in [CLAUDE.md](CLAUDE.md).

## Layout
```
src/tradefabe/     the installable engine. engine.py is the data/sizing/returns core and the
                   single source of truth — nothing else keeps a private copy of the math.
                   signals.py, books.py, piggyback.py, factory.py (template library + live
                   generation), carry_live.py, carry_risk.py (funding-flip + liquidation
                   monitor), runner.py, cli.py, desktop.py, risk_register.py, paths.py.
                   hourly.py (family L) and kronos.py + kronos_live.py (family M) each hold
                   both the signals AND the live monitor books, so a study and its book
                   share one function instead of two copies that drift.
app.py             Streamlit dashboard. Two sidebar views: Paper Books (live books grouped
                   by family, click-to-select cards, per-strategy panel with trade log) and
                   Research Lab (verdicts, luck floor, correlation, piggyback lab, and a
                   detail view for strategies that never reached a live book). Plotly.
harness.py         research evaluator: doctrine gates (Deflated Sharpe Ratio + Combinatorial
                   Purged CV as of v1.4), noise floors, graveyard writer.
research/          one-off studies (insider, congressional, carry, thematic, day-trading),
                   piggyback_backtest.py, factory_run.py, kronos_backtest.py,
                   tsmom_backtest.py (standalone TSMOM study + plot), combine.py (blending /
                   piggyback experiments)
tests/             pytest suite (433 tests), runs in CI on every push/PR to main
graveyard.csv      the verdict ledger — every strategy ever evaluated. Tracked in git.
generated_templates.csv   the factory's own ledger of every live-generated candidate's spec,
                   logged before its verdict is known
artifacts/         generated research outputs (tracked in git)
state/paper/       paper-book ledgers, carry_risk.json, promotion registries. TRACKED in git
                   and written by the cloud engine — see "What runs unattended".
```

## Quickstart
```sh
./ops/setup_venv.sh           # builds the venv; refuses to run inside a synced tree

.venv/bin/tradefabe run       # one daily paper cycle: rebalance due books, carry, risk monitor
.venv/bin/tradefabe mark      # mark all books to current price (finer chart resolution)
.venv/bin/tradefabe status    # current book equities
.venv/bin/streamlit run app.py  # dashboard at localhost:8501

.venv/bin/python harness.py   # re-run the research evaluation (appends graveyard.csv)
.venv/bin/pytest tests/       # run the test suite
```

**`git pull` before reading the dashboard locally** — the cloud engine owns `state/` and
commits the ledger every cycle.

## The paper books
20 live books as of 2026-07-29, at $100k each. `carry_btc_eth` accrues **real Hyperliquid
funding** on a delta-neutral notional — when funding goes negative in bear regimes the book
bleeds, and watching that live is the point. The rest are backtest-DEAD monitor-only books:
family A/B/C trend and calendar strategies, family L's hourly candidates, family M's Kronos
forecaster books, and the strategy factory's promotions.

**A backtest-DEAD book is monitor-only forever and can never become `paper-confirmed`**
(DOCTRINE v1.2), no matter how good its paper data looks. **Retiring a book is a human
decision only** (v1.6) — there is deliberately no performance trigger, because auto-killing
losers would filter the forward record on results and manufacture survivorship bias in the
one dataset here that has none.

The dashboard's carry panel includes a risk monitor: a trailing 7-day funding-flip alert and
a short-leg liquidation-distance stress table, sized against Hyperliquid's own live margin
tiers (fetched fresh each run, not a hardcoded leverage guess).

## What runs unattended
**The paper engine runs in GitHub Actions, not on the Mac**
([`paper-engine.yml`](.github/workflows/paper-engine.yml)). It used to be three launchd
agents, but launchd does not fire while a Mac is asleep, so the ledger had multi-hour
overnight holes. **The Action is now the sole owner of `state/`**; the plists remain in
[`ops/`](ops/) but are never loaded, and re-enabling one would fork the ledger.

| cycle | what it does | when |
|---|---|---|
| `mark` | mark-only, no rebalance, so the live-equity chart has more than one point per day | hourly (GitHub spaces these ~2h in practice) |
| `run` | the actual rebalance, each book on its doctrine-registered M/W/D schedule | daily 22:07 UTC |
| `factory` | 20 fresh candidates through the full doctrine gate, best promoted to a live book | **paused since 2026-07-27** |

The factory is paused deliberately, not broken ([#98](https://github.com/dzheng1328/tradefabe/issues/98)):
it promoted a book every cycle regardless of verdict, so finding something and finding nothing
produced the same outcome, while every draw raised the multiple-testing bar for all future
candidates. `gh workflow run "paper engine" -f job=factory` still triggers it by hand. The
unbounded-accumulation half of #98 now has a direct fix regardless of the pause:
`MAX_FACTORY_PROMOTED` ([#147](https://github.com/dzheng1328/tradefabe/issues/147)) caps the
factory-owned pool (templates + generated + combos) and the dashboard surfaces a read-only
"up for review" list for anything old — never a retirement trigger, still Dave's call alone
per DOCTRINE v1.6. Whether to resume the cron is the separate, still-open strategic question
`RUNDOWN.md` leaves unanswered: would a factory ALIVE have been pleasing or alarming?

Five more automations run *inside* those jobs rather than on their own schedule: family L's
hourly monitor books, family M's Kronos books (daily only — inference needs torch and a
400MB checkpoint), real Hyperliquid funding accrual, the carry risk monitor, and the factory's
auto-promotion. None of them can raise; a data outage on a monitor book must never take down
the cycle that owns the real ledger.

Tests run in CI on every push and PR **to `main`** via
[`tests.yml`](.github/workflows/tests.yml) — a PR targeting any other branch gets no checks
at all, which reads like a failure but means the workflow never fired.

`.claude/settings.json` lets coding agents run `git` and `gh` without a prompt (force-push and
repo-deletion denied, since the rule here is branch-and-PR).

## Desktop app
`~/Applications/tradefabe.app` opens the dashboard in a native window with its own Dock icon
(auto-starts the Streamlit server if needed; closing the window stops a server it started).
Entry point: `tradefabe-app` (pywebview). The bundle is not tracked in git, but its build
script is — rebuild with [`ops/build_app.sh`](ops/build_app.sh).

> **Repo location matters.** This repo lived in `~/Documents` until 2026-07-26, where iCloud
> corrupted the venv and wrote conflict copies of tracked files: iCloud flags files in that
> tree as `hidden`, and Python 3.14's `site` module silently skips hidden `.pth` files, so an
> editable install stops resolving and `import tradefabe` fails. **It now lives at
> `~/tradefabe`**, with a compatibility symlink at the old path that new config must not use.
> `ops/setup_venv.sh` refuses to build inside a synced tree, and `tests/test_repo_location.py`
> guards against the conflict copies — one such copy of the paper-engine workflow once ran as
> a second live workflow.

## Principles
- Strategies are deterministic; **no LLM in the trade loop** (LLMs are for research,
  reporting, and auditing — a nondeterministic trader can't be honestly evaluated).
- Verdicts are out-of-sample, cost-pessimistic, pre-registered; dead strategies stay dead.
- Every strategy ever tested is logged in `graveyard.csv` — the multiple-testing record.
- Doctrine changes are **forward-only**. A verdict is never re-scored under a later version;
  recomputing one is legitimate as a diagnostic and never as a silent re-verdict.

## Roadmap
**`gh issue list` is authoritative.** The
[Projects board](https://github.com/users/dzheng1328/projects/1) is a planning *view* with
Status / Phase / Area / Priority — useful, but it lags, because adding an issue to it is a
manual step. It once drifted 13 issues behind and convinced a reader the lab had been idle for
a week. When the board and the issues disagree, the issues win.

Work completed before the tracker existed was backfilled as already-closed issues (#41–58),
so those are history rather than a queue.
