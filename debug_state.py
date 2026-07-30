"""Debug script to trace state machine transitions."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

import numpy as np
from core.frame_scanner import FrameScanner
from core.flash_frame_v2.detector import FlashFrameDetectorV2
from core.flash_frame_v2.config import DetectionConfig
from core.flash_frame_v2.state_manager import TemporalStateManager
from core.flash_frame_v2.similarity import SimilarityEngine
from core.flash_frame_v2.gradient import TemporalGradientAnalyzer
from core.flash_frame_v2.candidate import CandidateDetector
from core.flash_frame_v2.preprocessor import FramePreprocessor
from core.flash_frame_v2.structures import FrameFeature

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

# Preprocess all thumbs
processed = []
for frame_num, gray in thumbs:
    if gray.shape == (cfg.thumb_height, cfg.thumb_width):
        f_i = gray
    else:
        bgr = np.stack([gray, gray, gray], axis=-1) if len(gray.shape) == 2 else gray
        f_i = preprocessor.process(bgr)
    processed.append((frame_num, f_i))

# Run detector with state tracing
prev = None
state_changes = []
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

    if old_state != new_state:
        state_changes.append((frame_num, old_state, new_state, feature.anomaly_score, feature.is_spike))

    if candidate is not None:
        print(f"\n  Candidate found at frame {frame_num}:")
        print(f"    Type: {candidate.detection_type}")
        print(f"    Span: {candidate.span}")
        print(f"    Recovery: {candidate.recovery_score:.3f}")

    prev = f_i

print(f"\nState transitions: {len(state_changes)}")
for frame_num, old_state, new_state, anomaly, spike in state_changes[:20]:
    print(f"  Frame {frame_num}: {old_state} -> {new_state} (anomaly={anomaly:.3f}, spike={spike})")
if len(state_changes) > 20:
    print(f"  ... and {len(state_changes) - 20} more")
