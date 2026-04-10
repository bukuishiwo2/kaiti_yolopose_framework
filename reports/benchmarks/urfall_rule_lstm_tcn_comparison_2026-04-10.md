# UR Fall Rule / LSTM / TCN Comparison (2026-04-10)

## Scope

This note records the current same-metric comparison among three detectors on `UR Fall`:
- Rule-based baseline
- Sequence LSTM
- Sequence TCN

The comparison uses the stable frame-level metrics exported by `scripts/eval_fall_batch.py` and the corresponding output summaries stored under `outputs/`.

## 1. Rule-Based Baseline

Evaluation directory:
- `outputs/eval_urfall/`

Stable result:
- Precision: `0.7558`
- Recall: `0.4196`
- F1: `0.5396`

Interpretation:
- Reasonable precision
- Low recall
- Strongly conservative for fall detection, but too many missed fall frames

## 2. Sequence LSTM

Evaluation directory:
- `outputs/eval_urfall_sequence/`

Stable result:
- Precision: `0.7769`
- Recall: `0.8000`
- F1: `0.7883`

Interpretation:
- Best overall balance among the three current baselines
- Recall is substantially better than the rule-based detector
- Still has notable ADL false alarms, which motivated threshold/stability tuning

## 3. Sequence TCN

Evaluation directory:
- `outputs/eval_urfall_sequence_tcn/`

Stable result:
- Precision: `0.8990`
- Recall: `0.5882`
- F1: `0.7111`

Interpretation:
- Much lower false-alarm tendency than the current LSTM
- But recall drops significantly
- This makes TCN a conservative candidate rather than the current main model

## 4. Same-Metric Comparison

| Method | Precision | Recall | F1 |
|---|---:|---:|---:|
| Rule baseline | 0.7558 | 0.4196 | 0.5396 |
| Sequence LSTM | 0.7769 | 0.8000 | 0.7883 |
| Sequence TCN | 0.8990 | 0.5882 | 0.7111 |

Increment vs rule baseline:
- LSTM: `+0.0211` precision, `+0.3804` recall, `+0.2487` F1
- TCN: `+0.1432` precision, `+0.1686` recall, `+0.1715` F1

Increment vs LSTM:
- TCN gains precision `+0.1221`
- TCN loses recall `-0.2118`
- TCN loses F1 `-0.0772`

## 5. Segment-Level Observation

Rule-based detector:
- `fall_fn_segments = 4`
- `adl_fp_segments = 10`
- average detection delay: about `1.019s`

Sequence LSTM:
- `fall_fn_segments = 0`
- `adl_fp_segments = 21`
- average detection delay: about `0.377s`

Sequence TCN:
- `fall_fn_segments = 1`
- `adl_fp_segments = 4`
- average detection delay: about `0.806s`

Interpretation:
- TCN is the strongest at suppressing ADL false alarms
- LSTM is still the best at not missing fall segments
- Rule-based baseline remains the weakest overall, but is still a useful reference

## 6. Current Decision

Current model positioning:
- `LSTM`: default main learning-based baseline
- `TCN`: low-false-alarm candidate, not the main model
- Rule-based detector: baseline / comparison only

This means TCN should be used as:
- a conservative comparison branch
- a candidate for low-false-alarm scenarios
- a target for threshold refinement, not an immediate replacement for LSTM

## 7. Follow-up Direction

Recommended next steps:
1. Keep the current LSTM configuration as the main learning baseline.
2. Keep TCN as a low-false-alarm branch and tune it separately from the LSTM main path.
3. If TCN remains conservative after refinement, keep it as a secondary model and move the main research effort to data augmentation and negative-sample hardening.

## 8. TCN Coarse Sweep Result

Completed tuning directory:
- `outputs/tune_fall_grid_sequence_tcn/`

Best coarse-sweep configuration:
- `combo_id = c015`
- `score_threshold = 0.4`
- `min_true_frames = 3`
- `min_false_frames = 7`

Best result from the coarse sweep:
- Precision: `0.8828`
- Recall: `0.6286`
- F1: `0.7343`
- `fall_fn_segments = 1`
- `adl_fp_segments = 4`
- `adl_false_alarm_per_min = 0.577`

Change vs untuned TCN:
- Precision: `0.8990 -> 0.8828`
- Recall: `0.5882 -> 0.6286`
- F1: `0.7111 -> 0.7343`

Interpretation:
- Lowering the TCN threshold recovered part of recall without changing its overall conservative character.
- TCN remains clearly below LSTM on overall F1.
- TCN remains useful as a low-false-alarm branch, not as the default main model.

Current repository decision:
- Keep `LSTM` as the default learning-based model.
- Track the current TCN best config in `configs/infer_pose_stream_tcn.yaml`.
- Use tuned TCN for conservative-mode experiments and future narrow refinement only.
