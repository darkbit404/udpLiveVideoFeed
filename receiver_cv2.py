import cv2
import socket
import struct
import numpy as np

UDP_PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))

print("Listening...")

while True:

    packet, addr = sock.recvfrom(65535)

    # First 8 bytes = size
    packed_size = packet[:8]

    frame_size = struct.unpack("Q", packed_size)[0]

    # Remaining bytes = JPEG image
    data = packet[8:]

    if len(data) != frame_size:
        print("Corrupted frame")
        continue

    npdata = np.frombuffer(data, dtype=np.uint8)

    frame = cv2.imdecode(npdata, cv2.IMREAD_COLOR)

    if frame is None:
        continue

    cv2.imshow("Receiver", frame)

    if cv2.waitKey(1) == ord('q'):
        break

sock.close()
cv2.destroyAllWindows()