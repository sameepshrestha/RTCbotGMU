document.addEventListener('DOMContentLoaded', () => {
      const startButton = document.getElementById('startBtn');
      const stopButton = document.getElementById('stopBtn');
      const upButton = document.getElementById('upBtn');
      const downButton = document.getElementById('downBtn');
      const leftButton = document.getElementById('leftBtn');
      const rightButton = document.getElementById('rightBtn');
      const videoElement = document.getElementById('video');
      const statusDisplay = document.getElementById('status');
      const sensorDataDisplay = document.getElementById('sensor-data');

      let pc = null;
      let dc = null;
      let proto = null;

      async function initProtoBuf() {
          const root = await protobuf.load("/public/sensor_data.proto");
          proto = {
              SensorData: root.lookupType("SensorData"),
              Command: root.lookupType("Command")
          };
      }

      function logStatus(msg) {
          statusDisplay.textContent = msg;
          console.log(msg);
      }

      function setUIState(state) {
          const isConnected = state === 'connected';
          startButton.disabled = isConnected;
          stopButton.disabled = !isConnected;
          upButton.disabled = !isConnected;
          downButton.disabled = !isConnected;
          leftButton.disabled = !isConnected;
          rightButton.disabled = !isConnected;
      }

      function sendCommand(type, duration) {
          if (dc && dc.readyState === 'open') {
              const cmd = proto.Command.create({
                  sequence: Math.floor(Math.random() * 1000),
                  timestamp: Date.now() / 1000,
                  type: type,
                  value: duration
              });
              const buffer = proto.Command.encode(cmd).finish();
              dc.send(buffer);
              logStatus(`Sent Command: ${type}, ${duration}s`);
          } else {
              console.warn('Data channel not open.');
          }
      }

      async function startStream() {
          await initProtoBuf();
          setUIState('connecting');
          logStatus('Starting connection...');
          pc = new RTCPeerConnection();
          const outgoing = pc.createDataChannel("protobuf", {
                    ordered: false,
                    maxRetransmits: 0
                });

          outgoing.onopen  = () => logStatus("Client: outgoing DC open");
          outgoing.onclose = () => logStatus("Client: outgoing DC closed");
          pc.ondatachannel = (event) => {
              logStatus('Data channel created.');
              dc = event.channel;
              dc.onopen = () => logStatus('Data channel open.');
              dc.onclose = () => logStatus('Data channel closed.');
              dc.onmessage = (event) => {
                  const msg = proto.SensorData.decode(new Uint8Array(event.data));
                  sensorDataDisplay.textContent = `Sensor Data: Sequence=${msg.sequence}, Timestamp=${msg.timestamp.toFixed(3)}, ` +
                                                  `Lat=${msg.gps.lat.toFixed(4)}, Lon=${msg.gps.lon.toFixed(4)}, Alt=${msg.gps.alt.toFixed(1)}`;
                  console.log("SensorData:", msg); // For programmatic access
              };
          };
          pc.onconnectionstatechange = () => {
              logStatus(`Connection state: ${pc.connectionState}`);
              if (pc.connectionState === 'connected') {
                  setUIState('connected');
              } else if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) {
                  stopStream();
              }
          };

          pc.ontrack = (event) => {
              logStatus('Video track received!');
              if (event.track.kind === 'video' && event.streams[0]) {
                  videoElement.srcObject = event.streams[0];
              }
          };

          pc.addTransceiver('video', { direction: 'recvonly' });

        //   pc.ondatachannel = (event) => {
        //       logStatus('Data channel created.');
        //       dc = event.channel;
        //       dc.onopen = () => logStatus('Data channel open.');
        //       dc.onclose = () => logStatus('Data channel closed.');
        //       dc.onmessage = (event) => {
        //           const msg = proto.SensorData.decode(new Uint8Array(event.data));
        //           sensorDataDisplay.textContent = `Sensor Data: Sequence=${msg.sequence}, Timestamp=${msg.timestamp.toFixed(3)}, ` +
        //                                           `Lat=${msg.gps.lat.toFixed(4)}, Lon=${msg.gps.lon.toFixed(4)}, Alt=${msg.gps.alt.toFixed(1)}`;
        //           console.log("SensorData:", msg); // For programmatic access
        //       };
        //   };

          try {
              const offer = await pc.createOffer();
              await pc.setLocalDescription(offer);
              console.log("===== Client Offer SDP =====\n", pc.localDescription.sdp);
              logStatus('Offer created. Sending to server...');
              const response = await fetch('/offer', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
              });
              if (!response.ok) throw new Error(`Server error: ${response.status}`);
              const answer = await response.json();
              logStatus('Answer received. Setting remote description...');
              await pc.setRemoteDescription(answer);
          } catch (err) {
              logStatus(`Error: ${err.message}`);
              stopStream();
          }
      }

      function stopStream() {
          if (pc) {
              pc.close();
              pc = null;
          }
          if (dc) {
              dc = null;
          }
          videoElement.srcObject = null;
          sensorDataDisplay.textContent = 'Sensor Data: Waiting...';
          logStatus('Disconnected. Ready.');
          setUIState('disconnected');
      }

      // Attach listeners
      startButton.addEventListener('click', startStream);
      stopButton.addEventListener('click', stopStream);
      upButton.addEventListener('click', () => sendCommand('up', 2));
      downButton.addEventListener('click', () => sendCommand('down', 2));
      leftButton.addEventListener('click', () => sendCommand('left', 2));
      rightButton.addEventListener('click', () => sendCommand('right', 2));

      // Initial UI state
      setUIState('disconnected');
  });
  