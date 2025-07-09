
#ifndef ROBOT_CONTROLLER_H
#define ROBOT_CONTROLLER_H

#include <Arduino.h>

namespace controller {
  extern const uint8_t controlMode;
  extern uint16_t cmdSteering;
  extern uint16_t cmdThrottle;
  extern uint32_t sequence;
  extern uint32_t lastMsgTime;
}

void failsafe();

#endif
