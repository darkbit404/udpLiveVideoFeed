# Packet Visualization and Frame Tear Detection Tools

## Overview

A comprehensive suite of tools to visualize and diagnose frame tears and packet loss in real-time during UDP video streaming.

## Tools Available

### 1. **sender_visualization.py** 
**Location:** On Jetson (sender side)
**Purpose:** Shows frame-by-frame statistics as frames are encoded and transmitted

**What it displays:**
- Live camera feed with overlay statistics
- Current frame number and total frames sent
- FPS (frames per second)
- Bitrate (Mbps) vs target bitrate
- Packets per frame
- Frame size in kilobytes
- Uptime counter

**Run with:**
```bash
python3 sender_visualization.py
```

**Key Metrics:**
- If FPS < 30: Encoder bottleneck or low light
- If Bitrate varies: Frame size inconsistent (causes packet loss)
- If Packets/Frame > 40: Large frames (more network vulnerability)

---

### 2. **receiver_visualization.py**
**Location:** On Laptop (receiver side)  
**Purpose:** Shows exact packets arriving and detects frame completeness

**What it displays:**
- Status of last received frame (✓ COMPLETE or ✗ INCOMPLETE)
- Packet count per frame
- Frame size in kilobytes
- Sequence number gaps (✓ NO GAPS or ✗ GAPS DETECTED)
- Aggregate statistics (total frames, complete/incomplete counts)
- Packet loss count
- Real-time timestamp

**Run with:**
```bash
python3 receiver_visualization.py
```

**Frame Status Meanings:**
| Status | Meaning | Impact |
|--------|---------|--------|
| ✓ COMPLETE | All packets for frame arrived | Frame displays correctly |
| ✗ INCOMPLETE | Missing packets | **Frame will show TEAR** |
| ✓ NO GAPS | Sequence numbers consecutive | Perfect packet delivery |
| ✗ GAPS DETECTED | Missing sequence numbers | **Packets lost in network** |

---

### 3. **stream_diagnostics.py**
**Location:** Either machine
**Purpose:** Network analysis and stream quality assessment

**What it analyzes:**
- Network connectivity (ping tests)
- Round-trip latency to sender/receiver
- WiFi signal quality and band (2.4GHz vs 5GHz)
- Network interface errors
- RTP packet characteristics:
  - Packet loss count
  - Bitrate measurement
  - Packets per frame
  - Frame count

**Run with:**
```bash
python3 stream_diagnostics.py
```

**How to interpret:**
- Packet Loss > 0 → Frames will have tears
- Bitrate > 5 Mbps → May exceed network capacity
- Latency > 50ms → Network congestion

---

### 4. **frame_tear_detector.py**
**Location:** On Jetson (sender side)
**Purpose:** Analyzes frame encoding characteristics to detect anomalies

**What it detects:**
- Frame size anomalies (sudden increases/decreases)
- Frame boundary issues
- Encoder output irregularities

**Run with:**
```bash
python3 frame_tear_detector.py
```

**Findings:**
- SIZE_ANOMALY: Frame size varies by >50% from average (indicates encoding issues)

---

### 5. **packet_stats.py**
**Location:** Utility module
**Purpose:** Core statistics tracking library used by other tools

**Features:**
- RTP packet tracking
- Frame boundary detection
- Packet loss calculation
- Frame buffer monitoring
- Statistics formatting

---

### 6. **visualize_packets.py**
**Location:** On either machine
**Purpose:** Interactive menu to run visualization tools

**Run with:**
```bash
python3 visualize_packets.py
```

Provides guided setup and launch of all visualization tools.

---

## Recommended Setup

### For Simultaneous Monitoring (Best for Troubleshooting)

**On Jetson (3 terminals):**
```bash
# Terminal 1: Watch what's being sent
python3 sender_visualization.py

# Terminal 2: Monitor frame encoding
python3 frame_tear_detector.py

# Terminal 3: Run network diagnostics (after sender starts)
python3 stream_diagnostics.py
```

**On Laptop (2 terminals):**
```bash
# Terminal 1: Watch what's being received
python3 receiver_visualization.py

# Terminal 2: Run network diagnostics (after sender starts)
python3 stream_diagnostics.py
```

### Interpretation Guide

#### Scenario 1: Perfect Stream
```
SENDER:
  ✓ FPS: 30.0
  ✓ Bitrate: 5.00 Mbps
  ✓ Packets/Frame: ~32

RECEIVER:
  ✓ COMPLETE frames
  ✓ NO GAPS
  ✓ Packet Loss: 0

DIAGNOSTICS:
  ✓ No packet loss
  ✓ Bitrate matches target
```

#### Scenario 2: Frame Tears Due to Packet Loss
```
SENDER:
  ✓ FPS: 30.0
  ✓ Bitrate: 5.00 Mbps
  ✓ Looks fine

RECEIVER:
  ✗ INCOMPLETE frames
  ✗ GAPS DETECTED
  ✗ Packet Loss: 15 packets

DIAGNOSTICS:
  ⚠ High packet loss rate
  ⚠ Network interference detected
  ⚠ On 2.4GHz WiFi (should be 5GHz)

ACTION:
  1. Switch to 5GHz WiFi
  2. Reduce bitrate
  3. Check WiFi interference
```

