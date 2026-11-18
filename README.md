# GTA VI launch-day Twitch viewer forecaster

Forecasts how many people watch **Grand Theft Auto VI** live on Twitch in each
hour of its release day, 2026-11-19 (UTC), from everything recorded up to the end
of the day's first hour.

Entry for the make.fun bounty
[Forecast GTA VI's launch-day Twitch viewers hour by hour](https://make.fun/bounty/gta6-twitch-ccu-forecast-01).

[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/almanraza/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/almanraza/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

## The idea

A launch day is not one curve. It is two, and which one you get is decided by how
much of the day's audience hour 1 already holds.

**A midnight unlock in the game's main market** puts the peak in hour 1 and the
day decays from there. **An unlock that lands while most of the world is asleep**
leaves hour 1 holding a fraction of the audience, and the day ramps up as each
region's midnight arrives, peaking late.

GTA VI is the second kind. New Zealand unlocks at 11:00Z the day before, central
Europe at 23:00Z, the UK at 00:00Z, the US east coast at 05:00Z and the west coast
at 08:00Z. Hour 1 (00:00–01:00Z) therefore holds Europe and the UK but almost none
of the Americas, so the day should keep rising for many hours after it.

The regime is read from the case itself rather than assumed: hour 1's print
against the category's own pre-release baseline, the median of the history the
case carries. A launch whose hour 1 already stands far above its ordinary
audience is the first kind; one whose hour 1 is only a few times its ordinary
audience is the second.

Within a regime the shape is a smooth curve — a level, a trend and three bumps
where launch days actually bend — fitted to the comparables' log ratio to their
own hour 1. The spread is the empirical spread of the residuals around that
curve, so the quantiles are measured rather than assumed. The pinball loss is a
proper scoring rule, so an honest spread is what scores best.

## What it does

Reads every `*.in` case in the input directory and writes one `*.out` per case:

```json
{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}
```

23 rows, hours 2 to 24, five quantiles each, non-decreasing, finite, above 0.

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, no network. Deterministic: two runs on the
same case write the same bytes. About 0.2 s for all four practice cases, against
an 8 s per-case cap.

## How it was checked

The practice answers stay on the server, so the local signal is leave-one-out
over the 38 comparables the cases ship: hold one past launch out, fit on the
other 37, forecast the held-out launch from its own hour-1 print, and score with
the contest's own pinball loss.

| Pool | House baseline | This model | Change |
|---|---|---|---|
| all 38 launches | 0.9297 | 0.6427 | −30.9% |
| launches with hour 1 ≥ 20k | 0.3214 | 0.2795 | −13.0% |
| launches with hour 1 ≥ 50k | 0.2509 | 0.2203 | −12.2% |

The large-launch rows are the honest comparison: GTA VI is a launch of that size,
and the small-launch rows are dominated by one or two big streamers.

## Licence

MIT — see [LICENSE](LICENSE).
