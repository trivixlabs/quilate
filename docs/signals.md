# The 7-signal rubric

Each coin gets 7 signals every time its verdict is computed. Each signal is in alert, not in alert, or without data. The sum of alerts gives the base verdict. Claude then confirms or adjusts it (see [architecture.md](architecture.md)).

Code: `backend/quilate/signals/rubric.py` (pure functions) and `backend/quilate/signals/inputs.py` (reads the database). Thresholds: `[thresholds]` in `backend/quilate/config.toml`. The values below are the defaults.

## Signals

| Code | Name in the UI | Alert when | Without data when |
|---|---|---|---|
| S1 | Força contra o BTC | The coin/BTC price fell more than 20% in 90 days (`s1_ret_90d = -0.20`) **and** is below its 200-day average. | The coin is BTC, or there are fewer than 200 daily closes against BTC. |
| S2 | Tendência de queda | The USD price is below its 200-day average, **and** it is more than 85% below its all-time high (`s2_drawdown = 0.85`), **and** the lowest close of the last 90 days is not higher than the lowest close of the 90 days before. | Fewer than 200 daily closes, or no all-time high. |
| S3 | Liquidez | Any of these: the 30-day average volume is below half the 180-day average (`s3_vol_ratio = 0.5`), the 30-day average daily volume is below 20 times your position (`s3_pos_mult = 20`), or the bid-ask spread is above 1% (`s3_spread = 0.01`). | None of the three checks has data. The volume ratio needs 180 days, the position check needs 30 days. |
| S4 | Oferta nova | Token unlocks in the next 90 days above 3% of supply (`s4_unlock_90d = 0.03`), or yearly inflation above 10% (`s4_inflation = 0.10`). | No unlock and no inflation data. |
| S5 | Risco de deslistagem | The coin has a Binance Monitoring Tag, or it is listed on only one exchange. | No delisting snapshot. |
| S6 | Analista | The analyst's latest stance on the coin is "sair" (exit), or the analyst has not mentioned the coin for more than 90 days (`s6_silence_days = 90`). | The analyst never mentioned the coin with a stance. |
| S7 | Atenção do grupo | Mentions in the last 7 days, compared with the 30-day weekly average, are below 0.3 times (`s7_low`), **or** above 3 times (`s7_high`) while the price is at 90% or more of its 90-day high (`s7_near_high`) and the members' average polarity is positive (or there is no polarity data). | No mention in 30 days. |

Notes:

- Percentages in the inputs are fractions: `0.03` means 3%.
- S7 counts all mentions of the coin. The polarity is the average of members' mentions (not the analyst's) in the last 7 days, from -1 to 1. Without polarity data, S7 uses only the mention ratio and the price. Many negative messages near the high are not counted as euphoria.
- A market snapshot older than 7 days counts as no data, not as old data (`MAX_AGE_DAYS` in `inputs.py`). This applies to the market caps, the inflation data and the delisting data.

## Market filter

`market_filter` adds 1 point when BTC dominance went up over the last 7 days **and** the alt season index is below 25. It adds 0 when either value is missing. The point does not apply to BTC itself.

## From points to verdict

```
points = number of signals in alert + market filter point (not for BTC)

0 to 2  -> Manter  (hold)
3 to 4  -> Reduzir (reduce)
5 or more -> Sair  (exit)
```

A signal without data counts as 0. The verdict labels stay in Portuguese in the API and the UI.

## Final verdict

The rubric verdict is the base. In the daily cycle and on a new message from the analyst, Claude reads the signals and the context and returns its own verdict. The final verdict is Claude's verdict. When the AI is paused by the spending limit, or its answer fails validation, the final verdict is the rubric's verdict and the card shows a flag (`ai_paused` or `ai_failed`). Price moves and delisting events recompute the rubric only.

## Hit rate

`track/record.py` checks each verdict after 7, 30 and 90 days:

- **Reduzir** means selling half (paying half of a 0.2% fee). **Sair** means selling all (paying the 0.2% fee). They hit when following the verdict returned more than holding.
- **Manter** hits when holding returned at least as much as BTC, minus the 0.2% fee.
- Manter on BTC is left out of the rates, because BTC is its own reference and it would always hit.

## Changing a signal

Add the threshold to `[thresholds]` in `config.toml` and to `Thresholds` in `config.py`, change the function in `rubric.py`, and test the exact limits in `tests/test_rubric.py`. If the dashboard shows the signal, update `frontend/src/lib/types.ts` too.
