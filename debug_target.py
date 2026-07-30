"""Debug script to trace state machine at specific frames."""
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
target_frames = [574, 661, 1261]

print(f"Testing: {video_path}")
print(f"Target frames: {target_frames}")

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

# Preprocess all thumbs
processed = []
for frame_num, gray in thumbs:
    if gray.shape == (cfg.thumb_height, cfg.thumb_width):
        f_i = gray
    else:
        bgr = np.stack([gray, gray, gray], axis=-1) if len(gray.shape) == 2 else gray
        f_i = preprocessor.process(bgr)
    processed.append((frame_num, f_i))

# Run detector with detailed tracing around target frames
prev = None
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

    # Check if we're near a target frame
    near_target = any(abs(frame_num - tf) <= 3 for tf in target_frames)

    old_state = state_mgr.state
    candidate = state_mgr.feed(frame_num, f_i, feature)
    new_state = state_mgr.state

    if near_target or (old_state != new_state and frame_num > 550 and frame_num < 1300):
        print(f"Frame {frame_num}: state={old_state}->{new_state}, anomaly={feature.anomaly_score:.3f}, "
              f"spike={feature.is_spike}, candidate={feature.is_candidate}")

        if new_state == State.SEARCH and old_state != State.SEARCH:
            print(f"  -> Entered SEARCH at frame {frame_num}")
            print(f"     start_frame={state_mgr.start_frame_idx}")
            print(f"     memory size={state_mgr.memory.size}")

        if new_state == State.RECOVERY and old_state != State.RECOVERY:
            print(f"  -> Entered RECOVERY at frame {frame_num}")
            print(f"     recovery_frame={state_mgr.recovery_frame_idx}")

        if new_state == State.VERIFY and old_state != State.VERIFY:
            print(f"  -> Entered VERIFY at frame {frame_num}")

        if new_state == State.NORMAL and old_state != State.NORMAL:
            print(f"  -> Returned to NORMAL at frame {frame_num}")
            if state_mgr.replay_from is not None:
                print(f"     replay_from={state_mgr.replay_from}")

    if candidate is not None:
        print(f"\n  *** CANDIDATE OUTPUT at frame {frame_num}:")
        print(f"      Type: {candidate.detection_type}")
        print(f"      Span: {candidate.span}")
        print(f"      Recovery: {candidate.recovery_score:.3f}")
        print()

    prev = f_i
