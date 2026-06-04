#!/usr/bin/env python3
"""
Camera and Hardware Codec Detection for Jetson Orin NX
Detects available cameras and hardware acceleration capabilities
"""

import subprocess
import os
import sys

print("=" * 60)
print("JETSON ORIN NX - HARDWARE & CAMERA DETECTION")
print("=" * 60)

# ================= CAMERA DETECTION =================

print("\n[1] DETECTING CAMERAS...")
print("-" * 60)

video_devices = []
for i in range(10):
    device = f"/dev/video{i}"
    if os.path.exists(device):
        video_devices.append(device)
        print(f"✓ Found {device}")

if not video_devices:
    print("✗ No video devices found!")
    sys.exit(1)

# Get camera info via v4l2-ctl
print("\n[2] CAMERA CAPABILITIES (v4l2-ctl)...")
print("-" * 60)

for device in video_devices:
    print(f"\n{device}:")
    try:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "--info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n')[:5]:
                if line.strip():
                    print(f"  {line}")
        
        # Get supported formats
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "--list-formats"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            formats = [l for l in result.stdout.split('\n') if 'Pixel' in l or 'YUV' in l or 'MJPEG' in l]
            if formats:
                print("  Supported Formats:")
                for fmt in formats[:3]:
                    print(f"    {fmt.strip()}")
    except Exception as e:
        print(f"  Error: {e}")

# ================= GSTREAMER ELEMENT DETECTION =================

print("\n\n[3] GSTREAMER HARDWARE ACCELERATION...")
print("-" * 60)

def check_gst_element(element_name):
    """Check if GStreamer element is available"""
    try:
        result = subprocess.run(
            ["gst-inspect-1.0", element_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False

encoders = {
    "nvv4l2h264enc": "NVIDIA V4L2 H.264 Encoder (recommended)",
    "nvv4l2h265enc": "NVIDIA V4L2 H.265 Encoder",
    "omxh264enc": "OpenMAX H.264 Encoder (legacy)",
}

decoders = {
    "nvv4l2h264dec": "NVIDIA V4L2 H.264 Decoder (recommended)",
    "nvv4l2h265dec": "NVIDIA V4L2 H.265 Decoder",
    "nvdec": "NVIDIA NVDEC Decoder (GPU)",
    "avdec_h264": "Software H.264 Decoder (fallback)",
}

print("\nENCODERS:")
encoder_found = False
for enc, desc in encoders.items():
    if check_gst_element(enc):
        print(f"  ✓ {enc:<20} - {desc}")
        encoder_found = True
    else:
        print(f"  ✗ {enc:<20} - Not available")

if not encoder_found:
    print("  ⚠ No hardware encoders found!")

print("\nDECODERS:")
decoder_found = False
for dec, desc in decoders.items():
    if check_gst_element(dec):
        print(f"  ✓ {dec:<20} - {desc}")
        decoder_found = True
    else:
        print(f"  ✗ {dec:<20} - Not available")

# ================= JETPACK VERSION =================

print("\n\n[4] JETPACK & NVIDIA TOOLS...")
print("-" * 60)

try:
    result = subprocess.run(
        ["apt-cache", "show", "nvidia-jetpack"],
        capture_output=True,
        text=True,
        timeout=5
    )
    for line in result.stdout.split('\n'):
        if 'Version' in line:
            print(f"✓ {line}")
            break
except:
    print("✗ Could not determine JetPack version")

# Check CUDA
try:
    result = subprocess.run(
        ["nvcc", "--version"],
        capture_output=True,
        text=True,
        timeout=5
    )
    for line in result.stdout.split('\n'):
        if 'release' in line.lower():
            print(f"✓ CUDA: {line.strip()}")
            break
except:
    print("✗ CUDA not found")

# Check cuDNN
try:
    result = subprocess.run(
        ["dpkg", "-l"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if 'cudnn' in result.stdout:
        print("✓ cuDNN: Installed")
    else:
        print("✗ cuDNN: Not found")
except:
    pass

# ================= RECOMMENDATIONS =================

print("\n\n[5] RECOMMENDATIONS...")
print("-" * 60)

if not encoder_found:
    print("""
⚠ MISSING: NVIDIA Hardware Encoders

Install with:
  sudo apt update
  sudo apt install nvidia-jetpack
  
Or install specific packages:
  sudo apt install nvidia-l4t-jetson-multimedia-api
  
Then restart the Jetson.
""")

if not decoder_found:
    print("""
⚠ WARNING: No hardware decoders found
The system will fall back to software decoding (slower).
""")

print("\n[6] OPTIMAL PIPELINE SETTINGS...")
print("-" * 60)
print("""
SENDER (Jetson Orin NX):
  Camera:    /dev/video0 (IMX477)
  Format:    NV12 (optimal for nvv4l2h264enc)
  Resolution: 1280x720@30fps
  Encoder:   nvv4l2h264enc
  Bitrate:   5000 kbps (adjust to your network)

RECEIVER (Linux Laptop):
  Decoder:   nvv4l2h264dec (if Jetson) or avdec_h264 (software)
  Display:   autovideosink (automatically selects best sink)
  
NETWORK:
  Protocol:  RTP over UDP
  Port:      5000
  Zero-Copy: YES (entire pipeline)
""")

print("\n" + "=" * 60)
print("Detection Complete!")
print("=" * 60)
