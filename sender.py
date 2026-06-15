#!/usr/bin/env python3
"""
Jetson Orin NX - Zero-Copy Hardware Encoded UDP Video Streaming (RTP)
Camera: Arducam OV2311 (MIPI CSI, Monochrome Global Shutter)
Encoder: NVIDIA NVENC H.264
Transport: RTP over UDP (zero-copy)

NOTE: OV2311 is a monochrome (grayscale) global shutter sensor.
It bypasses the Argus ISP — v4l2src with GRAY8 format is used instead
of nvarguscamerasrc.

FIX 1: CPU videoconvert GRAY8→I420 is isolated behind a queue element so
        GStreamer moves it to its own OS thread, decoupling it from v4l2src's
        capture thread. Previously a stall in conversion stalled capture too.

FIX 2: Resolution reduced from 1600x1300 to 1280x720.
        tegrastats showed CPU core 6 pinned at 90-92% — the bottleneck was
        single-threaded videoconvert processing 124.8M pixels/sec at 1600x1300.
        At 1280x720 this drops to 55.3M pixels/sec (57% less), bringing core
        load to ~40% and giving NVENC a steady frame supply instead of bursts.

FIX 3: udpsink sync=false — removes clock-based packet pacing on live source.

FIX 4: stdout relay moved to a daemon thread — main thread unblocked.

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
# OV2311 supported formats (confirmed via v4l2-ctl): GREY only (no YUV).
# nvvidconv does not accept GREY/GRAY8 directly — requires CPU videoconvert
# as an intermediate step (GRAY8 → I420), then nvvidconv (I420 → NV12/NVMM).
#
# WHY 1280x720 INSTEAD OF 1600x1300:
# tegrastats showed CPU core 6 pinned at 90-92% at 1600x1300@60fps.
# The bottleneck is single-threaded videoconvert at 124.8M pixels/sec.
# 1280x720@60fps = 55.3M pixels/sec — a 57% reduction — freeing the core
# and delivering frames to NVENC steadily instead of in starved bursts.
# Irregular encoder input was the direct cause of video distortion.
#
# NOTE: OV2311 supports 1280x720 @ 120fps natively. If 60fps looks smooth,
# try CAMERA_FPS=120 — pixel rate stays the same so CPU load won't increase.
CAMERA_DEVICE = "/dev/video0"
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 60           # Raise to 120 if smoother motion is needed
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720

# Encoder settings
# 1.5 Mbps is ample for 720p grayscale. Raise to 2.5 if detail looks soft.
BITRATE = 1500000        # 1.5 Mbps

# ================= GSTREAMER PIPELINE =================

# Pipeline flow:
#   v4l2src (GRAY8, mmap)
#     → queue            [isolates capture thread]
#     → videoconvert     [GRAY8→I420, CPU, now on its own thread]
#     → queue            [decouples convert from nvvidconv]
#     → nvvidconv        [I420→NV12/NVMM, GPU]
#     → nvv4l2h264enc    [NVENC hardware encoder]
#     → queue            [absorbs encoder output bursts]
#     → h264parse
#     → rtph264pay
#     → udpsink          [sync=false: no clock-pacing on live source]
#
# The two queues around videoconvert give GStreamer's scheduler room to run
# capture, conversion, and encoding on separate OS threads, preventing a
# slow conversion frame from blocking the camera capture buffer.
pipeline_str = (
    f"v4l2src device={CAMERA_DEVICE} ! "
    f"video/x-raw,format=GRAY8,width={CAMERA_WIDTH},height={CAMERA_HEIGHT},framerate={CAMERA_FPS}/1 ! "
    f"queue max-size-buffers=2 leaky=downstream ! "
    f"videoconvert ! video/x-raw,format=I420 ! "
    f"queue max-size-buffers=2 leaky=downstream ! "
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
print(f"Resolution: {CAMERA_WIDTH}x{CAMERA_HEIGHT} @ {CAMERA_FPS}fps → {TARGET_WIDTH}x{TARGET_HEIGHT} (encoded)")
print(f"Encoder:    NVIDIA NVENC H.264")
print(f"Bitrate:    {BITRATE / 1000000:.1f} Mbps")
print(f"Receiver:   {RECEIVER_IP}:{RECEIVER_PORT}")
print(f"\nNOTE: OV2311 is a monochrome sensor — stream will be grayscale.")
print(f"\nFIX SUMMARY:")
print(f"  [1] videoconvert isolated in own thread via surrounding queues")
print(f"  [2] Resolution 1600x1300 → 1280x720: 57% less CPU pixel work")
print(f"      (core 6 was 90-92%; now expected ~40%)")
print(f"  [3] udpsink sync=false — no CPU clock-pacing on live source")
print(f"  [4] stdout relay runs in daemon thread — main thread unblocked")
print(f"\nGStreamer Pipeline:")
print(f"{pipeline_str}\n")
print("=" * 80)
print("Starting stream (Press Ctrl+C to stop)...")
print("=" * 80 + "\n")

# ================= SUBPROCESS EXECUTION =================

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

    relay_thread = threading.Thread(target=relay_output, args=(process,), daemon=True)
    relay_thread.start()

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
