#!/usr/bin/env python3
"""
Jetson Orin NX - Zero-Copy Hardware Encoded UDP Video Streaming (RTP)
Camera: IMX477 (MIPI CSI)
Encoder: NVIDIA NVENC H.264
Transport: RTP over UDP (zero-copy)

Uses gst-launch-1.0 subprocess execution to avoid encoder driver crashes.
"""

import os
import sys
import subprocess
import time
import signal

# ================= CONFIG =================

RECEIVER_IP = "10.42.0.249"   # Receiver laptop IP
RECEIVER_PORT = 5000

# Camera settings
CAMERA_WIDTH = 1920      # Use native resolution
CAMERA_HEIGHT = 1080
CAMERA_FPS = 30
TARGET_WIDTH = 1080      # Downscale to reduce bitrate
TARGET_HEIGHT = 720

# Encoder settings  
BITRATE = 500 

# ================= GSTREAMER PIPELINE =================

pipeline_str = (
    f"nvarguscamerasrc ! "
    f"video/x-raw(memory:NVMM),format=NV12,width={CAMERA_WIDTH},height={CAMERA_HEIGHT},framerate={CAMERA_FPS}/1 ! "
    f"nvvidconv ! video/x-raw(memory:NVMM),format=I420,width={TARGET_WIDTH},height={TARGET_HEIGHT},framerate={CAMERA_FPS}/1 ! "
    f"nvv4l2h264enc bitrate={BITRATE // 1000} ! "
    f"queue ! h264parse ! rtph264pay config-interval=-1 ! "
    f"udpsink host={RECEIVER_IP} port={RECEIVER_PORT} sync=true async=true"
)

print("=" * 80)
print("JETSON ORIN NX - ZERO-COPY HARDWARE ENCODED VIDEO STREAMING")
print("=" * 80)
print(f"\nCamera:    /dev/video0 (IMX477)")
print(f"Resolution: {CAMERA_WIDTH}x{CAMERA_HEIGHT} (native) → {TARGET_WIDTH}x{TARGET_HEIGHT} (encoded)")
print(f"Encoder:   NVIDIA NVENC H.264")
print(f"Bitrate:   {BITRATE / 1000000:.1f} Mbps")
print(f"Receiver:  {RECEIVER_IP}:{RECEIVER_PORT}")
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