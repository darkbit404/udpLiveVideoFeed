#!/usr/bin/env python3
import os
import sys
import time
import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

pipeline_str = os.environ.get('PIPELINE')
if not pipeline_str:
    print('No PIPELINE env var provided', file=sys.stderr)
    sys.exit(2)

try:
    pipeline = Gst.parse_launch(pipeline_str)
    pipeline.set_state(Gst.State.PLAYING)
    time.sleep(5)
    pipeline.set_state(Gst.State.NULL)
    sys.exit(0)
except Exception as e:
    print(f'Error running pipeline: {e}', file=sys.stderr)
    try:
        pipeline.set_state(Gst.State.NULL)
    except:
        pass
    sys.exit(1)
