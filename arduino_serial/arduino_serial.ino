#include <pb_encode.h>
#include <pb_decode.h>
#include <SoftwareSerial.h>
#include "sensor_data.pb.h"

#define debugSerial Serial1
uint8_t buffer[128];
uint32_t sequence = 0;
uint32_t last_send = 0;
const uint32_t send_interval = 200;
const int up_pin = 9;
const int down_pin = 10;
const int left_pin = 11;
const int right_pin = 12;
uint32_t command_timeout = 0;
int active_pin = -1;

float random_float(float min, float max) {
    return min + (float)random(0, 1000) / 1000.0 * (max - min);
}

void setup() {
    Serial.begin(115200);
    debugSerial.begin(9600);
    while (!Serial) {}
    pinMode(up_pin, OUTPUT);
    pinMode(down_pin, OUTPUT);
    pinMode(left_pin, OUTPUT);
    pinMode(right_pin, OUTPUT);
    digitalWrite(up_pin, LOW);
    digitalWrite(down_pin, LOW);
    digitalWrite(left_pin, LOW);
    digitalWrite(right_pin, LOW);
    debugSerial.println("arduino started");
}

void send_sensor_data() {
    SensorData msg = SensorData_init_zero;
    msg.sequence = sequence++;
    msg.timestamp = millis() / 1000.0;
    msg.has_gps = true; // Enable GPS submessage
    msg.gps.lat = random_float(-90.0, 90.0);
    msg.gps.lon = random_float(-180.0, 180.0);
    msg.gps.alt = random_float(0.0, 5000.0);
    msg.has_imu = true; // Enable IMU submessage
    msg.imu.accel_x = random_float(-10.0, 10.0);
    msg.imu.accel_y = random_float(-10.0, 10.0);
    msg.imu.accel_z = random_float(-10.0, 10.0);
    msg.imu.gyro_x = random_float(-1.0, 1.0);
    msg.imu.gyro_y = random_float(-1.0, 1.0);
    msg.imu.gyro_z = random_float(-1.0, 1.0);
//
//    Serial.print("Preparing SensorData: sequence=");
//    Serial.print(msg.sequence);
//    Serial.print(", timestamp=");
//    Serial.print(msg.timestamp);
//    Serial.print(", lat=");
//    Serial.print(msg.gps.lat);
//    Serial.print(", lon=");
//    Serial.print(msg.gps.lon);
//    Serial.print(", alt=");
//    Serial.print(msg.gps.alt);
//    Serial.print(", accel_x=");
//    Serial.print(msg.imu.accel_x);
//    Serial.print(", gyro_x=");
//    Serial.println(msg.imu.gyro_x);
//    Serial.print("has_gps: ");
//    Serial.println(msg.has_gps);
//    Serial.print("has_imu: ");
//    Serial.println(msg.has_imu);

    pb_ostream_t stream = pb_ostream_from_buffer(buffer, sizeof(buffer));
    if (pb_encode(&stream, SensorData_fields, &msg)) {
        uint16_t len = stream.bytes_written;
//        Serial.print("Encoded length: ");
//        Serial.println(len);
        Serial.write((uint8_t)(len >> 8));
        Serial.write((uint8_t)(len & 0xFF));
        Serial.write(buffer, len);
//        Serial.println("Encoding successful");
    } else {
//        Serial.println("Failed to encode SensorData");
//        Serial.print("Encoding error: ");
//        Serial.println(PB_GET_ERROR(&stream));
    }
}

// Rest of code (receive_command, check_timeout, loop) unchanged
void receive_command() {
    // Static variables to maintain state between loop() calls
    static enum {
        STATE_WAITING_FOR_LEN_1,
        STATE_WAITING_FOR_LEN_2,
        STATE_READING_PAYLOAD
    } state = STATE_WAITING_FOR_LEN_1;

    static uint16_t expected_len = 0;
    static uint16_t bytes_received = 0;
    static uint8_t len_buf[2];

    while (Serial.available() > 0) {
        uint8_t incoming_byte = Serial.read();

        switch (state) {
            case STATE_WAITING_FOR_LEN_1:
                // State 1: Read the first (high) byte of the length
                len_buf[0] = incoming_byte;
                state = STATE_WAITING_FOR_LEN_2;
                break;

            case STATE_WAITING_FOR_LEN_2:
                // State 2: Read the second (low) byte of the length
                len_buf[1] = incoming_byte;
                expected_len = (len_buf[0] << 8) | len_buf[1];

                // Sanity check the length
                if (expected_len == 0 || expected_len > sizeof(buffer)) {
                    debugSerial.print("Error: Invalid length received: ");
                    debugSerial.println(expected_len);
                    state = STATE_WAITING_FOR_LEN_1; // Reset to wait for a new message
                } else {
                    debugSerial.print("Expecting payload of length: ");
                    debugSerial.println(expected_len);
                    bytes_received = 0; // Reset payload counter
                    state = STATE_READING_PAYLOAD;
                }
                break;

            case STATE_READING_PAYLOAD:
                // State 3: Read the message payload, one byte at a time
                if (bytes_received < sizeof(buffer)) {
                    buffer[bytes_received] = incoming_byte;
                }
                bytes_received++;

                // Check if we have received the full payload
                if (bytes_received >= expected_len) {
                    debugSerial.println("Full payload received. Decoding...");

                    // --- DECODING LOGIC (same as you had before) ---
                    Command cmd = Command_init_zero;
                    char type_str[16] = {0};
                    cmd.type.arg = type_str;
                    cmd.type.funcs.decode = [](pb_istream_t *stream, const pb_field_t *field, void **arg) {
                        char *str = (char*)*arg;
                        size_t len = stream->bytes_left;
                        if (len > 15) len = 15;
                        if (!pb_read(stream, (uint8_t*)str, len)) return false;
                        str[len] = '\0';
                        return true;
                    };
                    
                    pb_istream_t stream = pb_istream_from_buffer(buffer, expected_len);
                    if (pb_decode(&stream, Command_fields, &cmd)) {
                        debugSerial.print("Decoded command: ");
                        debugSerial.println(type_str);

                        if (active_pin != -1) {
                            digitalWrite(active_pin, LOW);
                        }
                        
                        int new_pin = -1;
                        if (strcmp(type_str, "up") == 0) new_pin = up_pin;
                        else if (strcmp(type_str, "down") == 0) new_pin = down_pin;
                        else if (strcmp(type_str, "left") == 0) new_pin = left_pin;
                        else if (strcmp(type_str, "right") == 0) new_pin = right_pin;
                        
                        if (new_pin != -1) {
                            digitalWrite(new_pin, HIGH);
                            active_pin = new_pin;
                            command_timeout = millis() + (uint32_t)(cmd.value * 1000);
                        }
                    } else {
                        debugSerial.print("Failed to decode command: ");
                        debugSerial.println(PB_GET_ERROR(&stream));
                    }

                    // Reset for the next message
                    state = STATE_WAITING_FOR_LEN_1;
                }
                break;
        }
    }
}

void check_timeout() {
    if (active_pin != -1 && millis() >= command_timeout) {
        digitalWrite(active_pin, LOW);
        active_pin = -1;
    }
}

void loop() {
    if (millis() - last_send >= send_interval) {
        send_sensor_data();
        last_send = millis();
    }
    receive_command();
    check_timeout();
}
