#!/usr/bin/env python3
"""
Packet Visualization Quick Start Guide
Helps run sender and receiver visualization tools together
"""

import subprocess
import sys
import os
import time
from pathlib import Path

print("=" * 80)
print("PACKET VISUALIZATION SETUP")
print("=" * 80)
print("""
This tool helps you visualize exact packets being streamed in real-time.

COMPONENTS:
  1. sender_visualization.py   - Shows frames and packets being SENT from Jetson
  2. receiver_visualization.py - Shows frames and packets being RECEIVED on laptop
  3. stream_diagnostics.py     - Analyzes stream quality and packet loss

REQUIREMENTS:
  - OpenCV (cv2): pip install opencv-python
  - Python 3.8+
  - Both sender and receiver on same network (preferably 5GHz WiFi)

RECOMMENDED SETUP:
  On Jetson (Sender):
    Terminal 1: python3 sender_visualization.py
    Terminal 2: python3 stream_diagnostics.py

  On Laptop (Receiver):
    Terminal 1: python3 receiver_visualization.py
    Terminal 2: python3 stream_diagnostics.py

THIS WILL SHOW YOU:
  ✓ Exact frames and packets being transmitted
  ✓ Frame integrity (complete/incomplete/torn)
  ✓ Packet loss detection
  ✓ Real-time bitrate and FPS
  ✓ Sequence number gaps (causes of frame tears)
  ✓ Network latency and WiFi band

CONTROLS:
  Press 'q' to quit any visualization window

INTERPRETING RESULTS:
  ✓ COMPLETE / ✓ NO GAPS
    → Frame transmitted/received perfectly
  
  ✗ INCOMPLETE
    → Frame has missing packets (will show as tear/corruption)
  
  ✗ GAPS DETECTED
    → RTP sequence numbers show packet loss in this frame
  
  ⚠ Packet Loss > 0
    → Previous frames had packet loss
    → Likely cause of frame tears
""")

print("\n" + "=" * 80)
print("QUICK START OPTIONS")
print("=" * 80)

options = [
    "1. Run sender-side visualization (Jetson)",
    "2. Run receiver-side visualization (Laptop)",
    "3. Run stream diagnostics",
    "4. Show usage instructions",
    "5. Exit",
]

for opt in options:
    print(opt)

while True:
    try:
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == "1":
            print("\n[SENDER] Starting visualization...")
            print("Run on Jetson with: python3 sender_visualization.py")
            subprocess.run([sys.executable, "sender_visualization.py"])
        
        elif choice == "2":
            print("\n[RECEIVER] Starting visualization...")
            print("Run on Laptop with: python3 receiver_visualization.py")
            subprocess.run([sys.executable, "receiver_visualization.py"])
        
        elif choice == "3":
            print("\n[DIAGNOSTICS] Starting stream analysis...")
            print("Make sure sender is streaming before running this!")
            subprocess.run([sys.executable, "stream_diagnostics.py"])
        
        elif choice == "4":
            print("""
DETAILED USAGE GUIDE:

1. SENDER VISUALIZATION (sender_visualization.py):
   
   What it shows:
   - Live camera feed from Jetson with overlay stats
   - Frame counter and current frame number
   - FPS and bitrate
   - Packets and bytes per frame
   - Estimated streaming quality
   
   Indicates:
   - If FPS < 30: Encoding bottleneck
   - If Bitrate > target: Network may drop packets
   - If Packets/Frame varies: Frame size inconsistent
   
   Why it matters:
   - Confirms frames are being captured and formatted
   - Shows encoder output characteristics
   - Helps identify sender-side issues

2. RECEIVER VISUALIZATION (receiver_visualization.py):
   
   What it shows:
   - Incoming RTP packets and their statistics
   - Frame completeness status (✓ COMPLETE or ✗ INCOMPLETE)
   - Sequence number gaps (indicates packet loss)
   - Total packets and data received
   - Per-frame packet counts
   
   Frame Status Meanings:
   ✓ COMPLETE     - All packets for this frame arrived
   ✗ INCOMPLETE   - Some packets missing (WILL CAUSE TEAR)
   ✓ NO GAPS      - RTP sequence numbers are consecutive
   ✗ GAPS FOUND   - Missing sequence numbers (packet loss)
   
   Why it matters:
   - Shows EXACTLY what the receiver gets
   - Identifies frame corruption before display
   - Detects packet loss in network

3. STREAM DIAGNOSTICS (stream_diagnostics.py):
   
   What it analyzes:
   - Network connectivity to sender/receiver
   - Round-trip latency
   - WiFi signal quality and band
   - RTP packet characteristics
   - Overall stream quality metrics
   
   Key metrics:
   - Packet Loss: Lost packets → frame tears
   - Bitrate: Should match target (5 Mbps default)
   - Packets/Frame: ~30-40 typical for H.264
   - Frame Rate: Should be 30 FPS
   
   Diagnostics help determine:
   - Is it a network problem? (5GHz, latency, interference)
   - Is it a sender problem? (bitrate, resolution)
   - Is it a receiver problem? (decoding issues)

TROUBLESHOOTING FRAME TEARS:

If you see:
  → Many "✗ INCOMPLETE" frames on receiver
    Cause: Packet loss in network
    Fix: Switch to 5GHz WiFi, reduce bitrate, reduce resolution
  
  → "✗ GAPS DETECTED" in diagnostics
    Cause: RTP sequence numbers show missing packets
    Fix: Check WiFi signal, reduce bitrate, check for interference
  
  → ⚠ HIGH PACKET LOSS
    Cause: Network congestion or weak WiFi
    Fix: Use 5GHz band, move closer to router, reduce bitrate
  
  → Frames arrive but display is torn
    Cause: Incomplete frames received
    Fix: Improve network, reduce bitrate, use hardware acceleration

""")
        
        elif choice == "5":
            print("Exiting...")
            break
        
        else:
            print("Invalid option. Please enter 1-5.")
    
    except KeyboardInterrupt:
        print("\n\nExiting...")
        break
    except Exception as e:
        print(f"Error: {e}")

print("\n" + "=" * 80)
print("REMEMBER:")
print("  • Use 5GHz WiFi for best results")
print("  • Monitor both sender and receiver simultaneously")
print("  • Check diagnostics regularly")
print("  • Compare frame counts on sender vs receiver")
print("=" * 80)
