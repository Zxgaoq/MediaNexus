"""Dump per-frame anomaly scores for known event positions."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

import numpy as np
from core.frame_scanner import FrameScanner
from core.flash_frame_v2.detector import FlashFrameDetectorV2
from core.flash_frame_v2.config import DetectionConfig
from core.flash_frame_v2.similarity import SimilarityEngine
from core.flash_frame_v2.gradient import TemporalGradientAnalyzer
from core.flash_frame_v2.candidate import CandidateDetector
from core.flash_frame_v2.preprocessor import FramePreprocessor

# Known events from old logs
KNOWN_EVENTS = {
    r"C:\Users\JW TSJ\Desktop\666\跳帧.mp4": [534, 574, 661, 1261],
    r"C:\Users\JW TSJ\Desktop\666\00000000.mp4": [2157],
}

for video_path, event_frames in KNOWN_EVENTS.items():
    print(f"\n{'='*60}")
    print(f"Video: {video_path}")
    print(f"Known events: {event_frames}")
    print(f"{'='*60}")

    scanner = FrameScanner(video_path)
    scanner.scan()
    thumbs = scanner.thumbs
    fps = scanner.fps

    cfg = DetectionConfig()
    preprocessor = FramePreprocessor(cfg)
    sim_engine = SimilarityEngine(cfg)
    gradient = TemporalGradientAnalyzer(cfg)
    candidate_det = CandidateDetector(cfg)

    # Preprocess all thumbs
    processed = []
    for frame_num, gray in thumbs:
        if gray.shape == (cfg.thumb_height, cfg.thumb_width):
            f_i = gray
        else:
            bgr = np.stack([gray, gray, gray], axis=-1) if len(gray.shape) == 2 else gray
            f_i = preprocessor.process(bgr)
        processed.append((frame_num, f_i))

    # Compute per-frame metrics
    prev = None
    frame_data = {}
    for frame_num, f_i in processed:
        if prev is None:
            prev = f_i
            continue
        sim = sim_engine.compute(prev, f_i)
        diff = 1.0 - sim['ssim']
        grad = gradient.update(diff)

        from core.flash_frame_v2.structures import FrameFeature
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

        frame_data[frame_num] = {
            'ssim': sim['ssim'],
            'anomaly': feature.anomaly_score,
            'curvature': grad['curvature'],
            'curvature_threshold': grad['curvature_threshold'],
            'spike': grad['is_spike'],
            'candidate': feature.is_candidate,
        }
        prev = f_i

    # Print around known events
    for ef in event_frames:
        print(f"\n  --- Event at frame {ef} ---")
        for f in range(max(1, ef-5), ef+6):
            if f in frame_data:
                d = frame_data[f]
                marker = " <-- KNOWN" if f == ef else ""
                print(f"    Frame {f}: ssim={d['ssim']:.3f} anomaly={d['anomaly']:.3f} "
                      f"curv={d['curvature']:.3f} th={d['curvature_threshold']:.3f} "
                      f"spike={d['spike']} cand={d['candidate']}{marker}")
