#!/usr/bin/env python3
"""
Jetson Orin NX - Zero-Copy Hardware Encoded UDP Video Streaming (RTP)
Camera: Arducam OV2311 (MIPI CSI, Monochrome Global Shutter)
Encoder: NVIDIA NVENC H.264
Transport: RTP over UDP (zero-copy)

NOTE: OV2311 is a monochrome (grayscale) global shutter sensor.
It bypasses the Argus ISP — v4l2src with GRAY8 format is used instead
of nvarguscamerasrc.

FIX 1: Removed CPU-side `videoconvert`. nvvidconv alone handles GRAY8 → NV12
        entirely on the GPU (zero-copy, no system RAM bandwidth consumed).

FIX 2: udpsink sync=false — removes clock-based packet pacing which caused
        constant CPU wakeups on a live camera source.

FIX 3: stdout relay moved to a daemon thread — no longer a tight blocking
        loop on the main thread competing with subprocess scheduling.

Uses gst_run.py subprocess execution to avoid encoder driver crashes.
"""

import os
import sys
import subprocess
import time
import threading

# ================= CONFIG =================

RECEIVER_IP = "10.42.0.50"   # Receiver laptop IP
RECEIVER_PORT = 5000

# Camera settings
# OV2311 native resolution: 1600x1300 @ up to 60fps
# Also supports: 1600x1080 @ 80fps, 1280x720 @ 120fps
CAMERA_DEVICE = "/dev/video0"
CAMERA_WIDTH = 1600
CAMERA_HEIGHT = 1300
CAMERA_FPS = 60
TARGET_WIDTH = 1600
TARGET_HEIGHT = 1300

# Encoder settings
# FIX 2 (related): Reduced from 4 Mbps to 2 Mbps.
# Grayscale content compresses extremely well. Lower bitrate = smaller UDP
# bursts = more headroom on the Wi-Fi link at range. Raise if quality suffers.
BITRATE = 2000000        # 2 Mbps

# ================= GSTREAMER PIPELINE =================

# FIX 1: Pipeline now uses nvvidconv for GRAY8 → NV12 conversion entirely on
# the GPU. The old `videoconvert ! video/x-raw,format=NV12` stage ran on the
# CPU and moved ~750 MB/s of frame data through system RAM at 1600x1300@60fps.
#
# nvvidconv on Jetson supports GRAY8 input directly and outputs NV12 into
# NVMM (GPU-side) memory in a single step, keeping frames off the CPU path.
#
# FIX 2: udpsink sync=false — on a live camera source there is no meaningful
# presentation timestamp to pace against. sync=true caused the GStreamer clock
# subsystem to wake the CPU hundreds of times per second to meter packets.
pipeline_str = (
    f"v4l2src device={CAMERA_DEVICE} io-mode=2 ! "
    f"video/x-raw,format=GRAY8,width={CAMERA_WIDTH},height={CAMERA_HEIGHT},framerate={CAMERA_FPS}/1 ! "
    f"nvvidconv ! "
    f"video/x-raw(memory:NVMM),format=NV12,width={TARGET_WIDTH},height={TARGET_HEIGHT},framerate={CAMERA_FPS}/1 ! "
    f"nvv4l2h264enc bitrate={BITRATE} iframeinterval=30 preset-level=1 ! "
    f"queue max-size-buffers=4 leaky=downstream ! "
    f"h264parse ! "
    f"rtph264pay config-interval=1 mtu=1400 ! "
    f"udpsink host={RECEIVER_IP} port={RECEIVER_PORT} buffer-size=2097152 sync=false async=false"
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
print(f"\nFIX SUMMARY:")
print(f"  [1] CPU videoconvert removed — nvvidconv handles GRAY8→NV12 on GPU")
print(f"  [2] udpsink sync=false — no CPU clock-pacing on live source")
print(f"  [3] stdout relay runs in daemon thread — main thread unblocked")
print(f"\nGStreamer Pipeline:")
print(f"{pipeline_str}\n")
print("=" * 80)
print("Starting stream (Press Ctrl+C to stop)...")
print("=" * 80 + "\n")

# ================= SUBPROCESS EXECUTION =================

# FIX 3: stdout relay moved to a dedicated daemon thread.
# The original tight `while process.poll() is None: readline()` loop ran on
# the main thread, holding the GIL between reads and interfering with
# subprocess scheduling. A daemon thread lets the OS handle blocking I/O
# independently and exits automatically when the main process ends.

def relay_output(proc):
    """Forward subprocess stdout to our stdout from a background thread."""
    try:
        for line in proc.stdout:
            if line:
                print(line.rstrip(), flush=True)
    except Exception:
        pass

process = None
try:
    env = dict(os.environ)
    env['PIPELINE'] = pipeline_str

    cmd = [sys.executable, 'gst_run.py']

    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # FIX 3: Launch relay thread instead of blocking the main thread
    relay_thread = threading.Thread(target=relay_output, args=(process,), daemon=True)
    relay_thread.start()

    # Main thread simply waits for the subprocess to finish
    process.wait()
    relay_thread.join(timeout=2)

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
