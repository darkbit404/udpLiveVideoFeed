#!/usr/bin/env python3
"""
Stream Diagnostics Tool
Comprehensive real-time analysis of sender-receiver stream quality
Detects frame tears, packet loss, latency issues, and bandwidth problems
"""

import socket
import struct
import subprocess
import threading
import time
import sys
from collections import deque, defaultdict
from datetime import datetime

# ================= CONFIGURATION =================

SENDER_IP = "10.42.0.1"      # Jetson IP
RECEIVER_IP = "10.42.0.249"  # Laptop IP
STREAM_PORT = 5000
SAMPLE_DURATION = 5  # seconds
CHECK_INTERVAL = 1   # seconds

# ================= NETWORK DIAGNOSTICS =================

class NetworkDiagnostics:
    """Diagnose network conditions"""
    
    @staticmethod
    def check_connectivity(ip: str) -> bool:
        """Check if IP is reachable"""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '1', ip],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def measure_latency(ip: str) -> float:
        """Measure RTT latency to IP"""
        try:
            result = subprocess.run(
                ['ping', '-c', '4', '-W', '1', ip],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            # Parse average latency
            for line in result.stdout.split('\n'):
                if 'min/avg/max' in line:
                    parts = line.split('=')[1].split('/')
                    return float(parts[1])  # avg
            
            return None
        except:
            return None
    
    @staticmethod
    def get_wifi_stats() -> dict:
        """Get WiFi signal strength and band"""
        try:
            result = subprocess.run(
                ['iwconfig'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            stats = {}
            for line in result.stdout.split('\n'):
                if 'Signal level' in line or 'Frequency' in line:
                    stats['wifi_info'] = line.strip()
            
            return stats
        except:
            return {}
    
    @staticmethod
    def get_interface_stats(interface: str = 'wlan0') -> dict:
        """Get network interface statistics"""
        try:
            result = subprocess.run(
                ['ethtool', '-S', interface],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            stats = {}
            for line in result.stdout.split('\n'):
                if 'rx_errors' in line or 'tx_errors' in line or 'dropped' in line:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        try:
                            value = int(parts[1].strip())
                            stats[key] = value
                        except:
                            pass
            
            return stats
        except:
            return {}

# ================= RTP STREAM ANALYZER =================

class RTPStreamAnalyzer:
    """Analyzes RTP stream characteristics"""
    
    def __init__(self, port: int = STREAM_PORT):
        self.port = port
        self.packets = deque()
        self.frames = defaultdict(dict)
        self.running = False
        self.lock = threading.Lock()
    
    def start_capture(self, duration: int = SAMPLE_DURATION):
        """Capture RTP packets for analysis"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", self.port))
            sock.settimeout(0.5)
            
            print(f"\n[ANALYZING] Capturing packets on port {self.port} for {duration}s...")
            
            start_time = time.time()
            packet_count = 0
            
            while time.time() - start_time < duration and self.running:
                try:
                    data, addr = sock.recvfrom(2048)
                    
                    if len(data) >= 12:
                        # Parse RTP header
                        rtp_info = self._parse_rtp(data, addr)
                        with self.lock:
                            self.packets.append(rtp_info)
                        packet_count += 1
                except socket.timeout:
                    pass
            
            sock.close()
            
            return packet_count
        except Exception as e:
            print(f"Capture error: {e}")
            return 0
    
    def _parse_rtp(self, data: bytes, addr: tuple) -> dict:
        """Parse RTP packet"""
        byte0 = data[0]
        byte1 = data[1]
        
        marker = (byte1 >> 7) & 0x1
        seq_num = struct.unpack('!H', data[2:4])[0]
        timestamp = struct.unpack('!I', data[4:8])[0]
        
        return {
            'timestamp': time.time(),
            'src_ip': addr[0],
            'marker': marker,
            'seq_num': seq_num,
            'rtp_ts': timestamp,
            'size': len(data),
            'payload_size': len(data) - 12,
        }
    
    def analyze(self) -> dict:
        """Analyze captured packets"""
        with self.lock:
            packets = list(self.packets)
        
        if not packets:
            return {
                'status': 'No packets captured',
                'packet_count': 0,
            }
        
        # Basic statistics
        total_packets = len(packets)
        total_bytes = sum(p['size'] for p in packets)
        
        # Sequence number analysis
        seq_nums = [p['seq_num'] for p in packets]
        packet_loss = 0
        for i in range(len(seq_nums) - 1):
            expected = (seq_nums[i] + 1) & 0xFFFF
            if seq_nums[i+1] != expected:
                packet_loss += (seq_nums[i+1] - expected) & 0xFFFF
        
        # Frame detection (marker bit)
        frame_count = sum(1 for p in packets if p['marker'] == 1)
        
        # Timestamp and timing analysis
        if len(packets) > 1:
            time_span = packets[-1]['timestamp'] - packets[0]['timestamp']
            pkt_rate = total_packets / time_span if time_span > 0 else 0
            bitrate = (total_bytes * 8 / 1000000) / time_span if time_span > 0 else 0
        else:
            pkt_rate = 0
            bitrate = 0
        
        # Packet size analysis
        sizes = [p['payload_size'] for p in packets]
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        max_size = max(sizes) if sizes else 0
        
        return {
            'status': 'OK' if packet_loss == 0 else f'⚠ Packet Loss Detected',
            'packet_count': total_packets,
            'frame_count': frame_count,
            'total_bytes': total_bytes,
            'packet_loss': packet_loss,
            'packet_rate_pps': pkt_rate,
            'bitrate_mbps': bitrate,
            'avg_packet_size': avg_size,
            'max_packet_size': max_size,
            'packets_per_frame': total_packets / frame_count if frame_count > 0 else 0,
        }

# ================= MAIN DIAGNOSTICS =================

def run_diagnostics():
    """Run complete stream diagnostics"""
    
    print("=" * 80)
    print("STREAM DIAGNOSTICS TOOL")
    print("=" * 80)
    
    # Network connectivity
    print("\n[1] NETWORK CONNECTIVITY")
    print("-" * 80)
    
    sender_reachable = NetworkDiagnostics.check_connectivity(SENDER_IP)
    receiver_reachable = NetworkDiagnostics.check_connectivity(RECEIVER_IP)
    
    print(f"Sender ({SENDER_IP}):     {'✓ Reachable' if sender_reachable else '✗ Not reachable'}")
    print(f"Receiver ({RECEIVER_IP}): {'✓ Reachable' if receiver_reachable else '✗ Not reachable'}")
    
    if not (sender_reachable and receiver_reachable):
        print("\n⚠ WARNING: Not all devices are reachable!")
        return
    
    # Latency measurement
    print("\n[2] LATENCY ANALYSIS")
    print("-" * 80)
    
    sender_latency = NetworkDiagnostics.measure_latency(SENDER_IP)
    receiver_latency = NetworkDiagnostics.measure_latency(RECEIVER_IP)
    
    if sender_latency:
        print(f"Sender Latency:     {sender_latency:.2f} ms")
    else:
        print(f"Sender Latency:     N/A")
    
    if receiver_latency:
        print(f"Receiver Latency:   {receiver_latency:.2f} ms")
    else:
        print(f"Receiver Latency:   N/A")
    
    # WiFi diagnostics
    print("\n[3] WIFI DIAGNOSTICS")
    print("-" * 80)
    
    wifi_stats = NetworkDiagnostics.get_wifi_stats()
    if wifi_stats:
        print(f"WiFi Info: {wifi_stats.get('wifi_info', 'N/A')}")
    else:
        print("WiFi Info: Unable to retrieve")
    
    # Interface statistics
    print("\n[4] NETWORK INTERFACE ERRORS")
    print("-" * 80)
    
    iface_stats = NetworkDiagnostics.get_interface_stats()
    if iface_stats:
        for key, value in iface_stats.items():
            if value > 0:
                print(f"⚠ {key}: {value}")
            else:
                print(f"✓ {key}: {value}")
    else:
        print("No interface errors detected (or unable to retrieve stats)")
    
    # RTP Stream analysis
    print("\n[5] RTP STREAM ANALYSIS")
    print("-" * 80)
    print(f"Listening on port {STREAM_PORT} for {SAMPLE_DURATION} seconds...")
    
    analyzer = RTPStreamAnalyzer(STREAM_PORT)
    analyzer.running = True
    
    try:
        packet_count = analyzer.start_capture(SAMPLE_DURATION)
        
        if packet_count == 0:
            print("⚠ No RTP packets received!")
            print("   Make sure the sender is streaming and receiver is listening")
        else:
            analysis = analyzer.analyze()
            
            print(f"\nStatus:             {analysis.get('status', 'Unknown')}")
            print(f"Packets Captured:   {analysis.get('packet_count', 0)}")
            print(f"Frames Detected:    {analysis.get('frame_count', 0)}")
            print(f"Total Data:         {analysis.get('total_bytes', 0) / (1024*1024):.2f} MB")
            print(f"Packet Loss:        {analysis.get('packet_loss', 0)} packets")
            print(f"Packet Rate:        {analysis.get('packet_rate_pps', 0):.0f} pkt/s")
            print(f"Bitrate:            {analysis.get('bitrate_mbps', 0):.2f} Mbps")
            print(f"Avg Packet Size:    {analysis.get('avg_packet_size', 0):.0f} bytes")
            print(f"Packets/Frame:      {analysis.get('packets_per_frame', 0):.1f}")
            
            # Recommendations
            print("\n[6] RECOMMENDATIONS")
            print("-" * 80)
            
            if analysis.get('packet_loss', 0) > 0:
                print("⚠ PACKET LOSS DETECTED - Frame tears likely!")
                print("  • Check network congestion (use 5GHz band)")
                print("  • Reduce bitrate or resolution")
                print("  • Check for WiFi interference (2.4GHz channels)")
                print("  • Verify sender and receiver are on same network")
            elif analysis.get('bitrate_mbps', 0) > 5:
                print("⚠ HIGH BITRATE - May cause packet loss on weak networks")
                print("  • Consider reducing bitrate in sender.py")
                print("  • Ensure 5GHz WiFi connection")
            else:
                print("✓ Stream appears healthy")
                print("  • Monitor for packet loss over time")
                print("  • Check for frame tears on receiver display")
    
    except KeyboardInterrupt:
        print("\n⚠ Interrupted by user")
    finally:
        analyzer.running = False
    
    print("\n" + "=" * 80)
    print(f"Diagnostics completed at {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 80)

if __name__ == '__main__':
    run_diagnostics()
