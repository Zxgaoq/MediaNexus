"""Quick verification script for v1.2 flash frame detector."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

from core.frame_scanner import FrameScanner
from core.flash_frame_v2.detector import FlashFrameDetectorV2
from core.flash_frame_v2.config import DetectionConfig

# Test videos
test_videos = [
    r"C:\Users\JW TSJ\Desktop\666\跳帧.mp4",
    r"C:\Users\JW TSJ\Desktop\666\00000000.mp4",
]

for video_path in test_videos:
    print(f"\n{'='*60}")
    print(f"Testing: {video_path}")
    print(f"{'='*60}")

    # Scan frames
    scanner = FrameScanner(video_path)
    scanner.scan()
    thumbs = scanner.thumbs
    fps = scanner.fps

    print(f"Frames: {len(thumbs)}, FPS: {fps:.1f}")

    # Run v2 detector
    cfg = DetectionConfig()
    detector = FlashFrameDetectorV2(cfg)
    result = detector.detect_from_thumbs(thumbs, fps=fps)

    # Print results
    print(f"Has flash frames: {result['has_flash_frames']}")
    print(f"Candidates: {len(result['candidates'])}")

    for i, cand in enumerate(result['candidates']):
        print(f"\n  Candidate {i+1}:")
        print(f"    Type: {cand['detection_type']}")
        print(f"    Frames: {cand['start_frame']} ~ {cand['end_frame']} (span: {cand['span_frames']})")
        print(f"    Confidence: {cand['confidence']:.1f}% ({cand['confidence_level']})")
        print(f"    Anomaly Score: {cand['anomaly_score']:.3f}")
        print(f"    Recovery Score: {cand['recovery_score']:.3f}")
        print(f"    Min SSIM: {cand['min_ssim']:.3f}")
        print(f"    Max Curvature: {cand['max_curvature']:.3f}")
