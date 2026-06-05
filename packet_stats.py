#!/usr/bin/env python3
"""
Real-time Packet and Frame Statistics Tracker
Monitors RTP packets, frame integrity, and stream quality
Detects packet loss, frame tears, and latency issues
"""

import time
import threading
import queue
import socket
import struct
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import subprocess


class PacketStats:
    """Tracks RTP packet and frame statistics"""
    
    def __init__(self):
        self.total_packets = 0
        self.total_bytes = 0
        self.packets_per_second = 0
        self.bytes_per_second = 0
        self.last_seq_num = None
        self.packet_loss_count = 0
        self.frame_count = 0
        self.incomplete_frames = 0
        self.last_timestamp = time.time()
        self.start_time = time.time()
        
        # Per-frame tracking
        self.current_frame_packets = 0
        self.frame_sizes = []  # Last 30 frame sizes
        self.frame_timestamps = []  # Last 30 frame arrival times
        
        # RTT estimation
        self.latencies = []
        self.last_estimate_time = time.time()
    
    def update_packet(self, seq_num: int, payload_size: int, is_frame_end: bool = False):
        """Update stats with a new packet"""
        self.total_packets += 1
        self.total_bytes += payload_size
        self.current_frame_packets += 1
        
        # Detect packet loss (seq num gaps)
        if self.last_seq_num is not None:
            expected_seq = (self.last_seq_num + 1) & 0xFFFF
            if seq_num != expected_seq:
                gap = (seq_num - expected_seq) & 0xFFFF
                self.packet_loss_count += gap
        
        self.last_seq_num = seq_num
        
        if is_frame_end:
            self.frame_count += 1
            if self.current_frame_packets > 0:
                self.frame_sizes.append(self.current_frame_packets)
                if len(self.frame_sizes) > 30:
                    self.frame_sizes.pop(0)
            self.frame_timestamps.append(time.time())
            if len(self.frame_timestamps) > 30:
                self.frame_timestamps.pop(0)
            self.current_frame_packets = 0
    
    def mark_incomplete_frame(self):
        """Mark current frame as incomplete (torn/corrupted)"""
        self.incomplete_frames += 1
        self.current_frame_packets = 0
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        now = time.time()
        elapsed = now - self.last_timestamp
        
        if elapsed >= 1.0:
            # Calculate rates
            self.packets_per_second = self.total_packets
            self.bytes_per_second = self.total_bytes / (1024 * 1024)  # MB/s
            self.total_packets = 0
            self.total_bytes = 0
            self.last_timestamp = now
        
        avg_frame_size = sum(self.frame_sizes) / len(self.frame_sizes) if self.frame_sizes else 0
        
        # Calculate FPS
        if len(self.frame_timestamps) > 1:
            time_span = self.frame_timestamps[-1] - self.frame_timestamps[0]
            fps = (len(self.frame_timestamps) - 1) / time_span if time_span > 0 else 0
        else:
            fps = 0
        
        return {
            'packets_per_sec': self.packets_per_second,
            'mbps': self.bytes_per_second * 8,  # Convert MB/s to Mbps
            'total_frames': self.frame_count,
            'incomplete_frames': self.incomplete_frames,
            'frame_loss_pct': (self.incomplete_frames / self.frame_count * 100) if self.frame_count > 0 else 0,
            'avg_packets_per_frame': avg_frame_size,
            'estimated_fps': fps,
            'packet_loss_count': self.packet_loss_count,
            'uptime_sec': now - self.start_time,
        }


