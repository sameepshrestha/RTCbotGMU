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
import robot_messages_pb2
from collections import deque
import struct

ROOT = os.path.dirname(__file__)
HOST = "0.0.0.0"
PORT = 8080
logging.basicConfig(level=logging.INFO)
connections = {}
serial_queue = deque(maxlen=200)

async def index(request):
    content = open(os.path.join(ROOT, "index_html.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def javascript(request):
    content = open(os.path.join(ROOT, "client_direct.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

def parse_data(frame):
    """Parses a 11-byte data frame from the WitMotion sensor."""
    if len(frame) != 11 or frame[0] != 0x55:
        return None
    checksum_calculated = sum(frame[0:10]) & 0xff
    if checksum_calculated != frame[10]:
        return None # Checksum failed
    data_type = frame[1]
    raw_data = struct.unpack('<hhhh', frame[2:10])
    if data_type == 0x51:
        acc_x = (raw_data[0] / 32768.0) * 16
        acc_y = (raw_data[1] / 32768.0) * 16
        acc_z = (raw_data[2] / 32768.0) * 16
        return "Acceleration", {"accel_x": acc_x, "accel_y": acc_y, "accel_z": acc_z}
    elif data_type == 0x52:
        gyro_x = (raw_data[0] / 32768.0) * 2000
        gyro_y = (raw_data[1] / 32768.0) * 2000
        gyro_z = (raw_data[2] / 32768.0) * 2000
        return "Angular Velocity", {"gyro_x": gyro_x, "gyro_y": gyro_y, "gyro_z": gyro_z}
    elif data_type == 0x53:
        roll = (raw_data[0] / 32768.0) * 180
        pitch = (raw_data[1] / 32768.0) * 180
        yaw = (raw_data[2] / 32768.0) * 180
        return "Angle", {"roll": roll, "pitch": pitch, "yaw": yaw}
    return None

# =======================================================
#    CORRECTED ARDUINO HANDLER (Use this in your Python)
# =======================================================
# class ArduinoHandler:
#     """A dedicated handler using efficient blocking reads."""
#     def __init__(self, data_queue):
#         # IMPORTANT: Double-check this device name!
#         self.ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
#         self.ser.flushInput()
#         self.data_queue = data_queue
#         self._is_stopped = threading.Event()
#         self._thread = threading.Thread(target=self._read_serial, daemon=True)
#         self._thread.start()

#     def _read_serial(self):
#         """Producer thread that efficiently waits for data."""
#         logging.info("Arduino reader thread started (using blocking reads).")
#         while not self._is_stopped.is_set():
#             try:
#                 # This is the key change. self.ser.read(2) will now WAIT
#                 # for 2 bytes to arrive, using almost no CPU.
#                 length_bytes = self.ser.read(2)
                
#                 # If read(2) returns after the timeout, it will be empty.
#                 if len(length_bytes) == 2:
#                     length = int.from_bytes(length_bytes, 'big')
#                     if 0 < length <= 128:
#                         # Now read the full message payload
#                         data = self.ser.read(length)
#                         if len(data) == length:
#                             msg = robot_messages_pb2.RobotStatus()
#                             msg.ParseFromString(data)
#                             self.data_queue.append(b'R' + msg.SerializeToString())
#                             logging.info(f"Queued RobotStatus message. Queue size: {len(self.data_queue)}")
#                         else:
#                             logging.warning("Arduino incomplete data read (timeout).")
#                     else:
#                         logging.warning(f"Arduino invalid length received: {length}")
                
#             except serial.SerialException as e:
#                 logging.error(f"Arduino serial port error: {e}")
#                 time.sleep(2) # Wait before trying to read again
#             except Exception as e:
#                 logging.warning(f"Arduino read thread error: {e}")
#                 time.sleep(1)

#     def send_command(self, cmd):
#         """Sends a command protobuf to the Arduino."""
#         try:
#             encoded = cmd.SerializeToString()
#             length = len(encoded)
#             self.ser.write(length.to_bytes(2, 'big') + encoded)
#         except Exception as e:
#             logging.error(f"Arduino serial write error: {e}")

#     def stop(self):
#         """Cleanly stops the thread and closes the serial port."""
#         self._is_stopped.set()
#         self._thread.join(timeout=1)
#         self.ser.close()
#         logging.info("Arduino handler stopped.")

# class SensorHandler:
#     def __init__(self, data_queue):
#         self.witmotion_ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
#         self.witmotion_ser.reset_input_buffer()
#         self.data_queue = data_queue
#         self.current_sequence_state = {}

#         self.packet_timestamps = {}
#         self.received_since_last_send = set()
#         self.lock = threading.Lock()
#         self._is_stopped = threading.Event()
#         self._sensor_thread = threading.Thread(target=self._read_witwotion_serial, daemon=True)
#         self._sensor_thread.start()

#     def _read_witwotion_serial(self):
#         """Producer thread: Reads 11-byte packets from the WitMotion sensor."""
#         logging.info("WitMotion reader thread started.")
#         buffer = b''
#         while not self._is_stopped.is_set():
#             try:
#                 buffer += self.witmotion_ser.read(self.witmotion_ser.in_waiting or 1)
#                 start_index = buffer.find(b'\x55')
                
#                 if start_index != -1 and len(buffer) >= start_index + 11:
#                     frame = buffer[start_index : start_index + 11]
#                     buffer = buffer[start_index + 11:]
                    
#                     parsed_result = parse_data(frame) 
#                     if parsed_result:
#                         data_type_name, values = parsed_result
#                         # logging.info(f"Received WitMotion packet: {data_type_name}, values={values}")
#                         # sensor_pb = robot_messages_pb2.SensorData()
#                         with self.lock:
#                             self.current_sequence_state.update(values)
#                             self.packet_timestamps[data_type_name] = time.time()
#                             self.received_since_last_send.add(data_type_name)
#                             if len(self.received_since_last_send) == 3:
#                                 sensor_pb = robot_messages_pb2.SensorData()
#                                 avg_timestamp = sum(self.packet_timestamps.values()) / 3.0
#                                 sensor_pb.sequence = 1 
#                                 sensor_pb.timestamp = avg_timestamp
#                                 state = self.current_sequence_state
#                                 sensor_pb.imu.accel_x = state.get('accel_x', 0.0)
#                                 sensor_pb.imu.accel_y = state.get('accel_y', 0.0)
#                                 sensor_pb.imu.accel_z = state.get('accel_z', 0.0)
#                                 sensor_pb.imu.gyro_x = state.get('gyro_x', 0.0)
#                                 sensor_pb.imu.gyro_y = state.get('gyro_y', 0.0)
#                                 sensor_pb.imu.gyro_z = state.get('gyro_z', 0.0)
#                                 sensor_pb.gps.lat = state.get('roll',0.0)
#                                 sensor_pb.gps.lon = state.get('pitch', 0.0)
#                                 sensor_pb.gps.alt = state.get('yaw', 0.0)
#                                 self.data_queue.append(b'S' + sensor_pb.SerializeToString())
#                                 self.received_since_last_send.clear()
#                                 self.packet_timestamps.clear()
#                                 # logging.info(f"Added to serial_queue, size: {len(self.data_queue)}")
#             except Exception as e:
#                 logging.warning(f"WitMotion serial read error: {e}")
#                 time.sleep(1)
#     def stop(self):
#         self._is_stopped.set()
#         self._sensor_thread.join(timeout=1)
#         self.witmotion_ser.close()




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
    content = open(os.path.join(ROOT, "index_html.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client_direct.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

# async def offer(request):
#     params = await request.json()
#     offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
#     pc = RTCPeerConnection()
#     pc_id = f"pc-{uuid.uuid4()}"
#     video_track = RobustPiCameraTrack()
#     video_track.start()
#     serial_handler = ArduinoHandler(data_queue=serial_queue)
#     sensor_handler = SensorHandler(data_queue=serial_queue)
#     data_channel = pc.createDataChannel("protobuf", ordered=False, maxRetransmits=0)
#     connections[pc_id] = (pc, video_track, serial_handler,sensor_handler)

#     @data_channel.on("message")
#     def on_message(message):
#         try:
#             cmd = robot_messages_pb2.Command()
#             cmd.ParseFromString(message)
#             serial_handler.send_command(cmd)
#             logging.info(f"Received Command: type={cmd.steering}, value={cmd.throttle:.2f}")
#         except Exception as e:
#             logging.error(f"Data channel error on message receive: {e}")

#     @pc.on("connectionstatechange")
#     async def on_connectionstatechange():
#         logging.info(f"Connection state is {pc.connectionState}")
#         if pc.connectionState in ("failed", "closed", "disconnected"):
#             if pc_id in connections:
#                 pc_ref, track_ref, serial_ref,sensor_ref = connections.pop(pc_id)
#                 track_ref.stop()
#                 serial_ref.stop()
#                 sensor_ref.stop()
#                 await pc_ref.close()
#                 logging.info(f"Closed and cleaned up connection {pc_id}")

#     async def send_sensor_data_after_open():
#         logging.info("Waiting for data channel to open...")
#         opened = asyncio.Future()

#         @data_channel.on("open")
#         def on_open():
#             logging.info("Data channel opened!")
#             if not opened.done():
#                 opened.set_result(True)

#         @data_channel.on("close")
#         def on_close():
#             logging.info("Data channel closed!")

#         try:
#             await asyncio.wait_for(opened, timeout=15.0)
#         except asyncio.TimeoutError:
#             logging.error("Data channel did not open within 15 seconds")
#             return

#         logging.info("Sending sensor data...")
#         while pc.connectionState == "connected":
#             if data_channel.readyState != "open":
#                 logging.warning(f"Data channel state: {data_channel.readyState}")
#                 break
#             if serial_queue:
#                 data = serial_queue.popleft()
#                 message_type = data[:1].decode('ascii', errors='ignore')
#                 logging.info(f"Attempting to send data, type={message_type}, queue size: {len(serial_queue) + 1}")
#                 try:
#                     data_channel.send(data)
#                     logging.info(f"Sent data to data channel, type={message_type}, queue size: {len(serial_queue)}")
#                 except Exception as e:
#                     logging.warning(f"Data channel send error: {e}")
#             else:
#                 logging.debug("Serial queue empty")
#             await asyncio.sleep(0.1)  # 50ms to avoid overwhelming the channel

#     start_time = time.time()
#     pc.addTrack(video_track)
#     await pc.setRemoteDescription(offer)
#     answer = await pc.createAnswer()
#     await pc.setLocalDescription(answer)
#     logging.info(f"WebRTC setup took {time.time() - start_time:.2f}s")
#     asyncio.create_task(send_sensor_data_after_open())

#     return web.Response(
#         content_type="application/json",
#         text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
#     )

# async def on_shutdown(app):
#     logging.info("Server is shutting down...")
#     # FIX #2: Unpack all four items correctly to prevent crash
#     for pc, track, arduino_handler, sensor_handler in list(connections.values()):
#         # track.stop() # Uncomment if your camera class has a stop method
#         arduino_handler.stop()
#         sensor_handler.stop()
#         await pc.close()
#     connections.clear()
#     logging.info("All connections closed.")

# app = web.Application()
# app.on_shutdown.append(on_shutdown)
# app.router.add_get("/", index)
# app.router.add_get("/client_direct.js", javascript)
# app.router.add_post("/offer", offer)
# app.router.add_static("/public", ROOT)
# web.run_app(app, host=HOST, port=PORT)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pc_id = f"pc-{uuid.uuid4()}"
    video_track = RobustPiCameraTrack()
    video_track.start()
    # serial_handler = ArduinoHandler(data_queue=serial_queue)
    sensor_handler = SensorHandler(data_queue=serial_queue)
    data_channel = pc.createDataChannel("protobuf", ordered=False, maxRetransmits=0)
    connections[pc_id] = (pc, video_track, sensor_handler)

    @data_channel.on("message")
    def on_message(message):
        try:
            cmd = robot_messages_pb2.Command()
            cmd.ParseFromString(message)
            # serial_handler.send_command(cmd)
            logging.info(f"Received Command: steering={cmd.steering:.2f}, throttle={cmd.throttle:.2f}")
        except Exception as e:
            logging.error(f"Data channel error on message receive: {e}")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logging.info(f"Connection state is {pc.connectionState}")
        if pc.connectionState in ("failed", "closed", "disconnected"):
            if pc_id in connections:
                pc_ref, track_ref, sensor_ref = connections.pop(pc_id)
                track_ref.stop()
                # serial_ref.stop()
                sensor_ref.stop()
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
                data_channel.send("TEST_MESSAGE")
                logging.info("Sent test message to data channel")
            except Exception as e:
                logging.warning(f"Test message send error: {e}")

        @data_channel.on("close")
        def on_close():
            logging.info("Data channel closed!")

        @data_channel.on("error")
        def on_error(error):
            logging.error(f"Data channel error: {error}")

        try:
            await asyncio.wait_for(opened, timeout=15.0)
        except asyncio.TimeoutError:
            logging.error("Data channel did not open within 15 seconds")
            return

        logging.info("Sending sensor data...")
        while pc.connectionState == "connected":
            if data_channel.readyState != "open":
                logging.warning(f"Data channel state: {data_channel.readyState}")
                break
            if serial_queue:
                data = serial_queue.popleft()
                # message_type = data[:1].decode('ascii', errors='ignore')
                # payload = data
                # logging.info(f"Attempting to send data, type={message_type}, payload size={len(payload)}, bytes={data.hex()}, queue size: {len(serial_queue) + 1}")
                try:
                    data_channel.send(data)
                    logging.info(f"Sent data to data channel payload size={len(data)}, queue size: {len(serial_queue)}")
                except Exception as e:
                    logging.warning(f"Data channel send error: {e}")
                    break
            else:
                logging.debug("Serial queue empty")
            await asyncio.sleep(0.05)  # Use 50ms to match previous working code

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

# ArduinoHandler with Dummy Data
class ArduinoHandler:
    def __init__(self, data_queue):
        self.data_queue = data_queue
        self._is_stopped = threading.Event()
        self._thread = threading.Thread(target=self._read_serial, daemon=True)
        self._thread.start()
        # Dummy data mode; comment out if using real serial port
        self.ser = None

    def _read_serial(self):
        logging.info("Arduino reader thread started (using dummy data).")
        sequence = 0
        while not self._is_stopped.is_set():
            try:
                sequence += 1
                msg = robot_messages_pb2.RobotStatus()
                msg.sequence = sequence
                msg.steering = 0.5
                msg.throttle = 0.5
                msg.timestamp = time.time()
                serialized = msg.SerializeToString()
                self.data_queue.append(b'R' + serialized)
                logging.info(f"Queued dummy RobotStatus: sequence={msg.sequence}, steering={msg.steering:.2f}, throttle={msg.throttle:.2f}, bytes={serialized.hex()}, queue size: {len(self.data_queue)}")
                time.sleep(0.1)
            except Exception as e:
                logging.warning(f"Arduino read thread error: {e}")
                time.sleep(1)

    def send_command(self, cmd):
        # logging.info(f"Dummy Arduino command sent: steering={cmd.steering:.2f}, throttle={cmd.throttle:.2f}")
        pass
    def stop(self):
        self._is_stopped.set()
        self._thread.join(timeout=1)
        if self.ser:
            self.ser.close()
        logging.info("Arduino handler stopped.")

# SensorHandler with Dummy Data
class SensorHandler:
    def __init__(self, data_queue):
        self.data_queue = data_queue
        self._is_stopped = threading.Event()
        self._sensor_thread = threading.Thread(target=self._read_witmotion_serial, daemon=True)
        self._sensor_thread.start()
        self.witmotion_ser = None

    def _read_witmotion_serial(self):
        logging.info("WitMotion reader thread started (using dummy data).")
        sequence = 0
        while not self._is_stopped.is_set():
            try:
                sequence += 1
                sensor_pb = robot_messages_pb2.SensorData()
                sensor_pb.sequence = sequence
                sensor_pb.timestamp = time.time()
                sensor_pb.imu.accel_x = 1.0
                sensor_pb.imu.accel_y = 2.0
                sensor_pb.imu.accel_z = 3.0
                sensor_pb.imu.gyro_x = 0.1
                sensor_pb.imu.gyro_y = 0.2
                sensor_pb.imu.gyro_z = 0.3
                sensor_pb.gps.lat = 45.0
                sensor_pb.gps.lon = 90.0
                sensor_pb.gps.alt = 180.0
                serialized = sensor_pb.SerializeToString()
                self.data_queue.append(serialized)
                # logging.info(f"Queued dummy SensorData: sequence={sensor_pb.sequence}, accel_x={sensor_pb.imu.accel_x:.2f}, lat={sensor_pb.gps.lat:.2f}, bytes={serialized.hex()}, queue size: {len(self.data_queue)}")
                time.sleep(0.1)
            except Exception as e:
                logging.warning(f"WitMotion serial read error: {e}")
                time.sleep(1)

    def stop(self):
        self._is_stopped.set()
        self._sensor_thread.join(timeout=1)
        if self.witmotion_ser:
            self.witmotion_ser.close()
        logging.info("WitMotion handler stopped.")




async def on_shutdown(app):
    logging.info("Server is shutting down...")
    # FIX #2: Unpack all four items correctly to prevent crash
    for pc, track, sensor_handler in list(connections.values()):
        track.stop() # Uncomment if your camera class has a stop method
        # arduino_handler.stop()
        sensor_handler.stop()
        await pc.close()
    connections.clear()
    logging.info("All connections closed.")

app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_get("/client_direct.js", javascript)
app.router.add_post("/offer", offer)
app.router.add_static("/public", ROOT)
web.run_app(app, host=HOST, port=PORT)