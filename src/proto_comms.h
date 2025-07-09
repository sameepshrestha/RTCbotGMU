
#ifndef PROTO_COMMS_H
#define PROTO_COMMS_H

#include <pb_encode.h>
#include <pb_decode.h>
#include "robot_messages.pb.h"

namespace proto_comms {
  extern uint8_t buffer[128];
  extern uint32_t last_send;
  extern const uint32_t send_interval;

  void init();
  void send_robot_status();
  void receive_command();
}

#endif
