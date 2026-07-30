"""Debug script to trace SEARCH and RECOVERY states."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

import numpy as np
from core.frame_scanner import FrameScanner
from core.flash_frame_v2.detector import FlashFrameDetectorV2
from core.flash_frame_v2.config import DetectionConfig
from core.flash_frame_v2.state_manager import TemporalStateManager
from core.flash_frame_v2.similarity import SimilarityEngine, compute_ssim
from core.flash_frame_v2.gradient import TemporalGradientAnalyzer
from core.flash_frame_v2.candidate import CandidateDetector
from core.flash_frame_v2.preprocessor import FramePreprocessor
from core.flash_frame_v2.structures import FrameFeature, State

video_path = r"C:\Users\JW TSJ\Desktop\666\跳帧.mp4"
print(f"Testing: {video_path}")

scanner = FrameScanner(video_path)
scanner.scan()
thumbs = scanner.thumbs
fps = scanner.fps

cfg = DetectionConfig()
preprocessor = FramePreprocessor(cfg)
sim_engine = SimilarityEngine(cfg)
gradient = TemporalGradientAnalyzer(cfg)
candidate_det = CandidateDetector(cfg)
state_mgr = TemporalStateManager(cfg, fps=fps)

print(f"W_max = {state_mgr._max_search} frames")
print(f"recovery_ssim_threshold = {cfg.recovery_ssim_threshold}")
print(f"memory_recover_threshold = {cfg.memory_recover_threshold}")

# Preprocess all thumbs
processed = []
for frame_num, gray in thumbs:
    if gray.shape == (cfg.thumb_height, cfg.thumb_width):
        f_i = gray
    else:
        bgr = np.stack([gray, gray, gray], axis=-1) if len(gray.shape) == 2 else gray
        f_i = preprocessor.process(bgr)
    processed.append((frame_num, f_i))

# Run detector with detailed tracing
prev = None
in_search = False
search_start = None
for frame_num, f_i in processed:
    if prev is None:
        prev = f_i
        continue

    sim = sim_engine.compute(prev, f_i)
    diff = 1.0 - sim['ssim']
    grad = gradient.update(diff)

    feature = FrameFeature(
        frame_index=frame_num,
        ssim=sim['ssim'],
        hist_corr=sim['hist_corr'],
        ncc=sim['ncc'],
        edge_diff=sim['edge_diff'],
        gradient_diff=sim['gradient_diff'],
        block_ssim_mean=sim['block_ssim_mean'],
        block_ssim_drops=sim['block_ssim_drops'],
        block_ssim_values=sim['block_ssim_values'],
        diff=diff,
        first_derivative=grad['first_derivative'],
        curvature=grad['curvature'],
        curvature_threshold=grad['curvature_threshold'],
        is_spike=grad['is_spike'],
    )
    feature.anomaly_score = candidate_det.compute_anomaly_score(feature)
    feature.is_candidate = candidate_det.evaluate(feature)

    old_state = state_mgr.state
    candidate = state_mgr.feed(frame_num, f_i, feature)
    new_state = state_mgr.state

    # Trace SEARCH state
    if new_state == State.SEARCH and old_state != State.SEARCH:
        in_search = True
        search_start = frame_num
        print(f"\n  SEARCH started at frame {frame_num} (anomaly={feature.anomaly_score:.3f}, spike={feature.is_spike})")
        print(f"    start_frame_data shape: {state_mgr.start_frame_data.shape if state_mgr.start_frame_data is not None else None}")
        print(f"    memory size: {state_mgr.memory.size}")

    if in_search and new_state == State.SEARCH:
        # Compute recovery metrics
        if state_mgr.start_frame_data is not None:
            ssim_to_start = compute_ssim(
                state_mgr.start_frame_data, f_i,
                cfg.ssim_window, cfg.ssim_sigma, cfg.ssim_c1, cfg.ssim_c2
            )
            ssim_to_memory = state_mgr.memory.query_similarity(f_i)
            print(f"    Frame {frame_num}: ssim_to_start={ssim_to_start:.3f}, ssim_to_memory={ssim_to_memory:.3f}, "
                  f"curve_len={len(state_mgr.curve_buffer.values)}")

    if in_search and new_state != State.SEARCH:
        in_search = False
        print(f"  SEARCH ended at frame {frame_num} -> {new_state}")
        if state_mgr.replay_from is not None:
            print(f"    replay_from = {state_mgr.replay_from}")

    if candidate is not None:
        print(f"\n  *** CANDIDATE FOUND at frame {frame_num}:")
        print(f"    Type: {candidate.detection_type}")
        print(f"    Span: {candidate.span}")
        print(f"    Recovery: {candidate.recovery_score:.3f}")

    prev = f_i

    # Stop after first few SEARCH events to avoid too much output
    if frame_num > 700:
        break
