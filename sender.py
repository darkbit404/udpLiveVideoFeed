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

FIX 4 (merged): gst_run.py inlined — pipeline runs directly in-process via
        GStreamer bindings instead of a subprocess.
"""

import sys
import time
import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# ================= CONFIG =================

RECEIVER_IP = "10.42.0.50"   # Receiver laptop IP
RECEIVER_PORT = 5000

# Camera settings
CAMERA_DEVICE = "/dev/video0"
CAMERA_WIDTH = 1600
CAMERA_HEIGHT = 1300
CAMERA_FPS = 60
TARGET_WIDTH = 1600
TARGET_HEIGHT = 1300

# Encoder settings
BITRATE = 2000000        # 2 Mbps

# ================= GSTREAMER INITIALIZATION =================

Gst.init(None)

# ================= GSTREAMER PIPELINE =================

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
print(f"\nGStreamer Pipeline:")
print(f"{pipeline_str}\n")
print("=" * 80)
print("Starting stream (Press Ctrl+C to stop)...")
print("=" * 80 + "\n")

# ================= PIPELINE CREATION =================

try:
    pipeline = Gst.parse_launch(pipeline_str)
    if pipeline is None:
        print("Failed to parse GStreamer pipeline", file=sys.stderr)
        sys.exit(1)

    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("Failed to set pipeline to PLAYING state", file=sys.stderr)
        sys.exit(1)

    print("Pipeline PLAYING. Running indefinitely...", file=sys.stderr)

    # ================= BUS MONITORING =================

    bus = pipeline.get_bus()

    while True:
        msg = bus.timed_pop_filtered(100000000, Gst.MessageType.ANY)

        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"ERROR: {err.message}", file=sys.stderr)
                if debug:
                    print(f"DEBUG: {debug}", file=sys.stderr)
                pipeline.set_state(Gst.State.NULL)
                sys.exit(1)
            elif msg.type == Gst.MessageType.EOS:
                print("End of stream", file=sys.stderr)
                pipeline.set_state(Gst.State.NULL)
                sys.exit(0)
            elif msg.type == Gst.MessageType.WARNING:
                warn, debug = msg.parse_warning()
                print(f"WARNING: {warn.message}", file=sys.stderr)

        time.sleep(0.01)

except KeyboardInterrupt:
    print("\n\nShutting down...")
    pipeline.set_state(Gst.State.NULL)
    print("Stream stopped. Camera and encoder cleaned up.")

except Exception as e:
    print(f"ERROR: {e}")
    try:
        pipeline.set_state(Gst.State.NULL)
    except Exception:
        pass
    sys.exit(1)