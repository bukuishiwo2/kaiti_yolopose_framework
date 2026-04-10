PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: help setup install-editable infer build-seq train-seq eval-rule eval-seq tune-seq clean clean-local

help:
	@echo "Targets:"
	@echo "  setup            Install runtime requirements into .venv"
	@echo "  install-editable Install the src package in editable mode"
	@echo "  infer            Run pose inference with the default config"
	@echo "  build-seq        Build the sequence dataset from UR Fall labels"
	@echo "  train-seq        Train the LSTM fall classifier"
	@echo "  eval-rule        Evaluate the rule-based detector on UR Fall"
	@echo "  eval-seq         Evaluate the sequence detector on UR Fall"
	@echo "  tune-seq         Grid-search sequence detector thresholds/stabilization"
	@echo "  clean            Remove runtime outputs and caches"
	@echo "  clean-local      Remove large local-only artifacts before publishing"

setup:
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

install-editable:
	$(PIP) install -e . --no-deps

infer:
	$(PYTHON) scripts/run_pose_infer.py --config configs/infer_pose_stream.yaml

build-seq:
	$(PYTHON) scripts/build_pose_sequence_dataset.py \
		--labels data/eval/video_labels_urfall_cam0.csv \
		--device 0 \
		--output data/processed/urfall_pose_sequences.npz

train-seq:
	$(PYTHON) scripts/run_fall_sequence_train.py --config configs/train_fall_sequence.yaml

eval-rule:
	$(PYTHON) scripts/eval_fall_batch.py \
		--labels data/eval/video_labels_urfall_cam0.csv \
		--config configs/infer_pose_stream.yaml \
		--mode predict \
		--device 0 \
		--out-dir outputs/eval_urfall

eval-seq:
	$(PYTHON) scripts/eval_fall_batch.py \
		--labels data/eval/video_labels_urfall_cam0.csv \
		--config configs/infer_pose_stream.yaml \
		--mode predict \
		--device 0 \
		--raw-key seq_raw_fall_detected \
		--stable-key seq_stable_fall_detected \
		--out-dir outputs/eval_urfall_sequence

tune-seq:
	$(PYTHON) scripts/tune_fall_grid.py \
		--labels data/eval/video_labels_urfall_cam0.csv \
		--base-config configs/infer_pose_stream.yaml \
		--grid data/eval/fall_grid_sequence.yaml \
		--target-detector sequence_fall_detector \
		--mode predict \
		--device 0 \
		--raw-key seq_raw_fall_detected \
		--stable-key seq_stable_fall_detected \
		--out-dir outputs/tune_fall_grid_sequence

clean:
	bash scripts/clean_outputs.sh

clean-local:
	bash scripts/clean_local_artifacts.sh
