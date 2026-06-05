#!/usr/bin/env python3
"""
Receiver-Side Packet Visualization
Displays received frame-by-frame packet statistics
Detects frame tears, packet loss, and incomplete frames
"""

import cv2
import socket
import struct
import numpy as np
import threading
import time
import queue
from collections import deque, defaultdict
from datetime import datetime

# ================= CONFIG =================

LISTEN_PORT = 5000
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480

# ================= RTP PACKET STRUCTURE =================

def parse_rtp_header(packet_data):
    """Parse RTP header from UDP packet"""
    if len(packet_data) < 12:
        return None
    
    # RTP Header Format:
    # 0-1: V(2), P(1), X(1), CC(4) | M(1), PT(7)
    # 2-3: Sequence Number
    # 4-7: Timestamp
    # 8-11: SSRC
    
    byte0 = packet_data[0]
    version = (byte0 >> 6) & 0x3
    padding = (byte0 >> 5) & 0x1
    extension = (byte0 >> 4) & 0x1
    cc = byte0 & 0xf
    
    byte1 = packet_data[1]
    marker = (byte1 >> 7) & 0x1
    pt = byte1 & 0x7f
    
    seq_num = struct.unpack('!H', packet_data[2:4])[0]
    timestamp = struct.unpack('!I', packet_data[4:8])[0]
    ssrc = struct.unpack('!I', packet_data[8:12])[0]
    
    # Calculate header size
    header_size = 12 + (cc * 4)
    if extension:
        header_size += 4 + struct.unpack('!H', packet_data[header_size+2:header_size+4])[0] * 4
    
    return {
        'version': version,
        'marker': marker,
        'seq_num': seq_num,
        'timestamp': timestamp,
        'ssrc': ssrc,
        'header_size': header_size,
        'payload_size': len(packet_data) - header_size,
    }

# ================= FRAME BUFFER & STATISTICS =================

class FrameBuffer:
    """Buffers RTP packets and detects frame boundaries"""
    
    def __init__(self, max_frames=60):
        self.frames = {}
        self.frame_queue = deque(maxlen=max_frames)
        self.current_timestamp = None
        self.seq_num_history = deque(maxlen=100)
        self.lock = threading.Lock()
        self.packet_loss_count = 0
        self.incomplete_frame_count = 0
    
    def add_packet(self, rtp_info):
        """Add RTP packet to frame buffer"""
        with self.lock:
            timestamp = rtp_info['timestamp']
            seq_num = rtp_info['seq_num']
            is_frame_end = rtp_info['marker'] == 1
            
            # Track sequence numbers for loss detection
            if self.seq_num_history:
                last_seq = self.seq_num_history[-1]
                expected_seq = (last_seq + 1) & 0xFFFF
                if seq_num != expected_seq:
                    gap = (seq_num - expected_seq) & 0xFFFF
                    self.packet_loss_count += gap
            
            self.seq_num_history.append(seq_num)
            
            # Create frame entry if needed
            if timestamp not in self.frames:
                self.frames[timestamp] = {
                    'packets': [],
                    'seq_nums': [],
                    'complete': False,
                    'arrival_time': time.time(),
                }
            
            # Add packet info
            self.frames[timestamp]['packets'].append(rtp_info['payload_size'])
            self.frames[timestamp]['seq_nums'].append(seq_num)
            
            # Check if frame is complete
            if is_frame_end:
                self.frames[timestamp]['complete'] = True
                self.frame_queue.append(timestamp)
    
    def get_frame_stats(self):
        """Get statistics for the most recent frame"""
        with self.lock:
            if not self.frame_queue:
                return None
            
            timestamp = self.frame_queue[-1]
            frame_info = self.frames[timestamp]
            
            total_packets = len(frame_info['packets'])
            total_bytes = sum(frame_info['packets'])
            is_complete = frame_info['complete']
            
            # Check for gaps in sequence numbers
            seq_nums = sorted(frame_info['seq_nums'])
            has_gaps = False
            for i in range(len(seq_nums) - 1):
                if seq_nums[i+1] - seq_nums[i] != 1:
                    has_gaps = True
                    break
            
            return {
                'timestamp': timestamp,
                'total_packets': total_packets,
                'total_bytes': total_bytes,
                'complete': is_complete,
                'has_gaps': has_gaps,
                'arrival_time': frame_info['arrival_time'],
            }
    
    def get_all_stats(self):
        """Get statistics for all buffered frames"""
        with self.lock:
            stats = {
                'total_frames': len(self.frames),
                'complete_frames': sum(1 for f in self.frames.values() if f['complete']),
                'incomplete_frames': sum(1 for f in self.frames.values() if not f['complete']),
                'total_packets': sum(len(f['packets']) for f in self.frames.values()),
                'total_bytes': sum(sum(f['packets']) for f in self.frames.values()),
                'packet_loss': self.packet_loss_count,
            }
            
            # Clean up old frames
            now = time.time()
            frames_to_remove = [
                ts for ts, frame in self.frames.items()
                if now - frame['arrival_time'] > 5.0
            ]
            for ts in frames_to_remove:
                del self.frames[ts]
            
            return stats

# Initialize frame buffer
frame_buffer = FrameBuffer()

# ================= RECEIVER VISUALIZATION =================

print("=" * 80)
print("RECEIVER - PACKET VISUALIZATION")
print("=" * 80)
print(f"\nListening for RTP stream on port {LISTEN_PORT}")
print("Monitoring packet integrity and detecting frame tears...")
print("=" * 80)

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", LISTEN_PORT))
sock.settimeout(0.1)

# Packet receiving thread
packet_count = 0
last_stats_time = time.time()

