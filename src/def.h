#ifndef DEF_H_
#define DEF_H_

/*******************************************************
                  Pin definitions
*******************************************************/
//LED pins
#define conLed        22
#define modeLed       23
#define batLed        24
#define rcLed         25
#define gpsLed        26
#define camLed        27
// #define modeLed       28 // Duplicated
#define lidarLed      29

//Sensor Pins
#define quadEncCnt    2
#define magEncCt      1
#define quadEncPins   {{4, 5}, {3, 2}}
#define magEncPins    {16}
#define batPinCnt     1
#define batSenPin     {A0}

//servo pin defination
#define steeringPin   7
#define escPin        6
#define auxPin        5

/*******************************************************
                  Limits definitions
*******************************************************/
// Limits for the servo range
#define minSt       1000 
#define maxSt       2000 
#define minTh       1000
#define maxTh       2000
#define maxbattV    16.8
#define minbattV    14.2


/*******************************************************
                  Timing definitions
*******************************************************/
#define brkTime         500
#define rcFailSafeTime  200
#define commLossTime    600
#define maxConLoopTime  100
#define pidLoopTime     20
#define joyPubTime      20
#define statPubTime     33


/*******************************************************
                  Parameter definitions
*******************************************************/
#define encCpr        {15, 15}
#define battscale     17.3
#define f_diff_ratio  0.3
#define tire_dia      218
#define KP            0.15
#define KI            0.3
#define KD            0.005
#define minAcc        0.1
#define maxAcc        1.0
#define maxDesc       32.0
#define maxSpeed      22.0

/*******************************************************
                  Serial definitions
*******************************************************/
#define baudRate    115200

#endif
