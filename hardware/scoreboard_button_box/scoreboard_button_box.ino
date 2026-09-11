/* ===========================================================================
   TMSA Scoreboard Button Box
   Pro Micro (ATmega32U4, 5V / 16 MHz) on a screw-terminal breakout shield.

   Every input uses the chip's internal pull-up resistor. A switch simply
   connects its pin to GND, so a closed switch reads LOW. There are NO power
   wires anywhere in this build -- each switch is just "pin to ground".

   Behaviour:
     * 25 ms debounce on every input
     * one keypress per physical press (fires on the press edge only), so
       holding a button down never repeats
     * a stuck/shorted wire therefore sends exactly one keystroke, not a flood

   TEST MODE:
     Hold the PLAY CLOCK CLEAR button (D5) while plugging in the USB cable.
     The TX LED blinks slowly and each button types its name as plain text
     instead of sending an F-key -- open Notepad and press every button to
     confirm the wiring. Unplug and replug without holding anything to
     return to normal operation.

   Board settings: see the accompanying guide.
   =========================================================================== */

#include <Keyboard.h>

/* ---------------------------------------------------------------------------
   F13-F20 key codes.

   The Arduino Keyboard library only gained KEY_F13..KEY_F24 in a later
   release, so we define our own names and work with every version.
   Keyboard.press() converts any code >= 0x88 into a raw USB HID usage by
   subtracting 0x88. The HID usage for F13 is 0x68, so 0x68 + 0x88 = 0xF0.
   --------------------------------------------------------------------------- */
#define KB_F13 0xF0
#define KB_F14 0xF1
#define KB_F15 0xF2
#define KB_F16 0xF3
#define KB_F17 0xF4
#define KB_F18 0xF5
#define KB_F19 0xF6
#define KB_F20 0xF7

/* ---------------------------------------------------------------------------
   PIN MAP

   The keys below are the ones the scoreboard software actually listens for
   (src/scoreboard/views/operator/keyboard.js). They are NOT in F15..F20 order
   down the panel -- the software's table is shuffled relative to the button
   layout, so the pin-to-key assignment here is what makes each button do what
   its label says.

     PIN  BUTTON                        KEY   WHAT THE SOFTWARE DOES
     D2   Game clock paddle, away       F13   Start game clock
     D3   Game clock paddle, toward     F14   Stop game clock
     D4   PLAY CLOCK START              F20   Start play clock
     D5   PLAY CLOCK CLEAR              F17   Clear play clock
     D6   PLAY CLOCK 25                 F18   Load play clock 25 (stopped)
     D7   PLAY CLOCK 40                 F19   Load play clock 40 (stopped)
     D8   QUICK 25                      F15   Load play clock 25 and start
     D9   QUICK 40                      F16   Load play clock 40 and start

   To change what a button sends, edit only the key column below.
   --------------------------------------------------------------------------- */

struct Input {
  uint8_t     pin;
  uint8_t     key;
  const char *label;   // typed in test mode
};

const Input INPUTS[] = {
  { 2, KB_F13, "D2  GAME CLOCK START (paddle away from me)" },
  { 3, KB_F14, "D3  GAME CLOCK STOP  (paddle toward me)"    },
  { 4, KB_F20, "D4  PLAY CLOCK START"                       },
  { 5, KB_F17, "D5  PLAY CLOCK CLEAR"                       },
  { 6, KB_F18, "D6  PLAY CLOCK 25"                          },
  { 7, KB_F19, "D7  PLAY CLOCK 40"                          },
  { 8, KB_F15, "D8  QUICK 25"                               },
  { 9, KB_F16, "D9  QUICK 40"                               },
};

const uint8_t COUNT = sizeof(INPUTS) / sizeof(INPUTS[0]);

/* --------------------------------------------------------------------------- */

const uint8_t  TEST_MODE_PIN = 5;    // hold PLAY CLOCK CLEAR at power-up
const uint16_t DEBOUNCE_MS   = 25;   // contact settling time
const uint16_t KEY_HOLD_MS   = 20;   // how long the key is reported as held

bool          rawState[COUNT];       // most recent raw reading
bool          stableState[COUNT];    // reading after debounce
unsigned long changedAt[COUNT];      // when the raw reading last flipped
bool          keyIsDown[COUNT];      // is this key currently reported pressed
unsigned long releaseAt[COUNT];      // when to release it

bool          testMode  = false;
unsigned long lastBlink = 0;
bool          blinkOn   = false;

/* --------------------------------------------------------------------------- */

void setup() {
  for (uint8_t i = 0; i < COUNT; i++) {
    pinMode(INPUTS[i].pin, INPUT_PULLUP);
  }

  delay(50);   // let the internal pull-ups charge the wiring before reading

  testMode = (digitalRead(TEST_MODE_PIN) == LOW);

  // Seed each input from its real state so a button held at power-up
  // (the test-mode button, or a pinched wire) does not fire a keystroke.
  unsigned long now = millis();
  for (uint8_t i = 0; i < COUNT; i++) {
    bool closed    = (digitalRead(INPUTS[i].pin) == LOW);
    rawState[i]    = closed;
    stableState[i] = closed;
    changedAt[i]   = now;
    keyIsDown[i]   = false;
    releaseAt[i]   = now;
  }

#ifdef LED_BUILTIN_TX
  pinMode(LED_BUILTIN_TX, OUTPUT);
  digitalWrite(LED_BUILTIN_TX, HIGH);   // this LED is inverted: HIGH = off
#endif

  Keyboard.begin();
  Keyboard.releaseAll();
}

void fire(uint8_t i, unsigned long now) {
  if (testMode) {
    Keyboard.print(INPUTS[i].label);
    Keyboard.write(KEY_RETURN);
    return;
  }
  Keyboard.press(INPUTS[i].key);
  keyIsDown[i] = true;
  releaseAt[i] = now + KEY_HOLD_MS;
}

void loop() {
  unsigned long now = millis();

  for (uint8_t i = 0; i < COUNT; i++) {
    bool closed = (digitalRead(INPUTS[i].pin) == LOW);   // LOW = pressed

    if (closed != rawState[i]) {
      // Reading changed -- restart the debounce timer and wait it out.
      rawState[i]  = closed;
      changedAt[i] = now;
    } else if (closed != stableState[i] &&
               (now - changedAt[i]) >= DEBOUNCE_MS) {
      // Reading has been steady long enough to trust it.
      stableState[i] = closed;
      if (closed) {
        fire(i, now);        // press edge only -- holding never auto-repeats
      }
    }

    // Release the key once its hold time is up (cast handles millis rollover).
    if (keyIsDown[i] && (long)(now - releaseAt[i]) >= 0) {
      Keyboard.release(INPUTS[i].key);
      keyIsDown[i] = false;
    }
  }

#ifdef LED_BUILTIN_TX
  if (testMode && (now - lastBlink) >= 500) {
    lastBlink = now;
    blinkOn   = !blinkOn;
    digitalWrite(LED_BUILTIN_TX, blinkOn ? LOW : HIGH);
  }
#endif
}
