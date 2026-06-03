import cv2
import socket
import math
import numpy as np

# ================= CONFIG =================

UDP_IP = "10.42.0.249"   # Receiver laptop IP
UDP_PORT = 5000

MAX_DGRAM = 60000

# ================= SOCKET =================

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ================= GSTREAMER PIPELINE =================

pipeline = (
    "v4l2src device=/dev/video0 ! "
    "video/x-raw,format=GRAY8,width=1280,height=720,framerate=15/1 ! "
    "videoconvert ! "
    "appsink"
)

# ================= CAMERA =================

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("Camera failed to open")
    exit()

print("Camera opened successfully")

# ================= MAIN LOOP =================

while True:

    ret, frame = cap.read()

    if not ret:
        print("Frame read failed")
        continue

    # Resize to reduce bandwidth
    frame = cv2.resize(frame, (640, 480))

    # JPEG compression
    result, encoded = cv2.imencode(
        '.jpg',
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), 70]
    )

    if not result:
        print("JPEG encode failed")
        continue

    data = encoded.tobytes()

    # Split into UDP-safe chunks
    num_chunks = math.ceil(len(data) / MAX_DGRAM)

    # Send chunk count
    sock.sendto(str(num_chunks).encode(), (UDP_IP, UDP_PORT))

    # Send chunks
    for i in range(num_chunks):

        start = i * MAX_DGRAM
        end = start + MAX_DGRAM

        sock.sendto(data[start:end], (UDP_IP, UDP_PORT))

    # Local preview
    cv2.imshow("Jetson Sender", frame)

    if cv2.waitKey(1) == ord('q'):
        break

# ================= CLEANUP =================

cap.release()
sock.close()
cv2.destroyAllWindows()