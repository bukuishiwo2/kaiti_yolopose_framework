# TCN Positioning

## What TCN Is Here

In this project, `TCN` is not the default main detector.
It is a conservative sequence-model branch used to compare against the current `LSTM` baseline.

## Current Empirical Position

On `UR Fall`, the current `TCN` result shows:
- very high precision
- noticeably lower recall than `LSTM`
- much fewer ADL false alarms than `LSTM`

That makes it a good candidate when the operating point prioritizes false-alarm suppression.

## Why It Is Not the Main Model Yet

The main model is still `LSTM` because it currently offers:
- better overall F1
- better fall recall
- fewer missed fall segments

`TCN` is therefore kept as:
- a low-false-alarm alternative
- a comparison baseline
- a target for narrow threshold refinement

## Practical Use

Recommended use cases for `TCN`:
- compare conservative detection behavior
- test whether false alarms can be reduced further by threshold tuning
- keep as a candidate when false alarms are more expensive than misses

Recommended non-use:
- do not replace the default LSTM branch unless the TCN refinement closes the recall gap

