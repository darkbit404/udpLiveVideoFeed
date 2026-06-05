import cv2
import socket
import struct

UDP_IP = "10.42.0.249"
UDP_PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not cap.isOpened():
    print("Camera failed to open")
    exit()

print("Streaming...")

while True:

    ret, frame = cap.read()

    if not ret:
        continue

    frame = cv2.resize(frame, (320, 240))

    result, encoded = cv2.imencode(
        '.jpg',
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), 40]
    )

    if not result:
        continue

    data = encoded.tobytes()

    size = len(data)

    if size > 65000:
        continue

    # Combine header + image into ONE UDP packet
    packet = struct.pack("Q", size) + data

    sock.sendto(packet, (UDP_IP, UDP_PORT))

    cv2.imshow("Sender", frame)

    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
sock.close()
cv2.destroyAllWindows()