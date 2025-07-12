#include <Arduino.h>
#include <avr/wdt.h>
#include "proto_comms.h"
#include "Motor.h"
#include "util.h"
#include "def.h"

namespace controller {
  const uint8_t controlMode = 1; // Fixed to autonomous
  uint16_t cmdSteering = 1500;
  uint16_t cmdThrottle = 1500;
  uint32_t sequence = 0;
  uint32_t lastMsgTime = 0;
}

uint16_t prevTime = 0;
uint16_t prevStatus = 0;

void failsafe() {
  if ((micros() - controller::lastMsgTime > 1000000) || (controller::lastMsgTime == 0)) {
    Motor::servoValues[0] = 1500; // Neutral steering
    Motor::servoValues[1] = 1500; // Neutral throttle
    Motor::servoValues[2] = 1500;
  }
}

void setup() {
  Serial.begin(115200);
  proto_comms::init();
  Motor::servoValues[0] = 1000; // Neutral steering
  Motor::servoValues[1] = 1500; // Neutral throttle
  Motor::servoValues[2] = 1500;
  initServos();
  write_servos();
  delay(1500);
  // Serial.println("Initialization Complete");
  wdt_enable(WDTO_250MS);
  wdt_reset();
}

void loop() {
  wdt_reset();
  uint16_t timeNow = (uint16_t)millis();
  if (timeNow - prevTime < 10) {
    return;
  }
  prevTime = timeNow;

  proto_comms::receive_command();
  failsafe();
  if ((micros() - controller::lastMsgTime < 1000000) && (controller::lastMsgTime != 0)) {
      Motor::servoValues[0] = (uint16_t)controller::cmdSteering;
      Motor::servoValues[1] = (uint16_t)controller::cmdThrottle;
      Motor::servoValues[2] = 1500; // Keep aux neutral for now
  }
  // Serial.println("Steering: " + String(Motor::servoValues[0]) + 
  //                ", Throttle: " + String(Motor::servoValues[1]) + 
  //                ", Aux: " + String(Motor::servoValues[2]));
  write_servos();

  if (timeNow - prevStatus >= proto_comms::send_interval) {
    proto_comms::send_robot_status();
    prevStatus = timeNow;
  }

  delay(5);
}
