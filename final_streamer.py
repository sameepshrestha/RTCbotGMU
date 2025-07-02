import asyncio
import json
import logging
import os
import time
import uuid
from fractions import Fraction
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel
from aiortc.contrib.media import MediaStreamTrack, MediaStreamError
from av import VideoFrame
from aiohttp import web
import cv2
import threading
import serial
import sensor_data_pb2
from collections import deque

ROOT = os.path.dirname(__file__)
HOST = "0.0.0.0"
PORT = 8080
logging.basicConfig(level=logging.INFO)
connections = {}
serial_queue = deque(maxlen=100)

async def index(request):
    content = open(os.path.join(ROOT, "index_html2.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def javascript(request):
    content = open(os.path.join(ROOT, "client_direct2.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

class SerialHandler:
    def __init__(self):
        self.ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.01)
        self.ser.flushInput()
        self._thread = threading.Thread(target=self._read_serial, daemon=True)
        self._is_stopped = threading.Event()
        self._thread.start()

    def _read_serial(self):
        last_flush_time = time.time()
        while not self._is_stopped.is_set():
            try:
                current_time = time.time()
                if current_time - last_flush_time >= 2.0:
                    self.ser.flushInput()
                    logging.info("Flushed serial input buffer")
                    last_flush_time = current_time

                if self.ser.in_waiting >= 2:
                    length_bytes = self.ser.read(2)
                    # logging.info(f"Read length bytes: {length_bytes.hex()}")
                    if len(length_bytes) == 2:
                        length = int.from_bytes(length_bytes, 'big')
                        # logging.info(f"Expected length: {length}")
                        if 0 < length <= 128:  # Increased limit
                            data = self.ser.read(length)
                            # logging.info(f"Read data: {len(data)} bytes")
                            if len(data) == length:
                                msg = sensor_data_pb2.SensorData()
                                msg.ParseFromString(data)
                                # Temporary: Skip has_imu check
                                # logging.info(f"Parsed SensorData: sequence={msg.sequence}, timestamp={msg.timestamp:.3f}, "
                                #              f"lat={msg.gps.lat:.4f}, lon={msg.gps.lon:.4f}, alt={msg.gps.alt:.1f}")
                                serial_queue.append(msg.SerializeToString())
                                # logging.info(f"Added to serial_queue, size: {len(serial_queue)}")
                            else:
                                # logging.warning(f"Incomplete data: expected {length}, got {len(data)}")
                                self.ser.flushInput()
                        else:
                            logging.warning(f"Invalid length: {length}")
                            self.ser.flushInput()
                    else:
                        logging.warning("Failed to read length bytes")
                        self.ser.flushInput()
                time.sleep(0.0001)
            except Exception as e:
                logging.warning(f"Serial read error: {e}")
                self.ser.flushInput()
                time.sleep(0.01)

    def send_command(self, cmd):
        try:
            encoded = cmd.SerializeToString()
            length = len(encoded)
            self.ser.write(length.to_bytes(2, 'big') + encoded)
            logging.info(f"Sending {length} bytes over serial: {encoded.hex()}")
            logging.info(f"Sent Command: sequence={cmd.sequence}, type={cmd.type}, value={cmd.value:.2f}")
        except Exception as e:
            logging.error(f"Serial write error: {e}")

    def stop(self):
        self._is_stopped.set()
        self._thread.join(timeout=1)
        self.ser.close()

class RobustPiCameraTrack(MediaStreamTrack):
    """
    A more robust video track that includes a startup health check
    and dedicated thread management for frame reading.
    """
    kind = "video"

    def __init__(self):
        super().__init__()
        self.cap = None
        self._frame = None
        self._is_stopped = threading.Event()
        self._thread = None
        self.is_healthy = False
        self._start_time = time.time()

    def start(self):
        """Initializes the camera and starts the background reading thread."""
        logging.info("ROBUST: Attempting to open camera...")
        pipeline = ("libcamerasrc ! video/x-raw,format=NV12,width=640,height=480,framerate=30/1 ! appsink drop=true")
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        
        if not self.cap.isOpened():
            logging.error("ROBUST: Camera failed to open at cv2.VideoCapture.")
            return

        # --- Health Check ---
        # Try to read the first frame to confirm the pipeline is actually working.
        ret, frame = self.cap.read()
        if not ret or frame is None:
            logging.error("ROBUST: Health check FAILED. Could not read the first frame.")
            self.cap.release()
            self.cap = None
            return

        logging.info("ROBUST: Health check PASSED. First frame read successfully.")
        self._frame = frame
        self.is_healthy = True
        
        # Start the dedicated reader thread
        self._thread = threading.Thread(target=self._read_frames, daemon=True)
        self._thread.start()

    def _read_frames(self):
        """The function that runs in the background to continuously read frames."""
        while not self._is_stopped.is_set():
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    self._frame = frame
                else:
                    logging.warning("ROBUST: Reader thread failed to read frame.")
                    # Allow a small sleep to prevent busy-looping on error
                    time.sleep(0.01)
            else:
                break
        logging.info("ROBUST: Reader thread has stopped.")
    
    async def recv(self):
        """Called by aiortc to get the next frame."""
        if self._is_stopped.is_set():
            raise MediaStreamError

        # If the camera isn't healthy, send black frames
        if not self.is_healthy or self._frame is None:
            logging.warning("ROBUST: Sending black frame because camera is not healthy.")
            black_frame = VideoFrame(width=640, height=480)
            await asyncio.sleep(1/30) # Maintain framerate
            return black_frame

        # Wait for a new frame from the reader thread
        # This is a simplified approach; a more complex one would use an asyncio.Queue
        # but for now we'll just use the latest available frame.
        current_frame = self._frame

        frame = VideoFrame.from_ndarray(current_frame, format="nv12")
        
        # This PTS logic is simple but effective for this test
        pts = int((time.time() - self._start_time) * 90000)
        frame.pts = pts
        frame.time_base = Fraction(1, 90000)

        await asyncio.sleep(1 / 30) # Regulate framerate
        return frame

    def stop(self):
        """Signals the reader thread to stop and releases resources."""
        if not self._is_stopped.is_set():
            logging.info("ROBUST: Stopping camera track...")
            self._is_stopped.set()
            if self._thread:
                self._thread.join(timeout=1) # Wait for the thread to exit
            if self.cap:
                self.cap.release()
            logging.info("ROBUST: Camera track fully stopped.")

async def index(request):
    content = open(os.path.join(ROOT, "index_html2.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client_direct2.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pc_id = f"pc-{uuid.uuid4()}"
    video_track = RobustPiCameraTrack()
    video_track.start()
    serial_handler = SerialHandler()
    data_channel = pc.createDataChannel("protobuf", ordered=False, maxRetransmits=0)
    connections[pc_id] = (pc, video_track, serial_handler)

    @data_channel.on("message")
    def on_message(message):
        try:
            cmd = sensor_data_pb2.Command()
            cmd.ParseFromString(message)
            serial_handler.send_command(cmd)
            logging.info(f"Received Command: type={cmd.type}, value={cmd.value:.2f}")
        except Exception as e:
            logging.error(f"Data channel error on message receive: {e}")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logging.info(f"Connection state is {pc.connectionState}")
        if pc.connectionState in ("failed", "closed", "disconnected"):
            if pc_id in connections:
                pc_ref, track_ref, serial_ref = connections.pop(pc_id)
                track_ref.stop()
                serial_ref.stop()
                await pc_ref.close()
                logging.info(f"Closed and cleaned up connection {pc_id}")

    async def send_sensor_data_after_open():
        logging.info("Waiting for data channel to open...")
        opened = asyncio.Future()

        @data_channel.on("open")
        def on_open():
            logging.info("Data channel opened!")
            if not opened.done():
                opened.set_result(True)

        try:
            await asyncio.wait_for(opened, timeout=15.0)
        except asyncio.TimeoutError:
            logging.error("Data channel did not open within 15 seconds")
            return

        logging.info("Sending sensor data...")
        while pc.connectionState == "connected":
            if serial_queue:
                data = serial_queue.popleft()
                try:
                    data_channel.send(data)
                    # logging.info(f"Sent SensorData to data channel, queue size: {len(serial_queue)}")
                except Exception as e:
                    logging.warning(f"Data channel send error: {e}")
                    break
            else:
                logging.debug("serial_queue empty")
            await asyncio.sleep(0.05)

    start_time = time.time()
    pc.addTrack(video_track)
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    logging.info(f"WebRTC setup took {time.time() - start_time:.2f}s")
    asyncio.create_task(send_sensor_data_after_open())

    return web.Response(
        content_type="application/json",
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    )

async def on_shutdown(app):
    for pc, track, serial_handler in list(connections.values()):
        track.stop()
        serial_handler.stop()
        await pc.close()
    connections.clear()

app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_get("/client_direct.js", javascript)
app.router.add_post("/offer", offer)
app.router.add_static("/public", ROOT)
web.run_app(app, host=HOST, port=PORT)