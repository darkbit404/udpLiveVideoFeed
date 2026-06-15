#!/usr/bin/env python3
"""
Jetson Orin NX - Zero-Copy Hardware Encoded UDP Video Streaming (RTP)
Camera: Arducam OV2311 (MIPI CSI, Monochrome Global Shutter)
Encoder: NVIDIA NVENC H.264
Transport: RTP over UDP (zero-copy)

gst_run.py subprocess helper has been eliminated. The pipeline now runs
directly inside this process using GLib.MainLoop, matching the architecture
of receiver.py. This removes:
  - A second Python interpreter loaded in memory
  - A cross-process stdout pipe + relay thread
  - Signal propagation delay on shutdown (was: SIGINT → sender → terminate()
    → sleep(1) → kill(); now: SIGINT → KeyboardInterrupt → pipeline.set_state(NULL))
  - Risk of /dev/video0 remaining locked after a subprocess kill
"""

import gi
import sys

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# ================= CONFIG =================

RECEIVER_IP   = "10.42.0.50"
RECEIVER_PORT = 5000

# Camera settings
# OV2311 supported formats (confirmed via v4l2-ctl): GREY only — no YUV output.
# nvvidconv does not accept GRAY8 directly; CPU videoconvert (GRAY8→I420) is
# used as an intermediate, then nvvidconv (I420→NV12/NVMM) hands off to GPU.
#
# WHY 1280x720 INSTEAD OF 1600x1300:
# tegrastats showed CPU core 6 pinned at 90-92% at 1600x1300@60fps.
# The bottleneck is single-threaded videoconvert at 124.8M pixels/sec.
# 1280x720@60fps = 55.3M pixels/sec — a 57% reduction — freeing the core
# and delivering frames to NVENC steadily instead of in starved bursts.
# Irregular encoder input was the direct cause of video distortion.
#
# OV2311 supports 1280x720 @ 120fps natively. If 60fps motion looks smooth,
# raise CAMERA_FPS to 120 — pixel/sec stays the same, no extra CPU cost.
CAMERA_DEVICE = "/dev/video0"
CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS    = 60
TARGET_WIDTH  = 1280
TARGET_HEIGHT = 720

# Encoder settings
# 1.5 Mbps is ample for 720p grayscale. Raise to 2.5 if detail looks soft.
BITRATE = 1500000   # 1.5 Mbps

# ================= GSTREAMER INIT =================

Gst.init(sys.argv)

# ================= PIPELINE =================

# Pipeline flow:
#   v4l2src      (GRAY8, mmap — OV2311 only exposes GREY formats)
#     → queue          [thread boundary: isolates capture from conversion]
#     → videoconvert   [GRAY8→I420, CPU — runs on its own OS thread]
#     → queue          [thread boundary: isolates conversion from GPU path]
#     → nvvidconv      [I420→NV12/NVMM, GPU — zero-copy into encoder]
#     → nvv4l2h264enc  [NVENC hardware H.264 encoder]
#     → queue          [absorbs encoder output bursts]
#     → h264parse      [packetises H.264 elementary stream]
#     → rtph264pay     [RTP payloader, mtu=1400 avoids IP fragmentation]
#     → udpsink        [sync=false: no clock-pacing needed on live source]

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

# ================= STARTUP BANNER =================

print("=" * 80)
print("JETSON ORIN NX - ZERO-COPY HARDWARE ENCODED VIDEO STREAMING")
print("=" * 80)
print(f"\nCamera:     {CAMERA_DEVICE} (Arducam OV2311 — Monochrome Global Shutter)")
print(f"Resolution: {CAMERA_WIDTH}x{CAMERA_HEIGHT} @ {CAMERA_FPS}fps → {TARGET_WIDTH}x{TARGET_HEIGHT} (encoded)")
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

pipeline = Gst.parse_launch(pipeline_str)
if pipeline is None:
    print("ERROR: Failed to parse GStreamer pipeline.")
    sys.exit(1)

# ================= BUS / ERROR HANDLING =================

loop = GLib.MainLoop()

def on_error(bus, msg):
    err, debug = msg.parse_error()
    print(f"\nERROR: {err.message}")
    if debug:
        print(f"Debug: {debug}")
    loop.quit()

def on_warning(bus, msg):
    warn, debug = msg.parse_warning()
    print(f"WARNING: {warn.message}")

def on_eos(bus, msg):
    print("\nEnd of stream.")
    loop.quit()

bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message::error",   on_error)
bus.connect("message::warning", on_warning)
bus.connect("message::eos",     on_eos)

# ================= STATE MANAGEMENT =================

ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("ERROR: Unable to set pipeline to PLAYING state.")
    sys.exit(1)

print("Pipeline PLAYING. Streaming...\n")

# ================= MAIN LOOP =================

try:
    loop.run()
except KeyboardInterrupt:
    print("\n\nShutting down...")

# ================= CLEANUP =================

pipeline.set_state(Gst.State.NULL)
print("Stream stopped. Camera and encoder cleaned up.")
