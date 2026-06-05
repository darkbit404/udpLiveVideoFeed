#!/usr/bin/env python3
"""
Frame Tear Detection and Analysis
Monitors GStreamer pipeline in real-time to detect frame boundaries and tears
"""

import gi
import sys
import time
import struct
from collections import deque, defaultdict

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# Initialize GStreamer
Gst.init(None)

print("=" * 80)
print("FRAME TEAR DETECTION TOOL")
print("=" * 80)

class FrameAnalyzer:
    """Analyzes frames in GStreamer pipeline"""
    
    def __init__(self):
        self.frame_count = 0
        self.frame_buffer = {}
        self.frame_sizes = deque(maxlen=30)
        self.frame_times = deque(maxlen=30)
        self.frame_issues = []
    
    def analyze_buffer(self, buffer):
        """Analyze GStreamer buffer for frame information"""
        self.frame_count += 1
        
        # Get buffer metadata
        size = buffer.get_size()
        duration = buffer.duration if buffer.duration != Gst.CLOCK_TIME_NONE else 0
        timestamp = buffer.pts if buffer.pts != Gst.CLOCK_TIME_NONE else 0
        
        self.frame_sizes.append(size)
        self.frame_times.append(time.time())
        
        # Detect frame boundary issues
        if len(self.frame_sizes) > 1:
            # Check for significant size variation (could indicate frame corruption)
            avg_size = sum(self.frame_sizes) / len(self.frame_sizes)
            current_size = self.frame_sizes[-1]
            
            variation = abs(current_size - avg_size) / avg_size * 100
            if variation > 50:
                issue = {
                    'frame': self.frame_count,
                    'type': 'SIZE_ANOMALY',
                    'size': current_size,
                    'avg': avg_size,
                    'variation': variation,
                }
                self.frame_issues.append(issue)
                print(f"⚠ Frame #{self.frame_count}: Size anomaly detected (variation: {variation:.1f}%)")
        
        return {
            'frame_num': self.frame_count,
            'size': size,
            'duration': duration,
            'timestamp': timestamp,
        }
    
    def get_stats(self):
        """Get frame statistics"""
        if not self.frame_sizes:
            return {}
        
        avg_size = sum(self.frame_sizes) / len(self.frame_sizes)
        
        if len(self.frame_times) > 1:
            time_span = self.frame_times[-1] - self.frame_times[0]
            fps = (len(self.frame_times) - 1) / time_span if time_span > 0 else 0
        else:
            fps = 0
        
        return {
            'total_frames': self.frame_count,
            'avg_frame_size': avg_size,
            'fps': fps,
            'issues': len(self.frame_issues),
        }

# Create analyzer
analyzer = FrameAnalyzer()

# ================= PIPELINE WITH RTP =================

RECEIVER_IP = "10.42.0.249"
RECEIVER_PORT = 5000
BITRATE = 5000

pipeline_str = (
    f"v4l2src device=/dev/video0 ! "
    f"video/x-raw,width=1280,height=720,framerate=30/1 ! "
    f"nvvidconv ! video/x-raw(memory:NVMM),format=I420,width=1280,height=720,framerate=30/1 ! "
    f"nvv4l2h264enc bitrate={BITRATE} ! "
    f"queue ! h264parse ! rtph264pay config-interval=-1 ! "
    f"udpsink host={RECEIVER_IP} port={RECEIVER_PORT} sync=false async=false"
)

print(f"\nPipeline: {pipeline_str}\n")

try:
    pipeline = Gst.parse_launch(pipeline_str)
    
    if pipeline is None:
        print("Failed to create pipeline")
        sys.exit(1)
    
    # Create a probe to analyze frames
    def frame_probe(pad, info, user_data):
        """GStreamer probe callback for frame analysis"""
        buffer = info.get_buffer()
        if buffer:
            analyzer.analyze_buffer(buffer)
        return Gst.PadProbeReturn.OK
    
    # Add probe to h264parse output
    h264parse = pipeline.get_by_name('h264parse') if hasattr(pipeline, 'get_by_name') else None
    
    # Set pipeline to PLAYING
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("Failed to set pipeline to PLAYING")
        sys.exit(1)
    
    print("Pipeline running. Monitoring for frame issues...")
    print("Press Ctrl+C to stop.\n")
    
    # Monitor for errors
    bus = pipeline.get_bus()
    last_stats_time = time.time()
    
    while True:
        # Check for messages
        msg = bus.timed_pop_filtered(100000000, Gst.MessageType.ANY)
        
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"ERROR: {err.message}")
                if debug:
                    print(f"Debug: {debug}")
                break
            elif msg.type == Gst.MessageType.EOS:
                print("End of stream")
                break
            elif msg.type == Gst.MessageType.WARNING:
                warn, debug = msg.parse_warning()
                print(f"WARNING: {warn.message}")
        
        # Print stats every 2 seconds
        now = time.time()
        if now - last_stats_time >= 2.0:
            stats = analyzer.get_stats()
            
            print(f"\n[{time.strftime('%H:%M:%S')}] Frame Analysis:")
            print(f"  Frames Sent:      {stats.get('total_frames', 0)}")
            print(f"  Avg Frame Size:   {stats.get('avg_frame_size', 0) / 1024:.1f} KB")
            print(f"  Estimated FPS:    {stats.get('fps', 0):.1f}")
            print(f"  Issues Detected:  {stats.get('issues', 0)}")
            
            if analyzer.frame_issues:
                print(f"\n  Last Issues:")
                for issue in analyzer.frame_issues[-3:]:
                    print(f"    Frame #{issue['frame']}: {issue['type']}")
            
            last_stats_time = now
        
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n\nShutdown requested")
except Exception as e:
    print(f"Error: {e}")
finally:
    pipeline.set_state(Gst.State.NULL)
    print("\nFrame tear detection stopped")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

stats = analyzer.get_stats()
print(f"Total Frames Analyzed: {stats.get('total_frames', 0)}")
print(f"Average Frame Size:    {stats.get('avg_frame_size', 0) / 1024:.1f} KB")
print(f"Detected FPS:          {stats.get('fps', 0):.1f}")
print(f"Issues Found:          {stats.get('issues', 0)}")

if analyzer.frame_issues:
    print(f"\nFrames with Issues:")
    for issue in analyzer.frame_issues[:10]:
        if issue['type'] == 'SIZE_ANOMALY':
            print(f"  Frame #{issue['frame']}: Size {issue['size']/1024:.1f}KB (avg: {issue['avg']/1024:.1f}KB, variation: {issue['variation']:.1f}%)")

print("\nRecommendations:")
if analyzer.frame_issues:
    print("⚠ Frame irregularities detected:")
    print("  • Check encoder bitrate settings")
    print("  • Verify H.264 profile compatibility")
    print("  • Check for packet loss on network")
    print("  • Monitor WiFi band (use 5GHz)")
else:
    print("✓ No frame irregularities detected")
    print("  • Frame tears likely caused by packet loss")
    print("  • Check network diagnostics")
    print("  • Monitor receiver-side packet loss")

print("=" * 80)
