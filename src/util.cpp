#include "util.h"
#include "def.h"

bool prev_dir = 0;
unsigned long brk_timer = 0;

float fmap(float toMap, float in_min, float in_max, float out_min, float out_max) {
  return (toMap - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

float clip(float source, float minVal, float maxVal){
  return  min(maxVal, max(source, minVal));
}

int get_thr_cmd(int inThr, int rpmCur){
    int thrOut = 1500;
    // ESC forward continue
    if ((inThr >= 1500) && (prev_dir == 0)){
      thrOut = inThr;
    }
    
    //ESC reverse continue 
    if ((inThr < 1500 ) && (prev_dir == 1)){
      thrOut = inThr;
    }

    //From forward to rev
    if ((inThr < 1500 ) && (prev_dir == 0)){
      thrOut = fw_to_rev(inThr, rpmCur);
    }

    //From rev to forward
    if ((inThr > 1500 ) && (prev_dir == 1)){ 
      thrOut = rev_to_fw(rpmCur);
    }

    return thrOut;
}

int fw_to_rev(int th, int rpmCur){
  if(abs(rpmCur) >= 10){
    brk_timer = millis();
  }
  
  if(abs(rpmCur) < 10){
    if((millis() - brk_timer) < 50 ){
      return 1500;
    }
    brk_timer = 0;
    prev_dir = 1;
    return 1500;
  }
  return th;
}

int rev_to_fw(int rpmCur){
  if(abs(rpmCur) >= 500){
    brk_timer = millis();
  }
  
  if(abs(rpmCur) < 500){
    if((millis() - brk_timer) < 50 ){
      return 1500;
    }
    brk_timer = 0;
    prev_dir = 0;
    return 1500;
  }
  return 1500;
}
