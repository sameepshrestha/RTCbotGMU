import serial
import time
import sensor_data_pb2
import random

# Initialize serial port
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.1)
cmd_sequence = 0
last_cmd_time = time.time()
commands = ["up", "down", "left", "right"]

print("Starting serial communication...")

while True:
    try:
        # Receive SensorData
        if ser.in_waiting >= 2:
            length_bytes = ser.read(2)
            if len(length_bytes) == 2:
                length = int.from_bytes(length_bytes, 'big')
                if 0 < length <= 64:
                    data = ser.read(length)
                    if len(data) == length:
                        msg = sensor_data_pb2.SensorData()
                        msg.ParseFromString(data)
                        print(f"Received SensorData: sequence={msg.sequence}, timestamp={msg.timestamp:.3f}, "
                              f"lat={msg.gps.lat:.4f}, lon={msg.gps.lon:.4f}, alt={msg.gps.alt:.1f}")
                    else:
                        print(f"Incomplete data: expected {length}, got {len(data)}")
                else:
                    print(f"Invalid length: {length}")
            else:
                print("Failed to read length bytes")

        # Send Command
        current_time = time.time()
        if current_time - last_cmd_time >= 2.0:  # Send every 2 seconds
            cmd = sensor_data_pb2.Command()
            cmd.timestamp = current_time
            cmd.type = random.choice(commands)
            cmd.value = random.uniform(1.0, 5.0)
            encoded = cmd.SerializeToString()
            length = len(encoded)
            ser.write(length.to_bytes(2, 'big') + encoded)
            print(f"Sent Command: sequence={cmd.sequence}, type={cmd.type}, duration={cmd.value:.2f}s")
            cmd_sequence += 1
            last_cmd_time = current_time

        time.sleep(0.001)  # Small delay to prevent CPU overload

    except serial.SerialException as e:
        print(f"Serial error: {e}")
        break
    except Exception as e:
        print(f"Error: {e}")

ser.close()