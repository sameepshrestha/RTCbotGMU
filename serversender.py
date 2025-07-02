import asyncio
import json
import logging
import os
from fractions import Fraction
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaStreamTrack, MediaStreamError
from av import VideoFrame
import cv2
from aiohttp import web
import uuid

# --- Configuration & Globals---
ROOT = os.path.dirname(__file__)
HOST = "0.0.0.0"
PORT = 8080
logging.basicConfig(level=logging.INFO)
# We now store a set of the active camera tracks for cleanup
active_tracks = set()

# --- On-Demand Camera Track Class (No changes needed, this is correct) ---
class OnDemandPiCameraTrack(MediaStreamTrack):
    kind = "video"
    def __init__(self):
        super().__init__()
        self.cap = None
        self._is_stopped = asyncio.Event()
        self._next_pts = 0
        self.VIDEO_CLOCK_RATE = 90000
        self.FRAME_RATE = 30
        self._pts_increment = self.VIDEO_CLOCK_RATE // self.FRAME_RATE
        self.time_base = Fraction(1, self.VIDEO_CLOCK_RATE)

    def start(self):
        logging.info("Attempting to open camera...")
        pipeline = ("libcamerasrc ! video/x-raw,format=NV12,width=640,height=480,framerate=30/1 ! appsink drop=true")
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if self.cap.isOpened():
            logging.info("Camera opened successfully.")
            active_tracks.add(self)
        else:
            logging.error("!!!!!!!!!! CAMERA FAILED TO OPEN !!!!!!!!!!!")
            self.cap = None

    async def recv(self):
        if self._is_stopped.is_set():
            raise MediaStreamError
        
        pts = self._next_pts
        self._next_pts += self._pts_increment
        
        if self.cap is None:
            av_frame = VideoFrame(width=640, height=480)
            await asyncio.sleep(1 / self.FRAME_RATE)
        else:
            loop = asyncio.get_event_loop()
            ret, frame = await loop.run_in_executor(None, self.cap.read)
            if not ret:
                av_frame = VideoFrame(width=640, height=480)
            else:
                av_frame = VideoFrame.from_ndarray(frame, format="nv12")
        
        av_frame.pts = pts
        av_frame.time_base = self.time_base
        return av_frame

    async def stop(self):
        if not self._is_stopped.is_set():
            logging.info("Stopping camera track...")
            self._is_stopped.set()
            if self.cap:
                self.cap.release()
                logging.info("Camera resource released.")
            self.cap = None
            active_tracks.discard(self)

# --- Web Handlers ---
async def index(request):
    content = open(os.path.join(ROOT, "index_direct.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def javascript(request):
    content = open(os.path.join(ROOT, "client_direct.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

# =========================================================================
# ===       THE FINAL, CANONICALLY CORRECT `OFFER` HANDLER            ===
# =========================================================================
async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pc_id = f"pc-{uuid.uuid4()}"

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logging.info(f"Connection state for {pc_id} is {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()

    # Create the camera track object, but don't add it yet
    video_track = OnDemandPiCameraTrack()

    @pc.on("track")
    def on_track(track):
        # This event is for receiving tracks, which we don't do.
        # It's good practice to log it.
        logging.info(f"Track {track.kind} received, but we are send-only.")

    # Process the offer from the browser
    await pc.setRemoteDescription(offer)

    # --- THIS IS THE CRITICAL LOGIC ---
    # Find the video transceiver that the browser's offer created.
    # The browser creates a `recvonly` or `inactive` slot for the video it wants to receive.
    video_transceiver = next((t for t in pc.getTransceivers() if t.kind == "video"), None)
    
    if video_transceiver:
        logging.info("Found video transceiver from browser offer. Adding our track.")
        # Start the camera and attach our video track to this specific transceiver.
        video_track.start()
        video_transceiver.sender.replaceTrack(video_track)
    else:
        # This would be unusual, but it's a safe fallback.
        logging.warning("No video transceiver in offer, adding a new one.")
        video_track.start()
        pc.addTrack(video_track)

    # Now create the answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    logging.info(f"Successfully created and sent answer for {pc_id}")
    return web.Response(
        content_type="application/json",
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    )

async def on_shutdown(app):
    logging.info("Application shutting down...")
    # Get a copy of the tracks to close them
    tracks_to_close = list(active_tracks)
    for track in tracks_to_close:
        await track.stop()
    logging.info("Shutdown complete.")

# --- App Setup ---
app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_get("/client_direct.js", javascript)
app.router.add_post("/offer", offer)

if __name__ == "__main__":
    web.run_app(app, host=HOST, port=PORT)