class RTPPacketSniffer:
    """Sniffs RTP packets on a UDP port"""
    
    def __init__(self, port: int, is_sender: bool = False):
        self.port = port
        self.is_sender = is_sender
        self.stats = PacketStats()
        self.running = False
        self.packet_queue = queue.Queue()
    
    def start_sniffing(self):
        """Start sniffing in background thread"""
        self.running = True
        thread = threading.Thread(target=self._sniff_loop, daemon=True)
        thread.start()
        return thread
    
    def _sniff_loop(self):
        """Background thread for packet sniffing"""
        try:
            # Use tcpdump or tshark to sniff packets
            if self.is_sender:
                # Monitor outgoing packets on port 5000
                cmd = [
                    'sudo', 'tcpdump', '-i', 'any',
                    '-n', 'udp port 5000',
                    '-c', '0',  # Infinite capture
                    '-l',  # Line-buffered output
                ]
            else:
                # Monitor incoming packets
                cmd = [
                    'sudo', 'tcpdump', '-i', 'any',
                    '-n', 'udp port 5000',
                    '-c', '0',  # Infinite capture
                    '-l',  # Line-buffered output
                ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            for line in process.stdout:
                if self.running:
                    # Parse packet info from tcpdump output
                    # Example: "... IP 10.42.0.1.12345 > 10.42.0.249.5000: UDP, length 1234"
                    if 'UDP' in line:
                        try:
                            parts = line.split()
                            # Extract payload size
                            if 'length' in parts:
                                idx = parts.index('length')
                                if idx + 1 < len(parts):
                                    payload_size = int(parts[idx + 1])
                                    self.stats.update_packet(0, payload_size)
                        except:
                            pass
        except Exception as e:
            print(f"Sniffing error: {e}", file=__import__('sys').stderr)
    
    def stop_sniffing(self):
        """Stop sniffing"""
        self.running = False
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        return self.stats.get_stats()


class FrameBufferMonitor:
    """Monitors frame buffer health and integrity"""
    
    def __init__(self):
        self.frame_buffer = {}
        self.frame_sequence = 0
        self.lock = threading.Lock()
    
    def add_packet(self, frame_id: int, packet_num: int, is_last: bool, data: bytes):
        """Add RTP packet to frame buffer"""
        with self.lock:
            if frame_id not in self.frame_buffer:
                self.frame_buffer[frame_id] = {
                    'packets': {},
                    'complete': False,
                    'timestamp': time.time(),
                }
            
            self.frame_buffer[frame_id]['packets'][packet_num] = data
            if is_last:
                self.frame_buffer[frame_id]['complete'] = True
    
    def get_frame_integrity(self, frame_id: int) -> Tuple[bool, int]:
        """
        Check if frame is complete and has all packets
        Returns: (is_complete, packet_count)
        """
        with self.lock:
            if frame_id not in self.frame_buffer:
                return False, 0
            
            frame = self.frame_buffer[frame_id]
            packets = frame['packets']
            
            # Check if packets are sequential from 0
            packet_count = len(packets)
            is_complete = frame['complete'] and all(i in packets for i in range(packet_count))
            
            return is_complete, packet_count
    
    def cleanup_old_frames(self, max_age: float = 5.0):
        """Remove frames older than max_age seconds"""
        with self.lock:
            now = time.time()
            frames_to_remove = [
                fid for fid, frame in self.frame_buffer.items()
                if now - frame['timestamp'] > max_age
            ]
            for fid in frames_to_remove:
                del self.frame_buffer[fid]
            
            return len(frames_to_remove)


def format_stats_display(stats: Dict, title: str = "STREAM STATS") -> str:
    """Format statistics for terminal display"""
    
    output = []
    output.append("=" * 70)
    output.append(f"{title:^70}")
    output.append("=" * 70)
    
    output.append(f"Uptime:              {stats.get('uptime_sec', 0):.1f}s")
    output.append(f"")
    output.append(f"FRAMES:")
    output.append(f"  Total Frames:      {stats.get('total_frames', 0)}")
    output.append(f"  Incomplete:        {stats.get('incomplete_frames', 0)}")
    
    frame_loss = stats.get('frame_loss_pct', 0)
    if frame_loss > 1:
        output.append(f"  Loss Rate:         ✗ {frame_loss:.2f}%")
    elif frame_loss > 0:
        output.append(f"  Loss Rate:         ⚠ {frame_loss:.2f}%")
    else:
        output.append(f"  Loss Rate:         ✓ {frame_loss:.2f}%")
    
    output.append(f"  Estimated FPS:     {stats.get('estimated_fps', 0):.1f}")
    output.append(f"  Avg Packets/Frame: {stats.get('avg_packets_per_frame', 0):.1f}")
    output.append(f"")
    output.append(f"NETWORK:")
    output.append(f"  Packets/sec:       {stats.get('packets_per_sec', 0)}")
    output.append(f"  Bitrate:           {stats.get('mbps', 0):.2f} Mbps")
    output.append(f"  Packet Loss:       {stats.get('packet_loss_count', 0)} packets")
    
    output.append("=" * 70)
    
    return "\n".join(output)


if __name__ == '__main__':
    # Test the packet stats module
    stats = PacketStats()
    
    # Simulate some packets
    for i in range(100):
        is_frame_end = (i % 20 == 19)
        stats.update_packet(i, 1500, is_frame_end)
    
    # Simulate some packet loss
    stats.packet_loss_count = 5
    stats.incomplete_frames = 2
    
    display = format_stats_display(stats.get_stats(), "TEST STREAM STATS")
    print(display)
