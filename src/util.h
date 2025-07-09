#ifndef UTIL_H_
#define UTIL_H_

#include <Arduino.h>

extern bool prev_dir;
extern unsigned long brk_timer;

float fmap(float toMap, float in_min, float in_max, float out_min, float out_max);
float clip(float source, float minVal, float maxVal);
int get_thr_cmd(int inThr, int rpmCur);
int fw_to_rev(int, int);
int rev_to_fw(int);

#endif  // UTIL_H_
