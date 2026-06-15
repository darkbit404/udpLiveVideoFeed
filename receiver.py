#!/usr/bin/env python3
"""
Jetson Orin NX / Linux Laptop - Zero-Copy Hardware Decoded UDP Video Streaming (RTP)
Camera source: Arducam OV2311 (Monochrome Global Shutter)
Decoder: NVIDIA NVDEC H.264 (Jetson) or Software fallback (Linux)
Transport: RTP over UDP (zero-copy)

NOTE: The OV2311 is a monochrome sensor, so the decoded stream will be
grayscale. videoconvert passes it through correctly to the display sink.

FIX 4: rtpjitterbuffer tuning for range resilience.
  - latency raised from 80ms → 150ms: gives the buffer more room to absorb
    the irregular packet delivery that occurs when Wi-Fi signal degrades at
    range. At close range this is invisible; at range it prevents cascading
    frame corruption.
  - drop-on-latency changed from true → false: previously, any momentary
    Wi-Fi hiccup would cause the buffer to drop frames rather than absorb
    the spike. With false, packets are held and delivered late rather than
    discarded, which is far less visually disruptive.
  - do-lost=true added: sends a GstRTPPacketLost event downstream when a
    packet is truly unrecoverable, allowing the decoder to conceal the loss
    gracefully rather than outputting corrupted macroblocks.
"""

import gi
import sys
import platform

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# ================= CONFIG =================

LISTEN_PORT = 5000

# ================= PLATFORM DETECTION =================

# Robust Jetson detection: check platform, /proc/cpuinfo, and device-tree model
try:
    cpuinfo = open('/proc/cpuinfo').read().lower()
except Exception:
    cpuinfo = ''

dt_model = ''
try:
    with open('/proc/device-tree/model', 'r') as f:
        dt_model = f.read().lower()
except Exception:
    dt_model = ''

is_jetson = (
    "tegra" in platform.platform().lower()
    or "tegra" in cpuinfo
    or "tegra" in dt_model
)

print(f"Platform: {'Jetson' if is_jetson else 'Linux PC'}")

# ================= GSTREAMER INITIALIZATION =================

Gst.init(sys.argv)

# ================= HARDWARE DECODER DETECTION =================

def check_nvv4l2_decoder():
    """Check if nvv4l2h264dec is available"""
    try:
        pipeline_test = Gst.parse_launch("nvv4l2h264dec ! fakesink")
        return pipeline_test is not None
    except Exception:
        return False

def check_nvdec_decoder():
    """Check if nvdec is available"""
    try:
        pipeline_test = Gst.parse_launch("nvdec ! fakesink")
        return pipeline_test is not None
    except Exception:
        return False

# Choose decoder based on platform
if is_jetson:
    print("Checking for NVIDIA hardware decoder...")
    if check_nvv4l2_decoder():
        decoder = "nvv4l2h264dec"
        print("Using nvv4l2h264dec (Jetson hardware decoder)")
    elif check_nvdec_decoder():
        decoder = "nvdec"
        print("Using nvdec (NVIDIA hardware decoder)")
    else:
        decoder = "avdec_h264"
        print("WARNING: Hardware decoder not found. Using software decoder (avdec_h264)")
else:
    # Linux PC - use available decoder
    try:
        pipeline_test = Gst.parse_launch("nvdec ! fakesink")
        decoder = "nvdec"
        print("Using nvdec (NVIDIA GPU decoder)")
    except Exception:
        if Gst.ElementFactory.find("avdec_h264") is not None:
            decoder = "avdec_h264"
            print("Using software decoder (avdec_h264)")
        else:
            decoder = "decodebin"
            print("avdec_h264 not found — using generic decodebin fallback")

# ================= GSTREAMER PIPELINE - HARDWARE DECODED RTP =================

