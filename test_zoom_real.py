"""Test mutation value for 1.05x scaled frame using real video."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

import cv2
import numpy as np
from core.flash_frame_v3 import FlashFrameDetectorV3, DetectionConfig

# Load a real video frame
video_path = r"C:\Users\JW TSJ\Desktop\666\跳帧.mp4"
cap = cv2.VideoCapture(video_path)
cap.set(cv2.CAP_PROP_POS_FRAMES, 100)  # Get frame 100
ret, frame = cap.read()
cap.release()

if not ret:
    print("Failed to read video frame")
    sys.exit(1)

# Convert to grayscale and resize to standard size
img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
img = cv2.resize(img, (160, 90))

# Create scaled version (1.05x zoom)
h, w = img.shape
scale = 1.05
scaled = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)

# Crop back to original size (center crop)
sh, sw = scaled.shape
y_offset = (sh - h) // 2
x_offset = (sw - w) // 2
scaled_cropped = scaled[y_offset:y_offset+h, x_offset:x_offset+w]

# Create detector
cfg = DetectionConfig()
detector = FlashFrameDetectorV3(cfg)

# Calculate mutation values
mutation_scaled = detector._compute_mutation_value(img, scaled_cropped)

# Calculate individual metrics
ssim_scaled = detector._compute_ssim(img, scaled_cropped)
block_ssim_scaled = detector._compute_block_ssim(img, scaled_cropped)
ncc_scaled = detector._compute_ncc(img, scaled_cropped)

print("="*60)
print("Real Video Test: 1.05x Scaled Frame")
print("="*60)

print("\n[Normal vs 1.05x Scaled]")
print(f"  SSIM:       {ssim_scaled:.4f}  (dissimilarity: {1-ssim_scaled:.4f})")
print(f"  Block SSIM: {block_ssim_scaled:.4f}  (dissimilarity: {1-block_ssim_scaled:.4f})")
print(f"  NCC:        {ncc_scaled:.4f}  (dissimilarity: {1-ncc_scaled:.4f})")
print(f"  Mutation:   {mutation_scaled:.4f}")

print("\n[Thresholds]")
print(f"  Threshold A (candidate): {cfg.threshold_a}")
print(f"  Threshold B (confirm):   {cfg.threshold_b}")

if mutation_scaled >= cfg.threshold_a:
    print(f"\n[OK] Mutation {mutation_scaled:.3f} >= {cfg.threshold_a}, WILL be detected")
else:
    print(f"\n[NO] Mutation {mutation_scaled:.3f} < {cfg.threshold_a}, will NOT be detected")

# Test different zoom levels
print("\n[Different Zoom Levels]")
for scale_factor in [1.01, 1.02, 1.03, 1.05, 1.10]:
    scaled_test = cv2.resize(img, (int(w * scale_factor), int(h * scale_factor)), interpolation=cv2.INTER_LINEAR)
    sh, sw = scaled_test.shape
    y_off = (sh - h) // 2
    x_off = (sw - w) // 2
    scaled_crop = scaled_test[y_off:y_off+h, x_off:x_off+w]
    
    mut = detector._compute_mutation_value(img, scaled_crop)
    detected = "YES" if mut >= cfg.threshold_a else "NO"
    print(f"  {scale_factor:.2f}x: mutation={mut:.3f} [{detected}]")
