#!/usr/bin/env python3
"""
Jetson Orin NX - Zero-Copy Hardware Encoded UDP Video Streaming (RTP)
Camera: Arducam OV2311 (MIPI CSI, Monochrome Global Shutter)
Encoder: NVIDIA NVENC H.264
Transport: RTP over UDP (zero-copy)

CPU / GPU LOAD BREAKDOWN
------------------------
Each pipeline stage runs on a distinct processing unit:

  v4l2src       [CPU — kernel driver]
    Captures raw GRAY8 frames from the OV2311 via V4L2 mmap. The kernel
    DMA-copies sensor data into a system-memory buffer; no GPU involvement.

  videoconvert  [CPU — single-threaded, the pipeline bottleneck]
    Converts GRAY8 → I420 entirely in software. nvvidconv cannot accept
    GRAY8 from system memory directly, making this step unavoidable with
    the OV2311. At 1600×1300@60fps this saturates a single core (~90-92%).
    At 1280×720@60fps the load drops to ~40-45%, which is why 720p is used.

  nvvidconv     [GPU — VIC / video image compositor]
    Converts I420 (system memory) → NV12 (NVMM, GPU-mapped memory).
    This is where the data crosses from the CPU domain into the GPU domain.
    From this point onward all buffers are zero-copy NVMM references.

  nvv4l2h264enc [GPU — NVENC hardware H.264 encoder]
    Encodes NV12/NVMM frames using the dedicated NVENC block on the Orin NX.
    Runs entirely on the encoder ASIC; negligible CPU and GPU shader load.
    Output is an H.264 elementary stream in system memory.

  h264parse / rtph264pay / udpsink  [CPU — lightweight]
    Parsing, RTP packetisation, and UDP socket writes are CPU tasks but
    involve only metadata and small packet headers. Payload bytes are passed
    by reference where possible. Combined CPU cost is well under 5%.

    Parses the H.264 bitstream to find NAL unit boundaries, SPS/PPS headers, 
    and stream metadata. This is pure byte-level parsing logic with no parallelisable math — 
    there's nothing for a GPU to accelerate. The NVENC output already lands in system memory, 
    so there's no NVMM buffer to hand off anyway.

    Constructs RTP packets: adds sequence numbers, timestamps, SSRC, and fragments NAL units 
    to fit the MTU. This is sequential, stateful network protocol logic — 
    the kind of work GPUs are fundamentally bad at (branchy, low-parallelism, one-packet-at-a-time).

    Writes to a kernel UDP socket via a syscall. The network stack lives in the kernel, on the CPU. 
    Even with RDMA or GPU-direct technologies (which require specialised NICs and are nowhere near a Jetson Wi-Fi setup), 
    the data has to transit through the kernel networking stack.

SUMMARY:
  The one unavoidable CPU cost is the GRAY8 → I420 conversion. All other
  heavy lifting (scaling, encoding) is done on dedicated GPU hardware.
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

# Pipeline flow (CPU = system CPU core, GPU = on-die NVIDIA hardware block):
#
#   v4l2src      [CPU] GRAY8 frames via V4L2 mmap; kernel DMA into system RAM
#     → queue          [thread boundary: isolates capture from conversion]
#     → videoconvert   [CPU] GRAY8→I420 — software conversion, single-threaded;
#                      this is the only unavoidable CPU-heavy stage (see module
#                      docstring). Runs on its own OS thread courtesy of queue.
#     → queue          [thread boundary: isolates CPU conversion from GPU path]
#     → nvvidconv      [GPU / VIC] I420 (system RAM) → NV12 (NVMM); data crosses
#                      from CPU domain into GPU-mapped memory here — zero-copy
#                      from this point forward
#     → nvv4l2h264enc  [GPU / NVENC] hardware H.264 encode from NVMM; negligible
#                      CPU and shader cost — runs on the dedicated encoder ASIC
#     → queue          [absorbs encoder output bursts]
#     → h264parse      [CPU] lightweight — metadata/header parsing only
#     → rtph264pay     [CPU] RTP packetisation; mtu=1400 avoids IP fragmentation
#     → udpsink        [CPU] UDP socket writes; sync=false, no clock-pacing needed

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