"""Test script for FlashFrameDetectorV3."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

from core.frame_scanner import FrameScanner
from core.flash_frame_v3 import FlashFrameDetectorV3, DetectionConfig

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

    # Run v3 detector
    cfg = DetectionConfig()
    detector = FlashFrameDetectorV3(cfg)
    result = detector.detect_from_thumbs(thumbs, fps=fps)

    # Print results
    print(f"Has flash frames: {result['has_flash_frames']}")
    print(f"Candidates: {len(result['candidates'])}")

    for i, cand in enumerate(result['candidates']):
        print(f"\n  Detection {i+1}:")
        print(f"    Type: {cand['detection_type']}")
        print(f"    Frames: {cand['start_frame']} ~ {cand['end_frame']} (span: {cand['span_frames']})")
        print(f"    Timestamp: {cand['start_time']:.2f}s")
        print(f"    Mutation Value: {cand['mutation_value']:.3f}")
