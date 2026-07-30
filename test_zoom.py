"""Test mutation value for 1.05x scaled frame."""
import sys
sys.path.insert(0, r"D:\Project\MediaSync-QC-Studio")

import cv2
import numpy as np
from core.flash_frame_v3 import FlashFrameDetectorV3, DetectionConfig

# Create a test image
np.random.seed(42)
img = np.random.randint(50, 200, (90, 160), dtype=np.uint8)

# Add some structure (edges, gradients)
img[20:40, 30:80] = 220  # bright rectangle
img[50:70, 100:140] = 30  # dark rectangle
img[:, :] += np.linspace(0, 30, 160).astype(np.uint8)  # horizontal gradient

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
mutation_normal = detector._compute_mutation_value(img, img)
mutation_scaled = detector._compute_mutation_value(img, scaled_cropped)

# Calculate individual metrics
ssim_normal = detector._compute_ssim(img, img)
ssim_scaled = detector._compute_ssim(img, scaled_cropped)

block_ssim_normal = detector._compute_block_ssim(img, img)
block_ssim_scaled = detector._compute_block_ssim(img, scaled_cropped)

ncc_normal = detector._compute_ncc(img, img)
ncc_scaled = detector._compute_ncc(img, scaled_cropped)

print("="*60)
print("测试：1.05倍缩放帧的突变值")
print("="*60)

print("\n【正常帧 vs 自身】")
print(f"  SSIM:       {ssim_normal:.4f}")
print(f"  Block SSIM: {block_ssim_normal:.4f}")
print(f"  NCC:        {ncc_normal:.4f}")
print(f"  突变值:     {mutation_normal:.4f}")

print("\n【正常帧 vs 1.05倍缩放帧】")
print(f"  SSIM:       {ssim_scaled:.4f}  (不相似度: {1-ssim_scaled:.4f})")
print(f"  Block SSIM: {block_ssim_scaled:.4f}  (不相似度: {1-block_ssim_scaled:.4f})")
print(f"  NCC:        {ncc_scaled:.4f}  (不相似度: {1-ncc_scaled:.4f})")
print(f"  突变值:     {mutation_scaled:.4f}")

print("\n【判定结果】")
print(f"  阈值 A (候选): {cfg.threshold_a}")
print(f"  阈值 B (确认): {cfg.threshold_b}")

if mutation_scaled >= cfg.threshold_a:
    print(f"  [OK] 突变值 {mutation_scaled:.3f} >= {cfg.threshold_a}，会触发候选检测")
else:
    print(f"  [NO] 突变值 {mutation_scaled:.3f} < {cfg.threshold_a}，不会触发候选检测")

print("\n【结论】")
if mutation_scaled < cfg.threshold_a:
    print("  1.05倍缩放的帧不会被检测为异常，突变值过低。")
    print(f"  需要至少 {cfg.threshold_a / mutation_scaled:.2f} 倍的缩放才能达到阈值。")
else:
    print("  1.05倍缩放的帧会被检测为异常。")
