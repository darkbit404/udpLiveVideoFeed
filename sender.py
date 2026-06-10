#!/usr/bin/env python3
"""
Jetson Orin NX - Zero-Copy Hardware Encoded UDP Video Streaming (RTP)
Camera: Arducam OV2311 (MIPI CSI, Monochrome Global Shutter)
Encoder: NVIDIA NVENC H.264
Transport: RTP over UDP (zero-copy)

NOTE: OV2311 is a monochrome (grayscale) global shutter sensor.
It bypasses the Argus ISP — v4l2src with GRAY8 format is used instead
of nvarguscamerasrc. A videoconvert step converts GRAY8 → NV12 before
passing to the hardware encoder.

Uses gst-launch-1.0 subprocess execution to avoid encoder driver crashes.
"""

import os
import sys
import subprocess
import time
import signal

# ================= CONFIG =================

RECEIVER_IP = "10.42.0.218"   # Receiver laptop IP
RECEIVER_PORT = 5000

# Camera settings
# OV2311 native resolution: 1600x1300 @ up to 60fps
# Also supports: 1600x1080 @ 80fps, 1280x720 @ 120fps
CAMERA_DEVICE = "/dev/video0"
CAMERA_WIDTH = 1600
CAMERA_HEIGHT = 1300
CAMERA_FPS = 60
TARGET_WIDTH = 1600      # Downscale for encoding (maintains ~16:9 crop)
TARGET_HEIGHT = 1300

# Encoder settings
BITRATE = 500        # 4 Mbps (sufficient for grayscale content)

# ================= GSTREAMER PIPELINE =================

# OV2311 pipeline notes:
# - v4l2src replaces nvarguscamerasrc (OV2311 does not go through the Argus ISP)
# - format=GRAY8 is the native OV2311 output (monochrome, 8-bit)
# - videoconvert converts GRAY8 → NV12 for nvv4l2h264enc
# - nvvidconv handles the optional downscale on-GPU after the colorspace convert
pipeline_str = (
    f"v4l2src device={CAMERA_DEVICE} ! "
    f"video/x-raw,format=GRAY8,width={CAMERA_WIDTH},height={CAMERA_HEIGHT},framerate={CAMERA_FPS}/1 ! "
    f"videoconvert ! video/x-raw,format=NV12 ! "
    f"nvvidconv ! video/x-raw(memory:NVMM),format=NV12,width={TARGET_WIDTH},height={TARGET_HEIGHT},framerate={CAMERA_FPS}/1 ! "
    f"nvv4l2h264enc bitrate={BITRATE // 1000} ! "
    f"queue ! h264parse ! rtph264pay config-interval=1 ! "
    f"udpsink host={RECEIVER_IP} port={RECEIVER_PORT} sync=true async=true"
)

print("=" * 80)
print("JETSON ORIN NX - ZERO-COPY HARDWARE ENCODED VIDEO STREAMING")
print("=" * 80)
print(f"\nCamera:     {CAMERA_DEVICE} (Arducam OV2311 — Monochrome Global Shutter)")
print(f"Resolution: {CAMERA_WIDTH}x{CAMERA_HEIGHT} @ {CAMERA_FPS}fps (native) → {TARGET_WIDTH}x{TARGET_HEIGHT} (encoded)")
print(f"Encoder:    NVIDIA NVENC H.264")
print(f"Bitrate:    {BITRATE / 1000000:.1f} Mbps")
print(f"Receiver:   {RECEIVER_IP}:{RECEIVER_PORT}")
print(f"\nNOTE: OV2311 is a monochrome sensor — stream will be grayscale.")
print(f"\nGStreamer Pipeline:")
print(f"{pipeline_str}\n")
print("=" * 80)
print("Starting stream (Press Ctrl+C to stop)...")
print("=" * 80 + "\n")

# ================= SUBPROCESS EXECUTION =================

process = None
try:
    # Run gst_run.py helper script (uses environment variable to pass pipeline)
    # This avoids shell parsing issues with complex GStreamer pipelines
    env = dict(os.environ)
    env['PIPELINE'] = pipeline_str
    
    cmd = [sys.executable, 'gst_run.py']
    
    process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    # Forward output
    while process.poll() is None:
        line = process.stdout.readline()
        if line:
            print(line.rstrip())
    
    # Print any remaining output
    for line in process.stdout:
        if line:
            print(line.rstrip())
    
    exit_code = process.returncode
    if exit_code == 0:
        print("\n✓ Stream ended gracefully.")
    else:
        print(f"\n✗ Stream ended with exit code {exit_code}")
    
except KeyboardInterrupt:
    print("\n\nShutting down...")
    if process and process.poll() is None:
        print("Terminating pipeline...")
        process.terminate()
        time.sleep(1)
        if process.poll() is None:
            process.kill()
            process.wait()
    print("Stream stopped. Camera and encoder cleaned up.")

except Exception as e:
    print(f"ERROR: {e}")
    if process and process.poll() is None:
        process.kill()
    sys.exit(1)