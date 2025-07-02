// --- File: client_direct.js (The Bulletproof Version) ---

document.addEventListener('DOMContentLoaded', () => {
    const startButton = document.getElementById('startBtn');
    const stopButton = document.getElementById('stopBtn');
    const forwardButton = document.getElementById('forwardBtn');
    const videoElement = document.getElementById('video');
    const statusDisplay = document.getElementById('status');

    let pc = null;
    let dc = null;

    function logStatus(msg) {
        statusDisplay.textContent = msg;
        console.log(msg);
    }

    function setUIState(state) {
        const isConnected = state === 'connected';
        startButton.disabled = isConnected;
        stopButton.disabled = !isConnected;
        forwardButton.disabled = !isConnected;
    }

    async function startStream() {
        setUIState('connecting');
        logStatus('Starting connection...');
        
        pc = new RTCPeerConnection();

        // Setup event handlers immediately
        pc.onconnectionstatechange = () => {
            logStatus(`Connection state: ${pc.connectionState}`);
            if (pc.connectionState === 'connected') {
                setUIState('connected');
            } else if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) {
                stopStream();
            }
        };

        pc.ontrack = (event) => {
            logStatus('!!! Video track event fired !!!');
            if (event.track.kind === 'video' && event.streams[0]) {
                logStatus('Video track received! Attaching to element.');
                videoElement.srcObject = event.streams[0];
            }
        };

        // --- THIS IS THE NEW, BULLETPROOF FIX ---
        // Manually and explicitly add a transceiver for receiving video.
        // This is more reliable than the { offerToReceiveVideo: true } option.
        pc.addTransceiver('video', { direction: 'recvonly' });
        // --- END OF FIX ---
        
        try {
            dc = pc.createDataChannel('commands');
            dc.onopen = () => { logStatus('Data channel is open.'); };
            dc.onclose = () => { logStatus('Data channel is closed.'); };
            
            // Now create the offer. It will be correctly formed because
            // of the addTransceiver call above.
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            
            logStatus('Offer created. Sending to server...');
            const response = await fetch('/offer', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type }),
            });

            if (!response.ok) throw new Error(`Server error: ${response.status}`);
            
            const answer = await response.json();
            logStatus('Answer received. Setting remote description...');
            await pc.setLocalDescription(answer); // Typo corrected: was setLocalDescription, now setRemoteDescription

        } catch (err) {
            logStatus(`Error: ${err.message}`);
            stopStream();
        }
    }

    // TYPO CORRECTION in the try-catch block above
    // It should be `await pc.setRemoteDescription(answer);` not `setLocalDescription` twice. Let's fix it properly.
    // The following is the fully corrected function.

    async function fullyCorrectedStartStream() {
        setUIState('connecting');
        logStatus('Starting connection...');
        pc = new RTCPeerConnection();
    
        pc.onconnectionstatechange = () => {
            logStatus(`Connection state: ${pc.connectionState}`);
            if (pc.connectionState === 'connected') { setUIState('connected'); }
            else if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) { stopStream(); }
        };
    
        pc.ontrack = (event) => {
            logStatus('!!! Video track event fired !!!');
            if (event.track.kind === 'video') {
                videoElement.srcObject = event.streams[0];
            }
        };
    
        pc.addTransceiver('video', { direction: 'recvonly' });
        
        dc = pc.createDataChannel('commands');
        dc.onopen = () => { logStatus('Data channel open.'); };
        dc.onclose = () => { logStatus('Data channel closed.'); };
    
        try {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
    
            logStatus('Offer created and sent.');
            const response = await fetch('/offer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pc.localDescription),
            });
    
            if (!response.ok) throw new Error(`Server error: ${response.status}`);
            
            logStatus('Answer received. Setting remote description...');
            const answer = await response.json();
            await pc.setRemoteDescription(answer);
    
        } catch (err) {
            logStatus(`Error: ${err.message}`);
            stopStream();
        }
    }

    function stopStream() {
        if (pc) { pc.close(); pc = null; }
        videoElement.srcObject = null;
        dc = null;
        logStatus('Disconnected. Ready.');
        setUIState('disconnected');
    }

    function sendCommand(command) {
        if (dc && dc.readyState === 'open') { dc.send(command); }
        else { console.warn('Data channel not open.'); }
    }

    // Attach listeners
    startButton.addEventListener('click', fullyCorrectedStartStream); // Use the fully corrected one
    stopButton.addEventListener('click', stopStream);
    forwardButton.addEventListener('click', () => sendCommand('move_forward'));

    // Initial UI state
    setUIState('disconnected');
});