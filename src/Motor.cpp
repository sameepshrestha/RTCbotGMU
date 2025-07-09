#include "def.h"
#include "Motor.h"
#include "util.h"

namespace Motor {
    uint16_t servoValues[noServos] = {1500, 1500, 1500};
    uint16_t servoData[3] = {1500, 1500, 1500};
    uint16_t minStr = minSt;
    uint16_t maxStr = maxSt;
    uint16_t minThr = minTh;
    uint16_t maxThr = maxTh;
    uint16_t offsetSteering = 0;
}


void initServos(){
  for(uint8_t i = 0; i < noServos; i++){
      Motor::servoValues[i] = 1500;
  }
  #if noServos > 0
      s_TCCRA = (1 << s_WGM1);
      s_TCCRB = (1 << s_WGM2) | (1 << s_WGM3) | (1 << s_CS1);
      s_ICR = 19999;

      s_DDR |= (1 << S1_PIN);
      s_TCCRA |= (1 << s_COMA1);

      S1 = 3000;
  #endif

  #if noServos > 1
      s_DDR |= (1 << S2_PIN);
      s_TCCRA |= (1 << s_COMB1);

      S2 = 3000;
  #endif

  #if noServos > 2
      s_DDR |= (1 << S3_PIN);
      s_TCCRA |= (1 << s_COMC1);
      S3 = Motor::servoValues[2] * 2;
  #endif
  delay(1000); 
}

void write_servos() {
  ESC(Motor::servoValues[1]);
  Steering(Motor::servoValues[0]);
  Aux(Motor::servoValues[2]);
}

void servo_failsafe(){
  ESC(1500);
  Steering(1500);
  Aux(1500);
}

