#!/usr/bin/env python3
"""
Real-time Performance Monitor for Hardware-Encoded Streaming
Displays CPU, GPU, memory usage and network stats during streaming
"""

import subprocess
import threading
import time
import queue
import os
import platform

print("=" * 80)
print("STREAMING PERFORMANCE MONITOR")
print("=" * 80)

is_jetson = "tegra" in platform.platform().lower()

# ================= STATS COLLECTION =================

stats_queue = queue.Queue()

def collect_stats():
    """Collect system statistics"""
    while True:
        stats = {}
        
        # CPU usage
        try:
            result = subprocess.run(['top', '-bn1'], capture_output=True, text=True, timeout=2)
            for line in result.stdout.split('\n'):
                if '%Cpu(s)' in line:
                    stats['cpu'] = line.split(':')[1].strip()
                    break
        except:
            stats['cpu'] = 'N/A'
        
        # Memory usage
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=2)
            for line in result.stdout.split('\n'):
                if 'Mem:' in line:
                    parts = line.split()
                    stats['memory'] = f"{parts[2]}/{parts[1]}"
                    break
        except:
            stats['memory'] = 'N/A'
        
        # Network stats (RTP port 5000)
        try:
            result = subprocess.run(
                ['netstat', '-an'],
                capture_output=True,
                text=True,
                timeout=2
            )
            rtp_packets = 0
            for line in result.stdout.split('\n'):
                if ':5000' in line:
                    rtp_packets += 1
            stats['network'] = f"{rtp_packets} active connections"
        except:
            stats['network'] = 'N/A'
        
        # GPU stats (if Jetson)
        if is_jetson:
            try:
                result = subprocess.run(
                    ['tegrastats', '--once'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                stats['gpu'] = result.stdout.split('\n')[0]
            except:
                stats['gpu'] = 'N/A'
        
        stats_queue.put(stats)
        time.sleep(1)

# Start collection thread
stats_thread = threading.Thread(target=collect_stats, daemon=True)
stats_thread.start()

# ================= DISPLAY LOOP =================

print("\nStreaming Performance (Press Ctrl+C to stop):\n")
print("-" * 80)

try:
    while True:
        try:
            stats = stats_queue.get(timeout=2)
            
            # Clear screen (works on Linux)
            os.system('clear')
            
            print("=" * 80)
            print("STREAMING PERFORMANCE MONITOR")
            print("=" * 80)
            print()
            
            # Display stats
            if 'cpu' in stats:
                print(f"CPU Usage:        {stats['cpu']}")
            
            if 'gpu' in stats:
                print(f"GPU Stats:        {stats['gpu']}")
            
            if 'memory' in stats:
                print(f"Memory:           {stats['memory']}")
            
            if 'network' in stats:
                print(f"Network:          {stats['network']}")
            
            # Performance tips
            print("\n" + "-" * 80)
            print("OPTIMIZATION TIPS:")
            print("-" * 80)
            
            # Parse CPU usage
            if 'cpu' in stats and stats['cpu'] != 'N/A':
                cpu_parts = stats['cpu'].split(',')
                if cpu_parts:
                    try:
                        us_idle = float(cpu_parts[-1].split('%')[0])
                        us_usage = 100 - us_idle
                        
                        if us_usage > 50:
                            print("⚠ HIGH CPU USAGE - Consider:")
                            print("  • Reduce resolution or framerate")
                            print("  • Lower bitrate")
                            print("  • Check for competing processes")
                        elif us_usage < 20:
                            print("✓ CPU usage normal for hardware encoding")
                    except:
                        pass
            
            if is_jetson:
                print("✓ Jetson hardware encoding active")
                print("✓ Monitor GPU encoder load with: tegrastats")
            else:
                print("ℹ Running on Linux PC (software decoder)")
                print("ℹ Enable GPU decoding if NVIDIA GPU available")
            
            print("\nNetwork Address:")
            try:
                result = subprocess.run(
                    ["hostname", "-I"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                ips = result.stdout.strip().split()
                for ip in ips:
                    print(f"  • {ip}:5000")
            except:
                pass
            
            print("\n" + "-" * 80)
            print("Last updated: " + time.strftime("%H:%M:%S"))
            print("-" * 80)
            
        except queue.Empty:
            print("Waiting for stats...")

except KeyboardInterrupt:
    print("\n\nMonitor stopped.")