# FIX 4: rtpjitterbuffer changes explained:
#
#   latency=150
#     Wi-Fi at range delivers packets with highly variable inter-arrival times
#     (jitter spikes to 100ms+ are common as the radio retries at lower MCS).
#     80ms was too tight — packets arriving 85ms late were treated as lost.
#     150ms gives a comfortable margin without adding perceptible display lag.
#
#   drop-on-latency=false
#     The old behaviour dropped any packet that arrived after the jitter
#     deadline, turning every brief signal fade into a burst of corrupted or
#     missing frames. With false, late packets are still rendered (slightly
#     delayed) which is far less disruptive visually.
#
#   do-lost=true
#     When a packet is genuinely unrecoverable (gap in sequence numbers),
#     this sends a downstream loss event so h264parse/the decoder can request
#     error concealment rather than outputting corrupted macroblocks.

pipeline_str = (
    f"udpsrc address=0.0.0.0 port={LISTEN_PORT} buffer-size=4194304 "
    f"caps=\"application/x-rtp,media=(string)video,clock-rate=(int)90000,encoding-name=(string)H264\" ! "
    f"rtpjitterbuffer latency=150 drop-on-latency=false do-lost=true ! "
    f"rtph264depay ! "
    f"h264parse ! "
    f"{decoder} ! "
    f"videoconvert ! "
    f"xvimagesink sync=false"
)

print(f"\nFIX SUMMARY:")
print(f"  [4] rtpjitterbuffer: latency=150, drop-on-latency=false, do-lost=true")
print(f"      → absorbs Wi-Fi jitter spikes at range without dropping frames")
print(f"\nGStreamer Pipeline:")
print(f"{pipeline_str}\n")

# ================= PIPELINE CREATION =================

try:
    pipeline = Gst.parse_launch(pipeline_str)
except Exception as e:
    print(f"Failed to create pipeline: {e}")
    print("Trying fallback pipeline with decodebin...")
    pipeline_str = (
        f"udpsrc address=0.0.0.0 port={LISTEN_PORT} buffer-size=4194304 "
        f"caps=\"application/x-rtp,media=(string)video,clock-rate=(int)90000,encoding-name=(string)H264\" ! "
        f"rtpjitterbuffer latency=150 drop-on-latency=false do-lost=true ! "
        f"rtph264depay ! "
        f"h264parse ! "
        f"decodebin ! "
        f"videoconvert ! "
        f"xvimagesink sync=false"
    )
    try:
        pipeline = Gst.parse_launch(pipeline_str)
    except Exception as e2:
        print(f"Fallback pipeline failed: {e2}")
        sys.exit(1)

if pipeline is None:
    print("Failed to parse GStreamer pipeline")
    sys.exit(1)

# ================= PIPELINE STATE MANAGEMENT =================

print(f"Listening for RTP video stream on port {LISTEN_PORT}")
print("Codec: H.264 | Source: Arducam OV2311 (Monochrome — grayscale stream)")
print("Press Ctrl+C to stop...\n")

ret = pipeline.set_state(Gst.State.PLAYING)

if ret == Gst.StateChangeReturn.FAILURE:
    print("Unable to set the pipeline to the PLAYING state.")
    sys.exit(1)

# ================= ERROR HANDLING & MONITORING =================

def on_error(bus, msg):
    error, debug = msg.parse_error()
    print(f"ERROR: {error.message}")
    if debug:
        print(f"Debug info: {debug}")
    pipeline.set_state(Gst.State.NULL)
    sys.exit(1)

def on_warning(bus, msg):
    warning, debug = msg.parse_warning()
    print(f"WARNING: {warning.message}")

def on_eos(bus, msg):
    print("End of stream reached")
    pipeline.set_state(Gst.State.NULL)
    sys.exit(0)

# ================= MAIN LOOP =================

bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message::error", on_error)
bus.connect("message::warning", on_warning)
bus.connect("message::eos", on_eos)

try:
    loop = GLib.MainLoop()
    loop.run()
except KeyboardInterrupt:
    print("\n\nShutting down...")

# ================= CLEANUP =================

pipeline.set_state(Gst.State.NULL)
print("Receiver stopped. Decoder cleaned up.")
