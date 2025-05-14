from main import FreshestFrame
import cv2

url = "rtsp://admin:Magnum%402023@10.10.50.6:554/cam/realmonitor?channel=15&subtype=0"

with FreshestFrame(url) as cam:
    while True:
        frame = cam.read()
        if frame is not None:
            cv2.imshow("Frame", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
