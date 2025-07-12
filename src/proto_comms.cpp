
#include <Arduino.h>
#include <pb_encode.h>
#include <pb_decode.h>
#include "robot_messages.pb.h"
#include "robot_controller.h"
#include "Motor.h"
#include "util.h"
#include "proto_comms.h"

namespace proto_comms {
  uint8_t buffer[128];
  uint32_t last_send = 0;
  const uint32_t send_interval = 50; // 20 Hz
  static uint32_t command_start_time = 0;
  const uint32_t command_duration = 100; // 100ms

  void init() {
    Serial.begin(115200); // For Protobuf
    while (!Serial) {}
  }

  void send_robot_status() {
    RobotStatus status = RobotStatus_init_zero;
    status.sequence = controller::sequence++;
    status.steering = fmap(Motor::servoValues[0], Motor::minStr, Motor::maxStr, -1.0, 1.0);
    status.throttle = fmap(Motor::servoValues[1], Motor::minThr, Motor::maxThr, -1.0, 1.0);
    status.timestamp = millis() / 1000.0;

    pb_ostream_t stream = pb_ostream_from_buffer(buffer, sizeof(buffer));
    if (pb_encode(&stream, RobotStatus_fields, &status)) {
      uint16_t len = stream.bytes_written;
      Serial.write((uint8_t)(len >> 8));
      Serial.write((uint8_t)(len & 0xFF));
      Serial.write(buffer, len);
    } 
  }

  void receive_command() {
    static enum {
      STATE_WAITING_FOR_LEN_1,
      STATE_WAITING_FOR_LEN_2,
      STATE_READING_PAYLOAD
    } state = STATE_WAITING_FOR_LEN_1;

    static uint16_t expected_len = 0;
    static uint16_t bytes_received = 0;
    static uint8_t len_buf[2];

    // Check if current command has expired (100ms)
    if (command_start_time > 0 && (millis() - command_start_time >= command_duration)) {
      controller::cmdSteering = 1500; // Neutral
      controller::cmdThrottle = 1500; // Neutral
      command_start_time = 0; // Reset timer
    }

    // Process new commands
    while (Serial.available() > 0) {
      uint8_t incoming_byte = Serial.read();
      // Serial.println("Received byte: ");
      switch (state) {
        case STATE_WAITING_FOR_LEN_1:
          // Serial.print("Waiting for length byte 1, received: ");
          len_buf[0] = incoming_byte;
          state = STATE_WAITING_FOR_LEN_2;
          break;

        case STATE_WAITING_FOR_LEN_2:
          // Serial.print("Received length byte: ");
          len_buf[1] = incoming_byte;
          expected_len = (len_buf[0] << 8) | len_buf[1];
          if (expected_len == 0 || expected_len > sizeof(buffer)) {
            // Serial.print("Error: Invalid length received: ");
            // Serial.println(expected_len);
            state = STATE_WAITING_FOR_LEN_1;
          } else {
            bytes_received = 0;
            state = STATE_READING_PAYLOAD;
          }
          break;

        case STATE_READING_PAYLOAD:
          // Serial.print("Reading payload, expected length: ");
          if (bytes_received < sizeof(buffer)) {
            buffer[bytes_received] = incoming_byte;
          }
          bytes_received++;

          if (bytes_received >= expected_len) {
            Command cmd = Command_init_zero;


            // Serial.print(cmd.throttle);
            // Serial.print(" bytes received, expected: ");

            pb_istream_t stream = pb_istream_from_buffer(buffer, expected_len);
            if (pb_decode(&stream, Command_fields, &cmd)) {
              // Serial.print("DEBUG: DECODE SUCCESS! Steering: ");
              // Serial.print(cmd.steering);
              // Serial.print(", Throttle: ");
              // Serial.println(cmd.throttle); 
              controller::lastMsgTime = micros();
              controller::cmdSteering = fmap(clip(cmd.steering, -1.0, 1.0), -1.0, 1.0, Motor::minStr, Motor::maxStr);
              controller::cmdThrottle = fmap(clip(cmd.throttle, -1.0, 1.0), -1.0, 1.0, Motor::minThr, Motor::maxThr);
              command_start_time = millis(); // Reset 100ms timer
            } else {
              Serial.print("Failed to decode command: ");
              Serial1.println(PB_GET_ERROR(&stream));
            }
            state = STATE_WAITING_FOR_LEN_1;
          }
          break;
      }
    }
  }
}