def receive_packets():
    """Background thread to receive and parse RTP packets"""
    global packet_count
    
    while True:
        try:
            data, addr = sock.recvfrom(2048)
            
            # Parse RTP header
            rtp_info = parse_rtp_header(data)
            if rtp_info:
                frame_buffer.add_packet(rtp_info)
                packet_count += 1
        
        except socket.timeout:
            pass
        except Exception as e:
            print(f"Receive error: {e}")

# Start receiving thread
receiver_thread = threading.Thread(target=receive_packets, daemon=True)
receiver_thread.start()

# ================= DISPLAY LOOP =================

try:
    while True:
        # Get current frame stats
        frame_stats = frame_buffer.get_frame_stats()
        all_stats = frame_buffer.get_all_stats()
        
        # Create display frame
        display_frame = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8)
        
        # Add statistics overlay
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        color_ok = (0, 255, 0)      # Green
        color_warn = (0, 165, 255)  # Orange
        color_error = (0, 0, 255)   # Red
        y_pos = 30
        
        # Title
        cv2.putText(display_frame, "RECEIVER - PACKET STATS", (10, 20),
                   font, 0.7, color_ok, 2)
        
        # Overall statistics
        cv2.putText(display_frame, f"Status: Receiving RTP Stream", (10, y_pos),
                   font, font_scale, color_ok, thickness)
        y_pos += 25
        
        if frame_stats:
            # Frame information
            incomplete_indicator = "✗ INCOMPLETE" if not frame_stats['complete'] else "✓ COMPLETE"
            color = color_error if not frame_stats['complete'] else color_ok
            
            cv2.putText(display_frame, f"Last Frame: {incomplete_indicator}", (10, y_pos),
                       font, font_scale, color, thickness)
            y_pos += 25
            
            cv2.putText(display_frame, f"Packets in Frame: {frame_stats['total_packets']}", (10, y_pos),
                       font, font_scale, color_ok, thickness)
            y_pos += 25
            
            cv2.putText(display_frame, f"Frame Size: {frame_stats['total_bytes'] / 1024:.1f} KB", (10, y_pos),
                       font, font_scale, color_ok, thickness)
            y_pos += 25
            
            # Check for packet loss in frame
            gap_indicator = "✗ GAPS DETECTED" if frame_stats['has_gaps'] else "✓ NO GAPS"
            color = color_warn if frame_stats['has_gaps'] else color_ok
            cv2.putText(display_frame, f"Sequence: {gap_indicator}", (10, y_pos),
                       font, font_scale, color, thickness)
            y_pos += 25
        
        y_pos += 10
        
        # Aggregate statistics
        cv2.putText(display_frame, "AGGREGATE STATS:", (10, y_pos),
                   font, 0.6, color_ok, 1)
        y_pos += 25
        
        cv2.putText(display_frame, f"Total Frames Received: {all_stats['total_frames']}", (10, y_pos),
                   font, font_scale, color_ok, thickness)
        y_pos += 20
        
        cv2.putText(display_frame, f"Complete: {all_stats['complete_frames']} | Incomplete: {all_stats['incomplete_frames']}", (10, y_pos),
                   font, font_scale, color_ok, thickness)
        y_pos += 20
        
        cv2.putText(display_frame, f"Total Packets: {all_stats['total_packets']}", (10, y_pos),
                   font, font_scale, color_ok, thickness)
        y_pos += 20
        
        cv2.putText(display_frame, f"Total Data: {all_stats['total_bytes'] / (1024*1024):.2f} MB", (10, y_pos),
                   font, font_scale, color_ok, thickness)
        y_pos += 20
        
        # Packet loss indicator
        if all_stats['packet_loss'] > 0:
            cv2.putText(display_frame, f"⚠ Packet Loss: {all_stats['packet_loss']}", (10, y_pos),
                       font, font_scale, color_error, thickness)
        else:
            cv2.putText(display_frame, f"✓ No Packet Loss", (10, y_pos),
                       font, font_scale, color_ok, thickness)
        y_pos += 20
        
        # Time info
        now = time.time()
        cv2.putText(display_frame, f"Timestamp: {datetime.now().strftime('%H:%M:%S')}", (10, y_pos),
                   font, font_scale, color_ok, thickness)
        
        # Display the frame
        cv2.imshow('[RECEIVER] Packet Visualization', display_frame)
        
        # Print detailed stats every 3 seconds
        if now - last_stats_time >= 3.0:
            print(f"\n[RECEIVER {datetime.now().strftime('%H:%M:%S')}]")
            print(f"  Total Packets Received: {packet_count}")
            print(f"  Total Frames: {all_stats['total_frames']}")
            print(f"  Complete: {all_stats['complete_frames']} | Incomplete: {all_stats['incomplete_frames']}")
            print(f"  Packet Loss: {all_stats['packet_loss']}")
            if frame_stats:
                print(f"  Last Frame: {frame_stats['total_packets']} packets, {frame_stats['total_bytes']} bytes")
                if not frame_stats['complete']:
                    print(f"    ⚠ FRAME INCOMPLETE - Possible tear detected!")
                if frame_stats['has_gaps']:
                    print(f"    ⚠ SEQUENCE GAPS - Packets may be lost!")
            last_stats_time = now
        
        # Check for quit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n[RECEIVER] Quit requested")
            break

except KeyboardInterrupt:
    print("\n[RECEIVER] Interrupted")
except Exception as e:
    print(f"[RECEIVER] Error: {e}")
finally:
    sock.close()
    cv2.destroyAllWindows()
    print("[RECEIVER] Shutdown complete")
