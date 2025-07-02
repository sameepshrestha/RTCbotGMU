#include <pb_encode.h>
#include <pb_decode.h>
#include "sensor_data.pb.h"

uint8_t buffer[64];
uint32_t sequence = 0;
uint32_t last_send = 0;
const uint32_t send_interval = 100; // 10 Hz
const int up_pin = 9;     // LED for "up"
const int down_pin = 10;  // LED for "down"
const int left_pin = 11;  // LED for "left"
const int right_pin = 12; // LED for "right"  
uint32_t command_timeout = 0; // When current command expires
int active_pin = -1; // Current LED pin (-1 for none)

float random_float(float min, float max) {
    return min + (float)random(0, 1000) / 1000.0 * (max - min);
}

void setup() {
    Serial.begin(115200);
    while (!Serial) {}
    pinMode(up_pin, OUTPUT);
    pinMode(down_pin, OUTPUT);
    pinMode(left_pin, OUTPUT);
    pinMode(right_pin, OUTPUT);
    digitalWrite(up_pin, LOW);
    digitalWrite(down_pin, LOW);
    digitalWrite(left_pin, LOW);
    digitalWrite(right_pin, LOW);
}

void send_sensor_data() {
    SensorData msg = SensorData_init_zero;
    msg.sequence = sequence++;
    msg.timestamp = millis() / 1000.0;
    msg.gps.lat = random_float(-90.0, 90.0);
    msg.gps.lon = random_float(-180.0, 180.0);
    msg.gps.alt = random_float(0.0, 5000.0);
    msg.imu.accel_x = random_float(-10.0, 10.0);
    msg.imu.accel_y = random_float(-10.0, 10.0);
    msg.imu.accel_z = random_float(-10.0, 10.0);
    msg.imu.gyro_x = random_float(-1.0, 1.0);
    msg.imu.gyro_y = random_float(-1.0, 1.0);
    msg.imu.gyro_z = random_float(-1.0, 1.0);

    pb_ostream_t stream = pb_ostream_from_buffer(buffer, sizeof(buffer));
    pb_encode(&stream, SensorData_fields, &msg);
    uint16_t len = stream.bytes_written;
    Serial.write((uint8_t)(len >> 8));
    Serial.write((uint8_t)(len & 0xFF));
    Serial.write(buffer, len);
}

void receive_command() {
    static uint8_t len_buf[2];
    static uint8_t len_idx = 0;
    static uint16_t expected_len = 0;

    while (Serial.available()) {
        if (len_idx < 2) {
            len_buf[len_idx++] = Serial.read();
            if (len_idx == 2) {
                expected_len = (len_buf[0] << 8) | len_buf[1];
                len_idx = 0;
            }
        } else if (Serial.available() >= expected_len) {
            Serial.readBytes(buffer, expected_len);
            Command cmd = Command_init_zero;
            pb_istream_t stream = pb_istream_from_buffer(buffer, expected_len);
            if (pb_decode(&stream, Command_fields, &cmd)) {
                // Turn off current LED
                if (active_pin != -1) {
                    digitalWrite(active_pin, LOW);
                    active_pin = -1;
                }
                // Process new command
                int new_pin = -1;
                if (strcmp(cmd.type, "up") == 0) {
                    new_pin = up_pin;
                } else if (strcmp(cmd.type, "down") == 0) {
                    new_pin = down_pin;
                } else if (strcmp(cmd.type, "left") == 0) {
                    new_pin = left_pin;
                } else if (strcmp(cmd.type, "right") == 0) {
                    new_pin = right_pin;
                }
                if (new_pin != -1) {
                    digitalWrite(new_pin, HIGH);
                    active_pin = new_pin;
                    command_timeout = millis() + (uint32_t)(cmd.value * 1000); // Duration in ms
                }
                // Debug output
                Serial.print("Received Command: sequence=");
                Serial.print(cmd.sequence);
                Serial.print(", type=");
                Serial.print(cmd.type);
                Serial.print(", duration=");
                Serial.println(cmd.value);
            }
            expected_len = 0;
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
