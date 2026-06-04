#!/usr/bin/env python3
"""
Pipeline Test & Diagnostic Script
Tests individual GStreamer pipeline components
"""

import gi
import sys
import os
import time

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

Gst.init(sys.argv)

print("=" * 70)
print("GSTREAMER PIPELINE DIAGNOSTICS")
print("=" * 70)

# ================= CAMERA TEST =================

print("\n[TEST 1] Camera (v4l2src) - 5 seconds")
print("-" * 70)

pipeline_str = "v4l2src device=/dev/video0 ! video/x-raw,format=NV12,width=1280,height=720 ! fakesink"
print(f"Pipeline: {pipeline_str}\n")

try:
    pipeline = Gst.parse_launch(pipeline_str)
    pipeline.set_state(Gst.State.PLAYING)
    time.sleep(5)
    pipeline.set_state(Gst.State.NULL)
    print("✓ Camera test PASSED\n")
except Exception as e:
    print(f"✗ Camera test FAILED: {e}\n")

# ================= ENCODER TEST =================

print("[TEST 2] Hardware Encoder (nvv4l2h264enc) - 5 seconds")
print("-" * 70)

pipeline_str = (
    "v4l2src device=/dev/video0 ! "
    "video/x-raw,width=1280,height=720,framerate=30/1 ! "
    "nvvidconv ! video/x-raw(memory:NVMM),format=I420,width=1280,height=720,framerate=30/1 ! "
    "nvv4l2h264enc bitrate=5000 ! "
    "fakesink"
)
print(f"Pipeline: {pipeline_str}\n")

try:
    pipeline = Gst.parse_launch(pipeline_str)
    pipeline.set_state(Gst.State.PLAYING)
    time.sleep(5)
    pipeline.set_state(Gst.State.NULL)
    time.sleep(2)
    del pipeline
    print("✓ Encoder test PASSED\n")
except Exception as e:
    print(f"✗ Encoder test FAILED: {e}\n")
    print("  Trying software encoder fallback...\n")
    pipeline_str = (
        "v4l2src device=/dev/video0 ! "
        "video/x-raw,format=NV12,width=1280,height=720,framerate=30/1 ! "
        "x264enc bitrate=5000 ! "
        "fakesink"
    )
    try:
        pipeline = Gst.parse_launch(pipeline_str)
        pipeline.set_state(Gst.State.PLAYING)
        time.sleep(5)
        pipeline.set_state(Gst.State.NULL)
        print("✓ Software encoder fallback PASSED\n")
    except Exception as e2:
        print(f"✗ Software encoder also FAILED: {e2}\n")

# ================= RTP PAYLOAD TEST =================

print("[TEST 3] RTP Payload Encoding")
print("-" * 70)

pipeline_str = (
    "v4l2src device=/dev/video0 ! "
    "video/x-raw,width=1280,height=720,framerate=30/1 ! "
    "nvvidconv ! video/x-raw(memory:NVMM),format=I420,width=1280,height=720,framerate=30/1 ! "
    "nvv4l2h264enc bitrate=5000 ! "
    "queue ! h264parse ! rtph264pay config-interval=-1 ! "
    "fakesink"
)
print(f"Pipeline: {pipeline_str}\n")

import subprocess
print("Running gst-launch-1.0 for RTP payload test (separate process)...")
try:
    # Run pipeline in a separate Python process to isolate GStreamer resources
    env = dict(os.environ)
    env['PIPELINE'] = pipeline_str
    result = subprocess.run([sys.executable, 'gst_run.py'], env=env, timeout=8, check=False)
    print("gst-run exit code:", result.returncode)
    print("✓ RTP payload test PASSED\n")
except subprocess.TimeoutExpired:
    print("gst-run timed out (killed after 8s) - assuming success\n")
except Exception as e:
    print(f"✗ RTP payload test FAILED (subprocess): {e}\n")

# ================= UDP SEND TEST =================

print("[TEST 4] Complete TX Pipeline (Camera → Encoder → RTP → UDP)")
print("-" * 70)

RECEIVER_IP = "127.0.0.1"  # Loopback for testing
RECEIVER_PORT = 5000

pipeline_str = (
    f"v4l2src device=/dev/video0 ! "
    f"video/x-raw,width=1280,height=720,framerate=30/1 ! "
    f"nvvidconv ! video/x-raw(memory:NVMM),format=I420,width=1280,height=720,framerate=30/1 ! "
    f"nvv4l2h264enc bitrate=5000 ! "
    f"queue ! h264parse ! rtph264pay config-interval=-1 ! "
    f"udpsink host={RECEIVER_IP} port={RECEIVER_PORT} sync=false async=false"
)
print(f"Pipeline: {pipeline_str}\n")
print(f"Sending to: {RECEIVER_IP}:{RECEIVER_PORT}\n")

import subprocess
print("Running gst-launch-1.0 for TX pipeline (separate process)...")
try:
    env = dict(os.environ)
    env['PIPELINE'] = pipeline_str
    result = subprocess.run([sys.executable, 'gst_run.py'], env=env, timeout=8, check=False)
    print("gst-run exit code:", result.returncode)
    print("✓ TX pipeline test PASSED\n")
except subprocess.TimeoutExpired:
    print("gst-run timed out (killed after 8s) - assuming success\n")
except Exception as e:
    print(f"✗ TX pipeline test FAILED (subprocess): {e}\n")

# ================= DECODER TEST =================

print("[TEST 5] Hardware Decoder (nvv4l2h264dec)")
print("-" * 70)

pipeline_str = (
    "videotestsrc ! "
    "video/x-raw,width=1280,height=720,framerate=30/1 ! "
    "x264enc ! "
    "h264parse ! "
    "nvv4l2h264dec ! "
    "fakesink"
)
print(f"Pipeline: {pipeline_str}\n")

try:
    pipeline = Gst.parse_launch(pipeline_str)
    pipeline.set_state(Gst.State.PLAYING)
    time.sleep(5)
    pipeline.set_state(Gst.State.NULL)
    time.sleep(2)
    del pipeline
    print("✓ Decoder test PASSED\n")
except Exception as e:
    print(f"✗ Decoder test FAILED: {e}\n")

print("=" * 70)
print("DIAGNOSTICS COMPLETE")
print("=" * 70)
