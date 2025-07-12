import serial
import time
import struct

# --- Configuration Commands (Hex Bytes) ---
CMD_UNLOCK = b'\xff\xaa\x69\x88\xb5'
CMD_SAVE = b'\xff\xaa\x00\x00\x00'
CMD_SET_RATE_50HZ = b'\xff\xaa\x03\x08\x00'

def parse_data(frame):
    """Parses a 11-byte data frame from the WitMotion sensor."""
    if len(frame) != 11:
        return None

    # Verify checksum
    checksum_calculated = sum(frame[0:10]) & 0xff
    checksum_received = frame[10]

    if checksum_calculated != checksum_received:
        # Print detailed error for debugging
        print(f"Checksum error! Frame: {frame.hex()} | Calc: {hex(checksum_calculated)} | Recv: {hex(checksum_received)}")
        return None

    data_type = frame[1]
    raw_data = struct.unpack('<hhhh', frame[2:10])

    if data_type == 0x51:  # Acceleration
        acc_x = (raw_data[0] / 32768.0) * 16
        acc_y = (raw_data[1] / 32768.0) * 16
        acc_z = (raw_data[2] / 32768.0) * 16
        return "Acceleration (g)", {"x": f"{acc_x:.2f}", "y": f"{acc_y:.2f}", "z": f"{acc_z:.2f}"}
    
    elif data_type == 0x52:  # Angular Velocity
        gyro_x = (raw_data[0] / 32768.0) * 2000
        gyro_y = (raw_data[1] / 32768.0) * 2000
        gyro_z = (raw_data[2] / 32768.0) * 2000
        return "Angular Velocity (°/s)", {"x": f"{gyro_x:.2f}", "y": f"{gyro_y:.2f}", "z": f"{gyro_z:.2f}"}

    elif data_type == 0x53:  # Angle
        roll = (raw_data[0] / 32768.0) * 180
        pitch = (raw_data[1] / 32768.0) * 180
        yaw = (raw_data[2] / 32768.0) * 180
        return "Angle (°)", {"roll": f"{roll:.2f}", "pitch": f"{pitch:.2f}", "yaw": f"{yaw:.2f}"}
        
    return None

# --- Main Execution ---
SERIAL_PORT = '/dev/ttyUSB0'

# !!! IMPORTANT: TRY CHANGING THIS VALUE !!!
# Common WitMotion baud rates are 9600 and 115200.
# Let's start with 115200 as it's a common default.
BAUD_RATE = 115200 

ser = serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=0.1)

print(f"Attempting to listen on {SERIAL_PORT} at {BAUD_RATE} bps...")

# Clear any old data in the buffer
ser.reset_input_buffer()

start_time = time.time()
packet_count = 0
buffer = b''

try:
    while True:
        # Read all available data from serial and add to buffer
        buffer += ser.read(ser.in_waiting or 1)
        
        # Look for the frame header (0x55)
        start_index = buffer.find(b'\x55')
        
        if start_index != -1:
            # Check if there's enough data for a full frame
            if len(buffer) >= start_index + 11:
                # Extract the 11-byte frame
                frame = buffer[start_index : start_index + 11]
                
                # Remove the processed bytes from the buffer
                buffer = buffer[start_index + 11:]
                
                parsed_result = parse_data(frame)
                if parsed_result:
                    packet_count += 1
                    data_type_name, values = parsed_result
                    print(f"{data_type_name}: {values}")

                # Calculate and display the frequency every second
                if time.time() - start_time >= 1.0:
                    print(f"--- Frequency: {packet_count} Hz ---")
                    packet_count = 0
                    start_time = time.time()
            else:
                # Not enough data for a full frame yet, wait for more
                time.sleep(0.005)
                
except KeyboardInterrupt:
    print("\nProgram terminated by user.")
finally:
    ser.close()
    print("Serial port closed.")