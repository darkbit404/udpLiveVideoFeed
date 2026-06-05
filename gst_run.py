#!/usr/bin/env python3
"""
GStreamer Pipeline Runner (Subprocess Helper)
Executes a GStreamer pipeline from PIPELINE environment variable.
Runs indefinitely until error or Ctrl+C.
"""

import os
import sys
import time
import signal
import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

Gst.init(None)

pipeline_str = os.environ.get('PIPELINE')
if not pipeline_str:
    print('No PIPELINE env var provided', file=sys.stderr)
    sys.exit(2)

try:
    pipeline = Gst.parse_launch(pipeline_str)
    if pipeline is None:
        print('Failed to parse pipeline', file=sys.stderr)
        sys.exit(1)
    
    # Set to PLAYING
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print('Failed to set pipeline to PLAYING state', file=sys.stderr)
        sys.exit(1)
    
    print(f"Pipeline PLAYING. Running indefinitely...", file=sys.stderr)
    sys.stderr.flush()
    
    # Monitor bus for errors and keep pipeline running
    bus = pipeline.get_bus()
    
    while True:
        # Poll bus with 100ms timeout
        msg = bus.timed_pop_filtered(100000000, Gst.MessageType.ANY)
        
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f'ERROR: {err.message}', file=sys.stderr)
                if debug:
                    print(f'DEBUG: {debug}', file=sys.stderr)
                pipeline.set_state(Gst.State.NULL)
                sys.exit(1)
            elif msg.type == Gst.MessageType.EOS:
                print('End of stream', file=sys.stderr)
                pipeline.set_state(Gst.State.NULL)
                sys.exit(0)
            elif msg.type == Gst.MessageType.WARNING:
                warn, debug = msg.parse_warning()
                print(f'WARNING: {warn.message}', file=sys.stderr)
        
        time.sleep(0.01)

except KeyboardInterrupt:
    print('\nInterrupted', file=sys.stderr)
    pipeline.set_state(Gst.State.NULL)
    sys.exit(0)
except Exception as e:
    print(f'Error running pipeline: {e}', file=sys.stderr)
    try:
        pipeline.set_state(Gst.State.NULL)
    except:
        pass
    sys.exit(1)
