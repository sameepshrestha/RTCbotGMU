# --- File: serversender_FINAL.py ---
# Combines the proven WebRTC logic with a more robust camera class.

import asyncio
import json
import logging
import os
import time
import uuid
from fractions import Fraction
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaStreamTrack, MediaStreamError
from av import VideoFrame
from aiohttp import web
import cv2
import threading

# --- Configuration & Globals---
ROOT = os.path.dirname(__file__)
HOST = "0.0.0.0"
PORT = 8080
logging.basicConfig(level=logging.INFO)
connections = {}

# =========================================================================
# ===           THE NEW, MORE ROBUST & RESILIENT CAMERA TRACK         ===
# =========================================================================
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

# --- Web Handlers ---
async def index(request):
    content = open(os.path.join(ROOT, "index_direct.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def javascript(request):
    content = open(os.path.join(ROOT, "client_direct.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pc_id = f"pc-{uuid.uuid4()}"
    
    video_track = RobustPiCameraTrack()
    video_track.start()
    
    # Store these to close them on shutdown
    connections[pc_id] = (pc, video_track)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logging.info(f"Connection state for {pc_id} is {pc.connectionState}")
        if pc.connectionState in ("failed", "closed", "disconnected"):
            video_track.stop()
            if pc_id in connections:
                del connections[pc_id]

    # Use the proven-working WebRTC logic
    pc.addTrack(video_track)
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.Response(content_type="application/json", text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}))

async def on_shutdown(app):
    logging.info("Application shutting down...")
    for pc, track in list(connections.values()):
        track.stop()
        await pc.close()
    connections.clear()

# --- App Setup ---
app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_get("/client_direct.js", javascript)
app.router.add_post("/offer", offer)

if __name__ == "__main__":
    web.run_app(app, host=HOST, port=PORT)