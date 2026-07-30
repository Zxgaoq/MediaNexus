"""Test the UI output format for flash frame results."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

from core.frame_scanner import FrameScanner
from core.flash_frame_v3 import FlashFrameDetectorV3, DetectionConfig

# Test video
video_path = r"C:\Users\JW TSJ\Desktop\666\跳帧.mp4"

print(f"Testing: {video_path}")
print("="*60)

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

# Simulate UI output
print("\n### Flash Frame Detection")
ff = result
if ff.get("candidates"):
    for cand in ff["candidates"][:10]:  # Show first 10
        cand_type = cand.get("type", "flash")
        span = cand.get("span_frames", 1)
        time_str = cand.get("time_str", "")
        line = (f"- Frame {cand.get('start_frame', '?')}~{cand.get('end_frame', '?')} "
                f"({span} frames) {time_str} "
                f"[{cand_type}]")
        print(line)
else:
    print("### Flash Frame Detection: Not found")
