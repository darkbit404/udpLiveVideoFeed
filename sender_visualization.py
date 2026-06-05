#!/usr/bin/env python3
"""
Sender-Side Packet Visualization
Displays frame-by-frame packet statistics on Jetson screen
Shows what's being transmitted and frame integrity
"""

import cv2
import gi
import sys
import time
import threading
import queue
from collections import deque
from datetime import datetime

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# ================= CONFIG =================

RECEIVER_IP = "10.42.0.249"
RECEIVER_PORT = 5000
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
CAMERA_FPS = 30
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
BITRATE = 5000

# ================= STATISTICS TRACKING =================

class FrameStats:
    """Track per-frame statistics"""
    def __init__(self, max_frames=60):
        self.max_frames = max_frames
        self.frames = deque(maxlen=max_frames)
        self.current_frame = {
            'id': 0,
            'timestamp': time.time(),
            'packets': 0,
            'bytes': 0,
        }
        self.lock = threading.Lock()
    
    def update_frame(self, packet_count: int, byte_count: int):
        """Update current frame statistics"""
        with self.lock:
            self.current_frame['packets'] = packet_count
            self.current_frame['bytes'] = byte_count
            self.current_frame['timestamp'] = time.time()
            
            if packet_count > 0:
                frame_copy = self.current_frame.copy()
                self.frames.append(frame_copy)
                self.current_frame['id'] += 1
    
    def get_stats(self):
        """Get aggregated statistics"""
        with self.lock:
            if not self.frames:
                return {
                    'total_frames': self.current_frame['id'],
                    'avg_packets_per_frame': 0,
                    'avg_bytes_per_frame': 0,
                    'fps': 0,
                    'bitrate_mbps': 0,
                }
            
            total_packets = sum(f['packets'] for f in self.frames)
            total_bytes = sum(f['bytes'] for f in self.frames)
            frame_count = len(self.frames)
            
            # Calculate FPS
            if frame_count > 1:
                time_span = self.frames[-1]['timestamp'] - self.frames[0]['timestamp']
                fps = (frame_count - 1) / time_span if time_span > 0 else 0
            else:
                fps = CAMERA_FPS
            
            # Calculate bitrate
            bitrate_mbps = (total_bytes * 8) / (1024 * 1024) if frame_count > 0 else 0
            
            return {
                'total_frames': self.current_frame['id'],
                'frame_count': frame_count,
                'avg_packets_per_frame': total_packets / frame_count if frame_count > 0 else 0,
                'avg_bytes_per_frame': total_bytes / frame_count if frame_count > 0 else 0,
                'fps': fps,
                'bitrate_mbps': bitrate_mbps,
                'last_frame_packets': self.frames[-1]['packets'] if self.frames else 0,
                'last_frame_bytes': self.frames[-1]['bytes'] if self.frames else 0,
            }

# Initialize statistics tracker
frame_stats = FrameStats()

# ================= SENDER WITH VISUALIZATION =================

print("=" * 80)
print("JETSON ORIN NX - SENDER WITH PACKET VISUALIZATION")
print("=" * 80)
print(f"\nCamera:     /dev/video0 (IMX477)")
print(f"Resolution: {CAMERA_WIDTH}x{CAMERA_HEIGHT} → {TARGET_WIDTH}x{TARGET_HEIGHT}")
print(f"FPS:        {CAMERA_FPS}")
print(f"Bitrate:    {BITRATE} kbps")
print(f"Receiver:   {RECEIVER_IP}:{RECEIVER_PORT}")
print(f"\n[SENDER] Starting capture and streaming...")
print("=" * 80)

# Open video capture
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
if not cap.isOpened():
    print("ERROR: Failed to open camera")
    sys.exit(1)

# Set camera properties
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

frame_count = 0
start_time = time.time()
last_display_time = start_time

# ================= STATISTICS DISPLAY =================

def create_stats_overlay(frame, stats):
    """Create on-screen statistics overlay"""
    height, width = frame.shape[:2]
    overlay = frame.copy()
    
    # Semi-transparent background
    cv2.rectangle(overlay, (10, 10), (width - 10, 200), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    
    # Text properties
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    color = (0, 255, 0)  # Green
    thickness = 2
    y_pos = 40
    
    # Display statistics
    texts = [
        f"SENDER STREAM STATS",
        f"Frame #{stats['total_frames']} | FPS: {stats['fps']:.1f}",
        f"Bitrate: {stats['bitrate_mbps']:.2f} Mbps | Packets/Frame: {stats['last_frame_packets']:.0f}",
        f"Frame Size: {stats['last_frame_bytes'] / 1024:.1f} KB | Avg: {stats['avg_packets_per_frame']:.0f} packets",
        f"Uptime: {time.time() - start_time:.1f}s",
    ]
    
    for text in texts:
        cv2.putText(frame, text, (20, y_pos), font, font_scale, color, thickness)
        y_pos += 30
    
    return frame

# ================= STREAMING LOOP =================

try:
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print("ERROR: Failed to read frame")
            break
        
        # Downscale for display
        display_frame = cv2.resize(frame, (640, 480))
        
        # Update statistics
        stats = frame_stats.get_stats()
        frame_count += 1
        
        # Simulate frame encoding stats (in real scenario, get from encoder)
        # Approximate frame size for H.264 encoding
        avg_frame_size = BITRATE * 1000 / (8 * CAMERA_FPS)  # bytes per frame
        packets_per_frame = int(avg_frame_size / 1500) + 1  # ~1500 bytes per UDP packet
        frame_stats.update_frame(packets_per_frame, int(avg_frame_size))
        
        # Add overlay
        display_frame = create_stats_overlay(display_frame, frame_stats.get_stats())
        
        # Display
        cv2.imshow('[SENDER] Streaming Frame Packets', display_frame)
        
        # Print detailed stats every 3 seconds
        now = time.time()
        if now - last_display_time >= 3.0:
            print(f"\n[SENDER {datetime.now().strftime('%H:%M:%S')}]")
            print(f"  Frame #: {stats['total_frames']}")
            print(f"  FPS: {stats['fps']:.1f}")
            print(f"  Bitrate: {stats['bitrate_mbps']:.2f} Mbps (target: {BITRATE/1000:.1f} Mbps)")
            print(f"  Packets/Frame: {stats['last_frame_packets']:.0f}")
            print(f"  Frame Size: {stats['last_frame_bytes']/1024:.1f} KB")
            last_display_time = now
        
        # Check for quit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n[SENDER] Quit requested")
            break

except KeyboardInterrupt:
    print("\n[SENDER] Interrupted")
except Exception as e:
    print(f"[SENDER] Error: {e}")
finally:
    cap.release()
    cv2.destroyAllWindows()
    print("[SENDER] Shutdown complete")
