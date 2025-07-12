#!/usr/bin/env python3
import serial
import time
import robot_messages_pb2

def decode_protobuf_message(port='/dev/ttyACM0', baudrate=115200):
    ser = serial.Serial(port, baudrate, timeout=1)
    print(f"Connected to {port} at {baudrate} baud")
    steering_toggle = -0.0  # Start with -0.1
    last_send = time.time()

    try:
        while True:
            # Send Command every 20ms
            if time.time() - last_send >= 0.02:  # 50 Hz
                cmd = robot_messages_pb2.Command()
                cmd.steering = 0
                cmd.throttle = 0.3
                data = cmd.SerializeToString()
                ser.write(bytes([(len(data) >> 8), len(data) & 0xFF]) + data)
                print(f"[{time.time():.3f}] Sent Command: Steering={steering_toggle:.3f}, Throttle=0.700")
                steering_toggle = -steering_toggle  # Toggle between -0.1 and 0.1
                last_send = time.time()

            # Read RobotStatus
            length_bytes = ser.read(2)
            if len(length_bytes) < 2:
                continue

            msg_length = (length_bytes[0] << 8) | length_bytes[1]
            if msg_length == 0 or msg_length > 128:
                raw_data = ser.read(ser.in_waiting or 128)  # Read available bytes
                try:
                    # Try to decode as ASCII string
                    debug_msg = raw_data.decode('ascii').strip()
                    print(f"Arduino debug: '{debug_msg}'")
                except UnicodeDecodeError:
                    pass
                continue

            data = ser.read(msg_length)
            if len(data) != msg_length:
                ser.read(ser.in_waiting)  # Clear buffer
                continue

            status = robot_messages_pb2.RobotStatus()
            try:
                status.ParseFromString(data)
                print(f"[{time.time():.3f}] Sequence: {status.sequence}, "
                      f"Steering: {status.steering:.3f}, "
                      f"Throttle: {status.throttle:.3f}, "
                      f"Timestamp: {status.timestamp:.3f}")
            except Exception as e:
                print(f"[{time.time():.3f}] Failed to decode message: {e}")

    except KeyboardInterrupt:
        print("\nStopping decoder")
    finally:
        ser.close()
        print("Serial port closed")

if __name__ == "__main__":
    decode_protobuf_message()