#### Scenario 3: Encoder Issues
```
SENDER:
  ✓ FPS: 15-25 (LOW)
  ⚠ Bitrate: variable
  ⚠ Packets/Frame: varies widely

RECEIVER:
  Fewer total frames arriving

FRAME_TEAR_DETECTOR:
  ⚠ SIZE_ANOMALY detected

ACTION:
  1. Check camera lighting
  2. Reduce resolution
  3. Lower target bitrate
  4. Verify hardware encoder
```

---

## Quick Troubleshooting

### "Receiver shows ✗ INCOMPLETE frames"
**Cause:** Missing packets in network
**Check:**
1. Run `stream_diagnostics.py` on both sides
2. Look for "Packet Loss" in diagnostics output
3. Check WiFi band: should be 5GHz

**Fix:**
```bash
# Force 5GHz (Linux)
nmcli con modify <connection_name> wifi.band 'a'
nmcli con up <connection_name>

# Reduce bitrate in sender.py
BITRATE = 3000  # From 5000
```

### "Receiver shows ✗ GAPS DETECTED"
**Cause:** RTP sequence numbers show dropped packets
**Check:**
1. WiFi signal strength
2. Network interface errors: `stream_diagnostics.py`
3. Bitrate too high for network

**Fix:**
1. Move receiver closer to WiFi router
2. Switch to 5GHz band
3. Reduce resolution/framerate

### "Frame tears but no diagnostics errors"
**Cause:** Encoder or frame boundary issue
**Check:**
1. Run `frame_tear_detector.py` on sender
2. Look for "SIZE_ANOMALY" warnings
3. Check camera focus/lighting

**Fix:**
1. Reduce bitrate gradually
2. Test with lower resolution
3. Verify camera hardware

---

## Real-time Monitoring Dashboard

To create a comprehensive dashboard, run in separate terminals:

```bash
# Terminal 1 (Jetson - Sender):
watch -n 1 'echo "=== SENDER ===" && python3 sender_visualization.py'

# Terminal 2 (Jetson - Analysis):
watch -n 3 'python3 stream_diagnostics.py'

# Terminal 3 (Laptop - Receiver):
python3 receiver_visualization.py

# Terminal 4 (Laptop - Diagnostics):
watch -n 3 'python3 stream_diagnostics.py'
```

---

## Performance Tuning Based on Diagnostics

### If Packet Loss > 0:

1. **Check Network Band:**
   ```bash
   iwconfig  # Look for "Frequency"
   # Should show: ~5.0 GHz (5GHz) not ~2.4 GHz
   ```

2. **Reduce Bitrate:**
   - Edit `sender.py`: `BITRATE = 3000` (was 5000)

3. **Reduce Resolution:**
   - Edit `sender.py`: `TARGET_WIDTH = 960`, `TARGET_HEIGHT = 540`

4. **Lower Framerate:**
   - Edit `sender.py`: `CAMERA_FPS = 15` (was 30)

### If FPS < 30 (Sender Side):

1. Check encoder load: `tegrastats` (on Jetson)
2. Reduce bitrate to ease encoder
3. Check lighting (dark scenes = more bits needed)

### If Latency > 50ms:

1. Use wired Ethernet if possible
2. Reduce distance between sender/receiver
3. Check for WiFi interference (use 5GHz band)

---

## Files Summary

| File | Purpose | Run Location | Frequency |
|------|---------|--------------|-----------|
| `sender_visualization.py` | Show transmitted frames | Jetson | Continuous |
| `receiver_visualization.py` | Show received frames | Laptop | Continuous |
| `stream_diagnostics.py` | Network analysis | Either | Every 30-60s |
| `frame_tear_detector.py` | Encoder analysis | Jetson | Continuous |
| `packet_stats.py` | Statistics library | (imported) | - |
| `visualize_packets.py` | Interactive launcher | Either | Once |

---

## Key Insights

1. **Frame tears always come from packet loss** - If receiver shows ✗ INCOMPLETE, packets were lost in network
2. **Packet loss is usually a network problem** - Check WiFi band, bitrate, and interference
3. **Monitor both sides simultaneously** - Sender stats tell you what was sent; receiver stats show what arrived
4. **5GHz is essential** - 2.4GHz networks are too congested for reliable video
5. **Bitrate must match network capacity** - 5 Mbps requires clean 5GHz or wired connection

---

## Commands Reference

```bash
# Run sender visualization
python3 sender_visualization.py

# Run receiver visualization  
python3 receiver_visualization.py

# Run diagnostics
python3 stream_diagnostics.py

# Run frame tear detector
python3 frame_tear_detector.py

# Interactive menu
python3 visualize_packets.py

# Check WiFi band (Linux)
iwconfig | grep Frequency

# Force 5GHz (Linux)
nmcli con modify <name> wifi.band 'a' && nmcli con up <name>

# Check interface errors
ethtool -S wlan0 | grep -i error

# Monitor Jetson GPU (if available)
tegrastats
```
