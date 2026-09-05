from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root and use-scripts to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
USE_SCRIPTS_DIR = PROJECT_ROOT / 'use-scripts'
if str(USE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(USE_SCRIPTS_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np
import tifffile
import torch
import segmentation_models_pytorch as smp

from train_classifier import build_classifier
from evaluate_part3 import (
    load_model,
    predict_full_scene_wholescene,
    predict_full_scene,
    _classify_scene,
    percentile_normalize,
)


def run_cascade_inference(
    image_path: str,
    classifier_ckpt_path: str,
    segmenter_ckpt_path: str,
    output_dir: str | None = None,
    classify_threshold: float = 0.5,
    segment_threshold: float = 0.5,
    decoder_width: str = 'wide',
    decoder_attention: str = 'none',
    despeckle: bool = False,
    device_str: str | None = None,
):
    image_file = Path(image_path)
    if not image_file.exists():
        raise FileNotFoundError(f'Image not found: {image_path}')

    if device_str:
        device = torch.device(device_str)
    else:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'[Device] Running inference on: {device.type.upper()}')

    print(f'\n--- [Stage 1: Classification] ---')
    print(f'Loading classifier checkpoint: {classifier_ckpt_path}')
    classifier = build_classifier().to(device)
    c_ckpt = torch.load(classifier_ckpt_path, map_location=device)
    classifier.load_state_dict(c_ckpt['model_state_dict'])
    classifier.eval()
    recall_val = c_ckpt.get('recall', 0.0)
    prec_val = c_ckpt.get('precision', 0.0)
    print(f'Classifier ready (trained recall: {recall_val:.4f}, precision: {prec_val:.4f})')

    print(f'Reading SAR scene: {image_path}')
    raw_scene = tifffile.imread(image_path)
    h, w = raw_scene.shape[:2]
    channels = raw_scene.shape[2] if raw_scene.ndim == 3 else 1
    print(f'Scene shape: {h}x{w}, channels: {channels}')

    prob_oil = _classify_scene(classifier, str(image_file), device)
    oil_detected = prob_oil >= classify_threshold

    print(f'Stage 1 Oil Presence Probability: {prob_oil:.4f} (Cutoff Threshold: {classify_threshold:.2f})')
    if oil_detected:
        print(f'>> STATUS: OIL DETECTED. Proceeding to Stage 2 segmentation...')
    else:
        print(f'>> STATUS: NO OIL DETECTED. Gate closed (skipping Stage 2 to prevent false alarms).')

    # Stage 2: Segmentation
    if oil_detected:
        print(f'\n--- [Stage 2: Whole-Scene Segmentation] ---')
        print(f'Loading segmenter checkpoint: {segmenter_ckpt_path}')
        segmenter, ckpt_mode = load_model(
            segmenter_ckpt_path, device, decoder_width=decoder_width, decoder_attention=decoder_attention
        )
        print(f'Segmenter model loaded (input_mode: {ckpt_mode}, decoder: {decoder_width})')

        print(f'Running full-scene TTA inference...')
        if ckpt_mode == 'whole_scene':
            prob_map = predict_full_scene_wholescene(segmenter, str(image_file), device, despeckle=despeckle)
        else:
            prob_map = predict_full_scene(segmenter, str(image_file), device)

        max_prob = float(np.max(prob_map))
        min_prob = float(np.min(prob_map))
        oil_pixel_count = int((prob_map >= segment_threshold).sum())
        total_pixels = h * w
        slick_coverage_pct = (oil_pixel_count / total_pixels) * 100.0

        print(f'Segmentation complete.')
        print(f'Probability range: min={min_prob:.4f}, max={max_prob:.4f}')
        print(f'Oil pixels >= {segment_threshold:.2f}: {oil_pixel_count:,} ({slick_coverage_pct:.3f}% of scene)')
    else:
        prob_map = np.zeros((h, w), dtype=np.float32)
        oil_pixel_count = 0
        slick_coverage_pct = 0.0
        max_prob = 0.0

    # Save outputs
    out_target_dir = Path(output_dir) if output_dir else image_file.parent
    out_target_dir.mkdir(parents=True, exist_ok=True)
    stem = image_file.stem

    npy_out = out_target_dir / f'{stem}_prob_mask.npy'
    png_out = out_target_dir / f'{stem}_cascade_result.png'

    np.save(npy_out, prob_map)
    print(f'\n[Artifacts Saved]')
    print(f'Probability array (.npy): {npy_out}')

    # Create visualization
    norm_scene = percentile_normalize(raw_scene)
    if norm_scene.ndim == 3:
        sar_gray = (norm_scene[:, :, 0] * 255.0).clip(0, 255).astype(np.uint8)
    else:
        sar_gray = (norm_scene * 255.0).clip(0, 255).astype(np.uint8)

    vis_bgr = cv2.cvtColor(sar_gray, cv2.COLOR_GRAY2BGR)

    if oil_detected and oil_pixel_count > 0:
        # Create colored overlay for segmented oil slick
        mask_binary = (prob_map >= segment_threshold).astype(np.uint8)
        color_mask = np.zeros_like(vis_bgr)
        # Saturated red/orange overlay for oil
        color_mask[:, :, 2] = (prob_map * 255).clip(0, 255).astype(np.uint8)  # Red channel
        color_mask[:, :, 1] = ((1.0 - prob_map) * 70).clip(0, 70).astype(np.uint8)  # Orange tint
        color_mask[:, :, 0] = 0

        # Alpha blend over SAR
        alpha = 0.55
        vis_bgr = np.where(mask_binary[:, :, None] == 1,
                           cv2.addWeighted(vis_bgr, 1.0 - alpha, color_mask, alpha, 0),
                           vis_bgr)

        # Draw slick contours
        contours, _ = cv2.findContours(mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis_bgr, contours, -1, (0, 165, 255), 2)  # Amber contour line

    # Add header banner with diagnostics
    banner = np.zeros((100, vis_bgr.shape[1], 3), dtype=np.uint8)
    status_text = f'OIL DETECTED (P={prob_oil:.2%})' if oil_detected else f'NO OIL DETECTED (P={prob_oil:.2%})'
    status_color = (0, 69, 255) if oil_detected else (0, 200, 0)

    cv2.putText(banner, f'OilTrace SAR Cascade Inference Demo | Scene: {image_file.name}', (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 220, 220), 2)
    cv2.putText(banner, f'Gate Decision: {status_text}', (20, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, status_color, 2)
    cv2.putText(banner, f'Pixels > {segment_threshold:.2f}: {oil_pixel_count:,} ({slick_coverage_pct:.3f}%)',
                (vis_bgr.shape[1] - 420, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2)

    final_vis = np.vstack([banner, vis_bgr])
    cv2.imwrite(str(png_out), final_vis)
    print(f'Visualization image (.png): {png_out}')
    print('\nCascade execution finished successfully.')

    return {
        'oil_detected': oil_detected,
        'classifier_prob': prob_oil,
        'max_segment_prob': max_prob,
        'oil_pixels': oil_pixel_count,
        'npy_path': str(npy_out),
        'png_path': str(png_out),
    }


def main():
    parser = argparse.ArgumentParser(description='OilTrace Two-Stage SAR Cascade Inference Demo')
    parser.add_argument('--image', required=True, help='Path to input Sentinel-1 SAR TIFF file')
    parser.add_argument('--classifier-checkpoint', default='checkpoints/classifier_best.pt',
                        help='Path to trained classifier checkpoint (.pt)')
    parser.add_argument('--segmenter-checkpoint', default='checkpoints/unet_wholescene_best.pt',
                        help='Path to trained segmenter checkpoint (.pt)')
    parser.add_argument('--classify-threshold', type=float, default=0.5,
                        help='Threshold above which to trigger segmenter (default: 0.5)')
    parser.add_argument('--segment-threshold', type=float, default=0.5,
                        help='Threshold for binarizing oil probability mask (default: 0.5)')
    parser.add_argument('--decoder-width', default='wide', choices=['default', 'wide'],
                        help='Decoder width preset (shipped whole-scene model uses "wide")')
    parser.add_argument('--decoder-attention', default='none', choices=['none', 'scse'],
                        help='Decoder attention type (shipped model uses "none")')
    parser.add_argument('--despeckle', action='store_true',
                        help='Apply Lee despeckling filter')
    parser.add_argument('--output-dir', default=None,
                        help='Directory where output .npy and .png will be saved')
    parser.add_argument('--device', default=None, choices=['cpu', 'cuda'],
                        help='Compute device to run on (defaults to cuda if available, else cpu)')

    args = parser.parse_args()
    run_cascade_inference(
        image_path=args.image,
        classifier_ckpt_path=args.classifier_checkpoint,
        segmenter_ckpt_path=args.segmenter_checkpoint,
        output_dir=args.output_dir,
        classify_threshold=args.classify_threshold,
        segment_threshold=args.segment_threshold,
        decoder_width=args.decoder_width,
        decoder_attention=args.decoder_attention,
        despeckle=args.despeckle,
        device_str=args.device,
    )


if __name__ == '__main__':
    main()
