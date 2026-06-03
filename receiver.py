import cv2
import socket
import numpy as np

UDP_PORT = 5000
MAX_DGRAM = 60000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))

print("Listening...")

while True:

    # Receive number of chunks
    packet, _ = sock.recvfrom(1024)

    try:
        num_chunks = int(packet.decode())
    except:
        continue

    data = b''

    # Receive all chunks
    for _ in range(num_chunks):

        packet, _ = sock.recvfrom(MAX_DGRAM)

        data += packet

    npdata = np.frombuffer(data, dtype=np.uint8)

    frame = cv2.imdecode(npdata, cv2.IMREAD_GRAYSCALE)

    if frame is None:
        continue

    cv2.imshow("Receiver", frame)

    if cv2.waitKey(1) == ord('q'):
        break

sock.close()
cv2.destroyAllWindows()