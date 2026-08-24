#
# Thermostat - This is the Python code used to demonstrate
# the functionality of the thermostat that we have prototyped throughout
# the course.
#
# This code works with the test circuit that was built for module 7.
#
# Functionality:
#
# The thermostat has three states: off, heat, cool
#
# The lights will represent the state that the thermostat is in.
#
# If the thermostat is set to off, the lights will both be off.
#
# If the thermostat is set to heat, the Red LED will be fading in
# and out if the current temperature is below the set temperature;
# otherwise, the Red LED will be on solid.
#
# If the thermostat is set to cool, the Blue LED will be fading in
# and out if the current temperature is above the set temperature;
# otherwise, the Blue LED will be on solid.
#
# One button will cycle through the three states of the thermostat.
#
# One button will raise the setpoint by a degree.
#
# One button will lower the setpoint by a degree.
#
# The LCD display will display the date and time on one line and
# alternate the second line between the current temperature and
# the state of the thermostat along with its set temperature.
#
# The Thermostat will send a status update to the TemperatureServer
# over the serial port every 30 seconds in a comma delimited string
# including the state of the thermostat, the current temperature
# in degrees Fahrenheit, and the setpoint of the thermostat.
#
#------------------------------------------------------------------
# Change History
#------------------------------------------------------------------
# Version   |   Description
#------------------------------------------------------------------
#    1          Initial Development
#    2          Completed final project thermostat functionality
#------------------------------------------------------------------

from time import sleep
from datetime import datetime

from statemachine import StateMachine, State

import board
import adafruit_ahtx0

import digitalio
import adafruit_character_lcd.character_lcd as characterlcd

import serial

from gpiozero import Button, PWMLED

from threading import Thread

from math import floor

DEBUG = True

# Create I2C instance and initialize AHT20 sensor.
i2c = board.I2C()
thSensor = adafruit_ahtx0.AHTx0(i2c)

# Initialize UART serial connection: 115200 baud, 8-N-1.
ser = serial.Serial(
    port='/dev/ttyS0',
    baudrate=115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# Heating and cooling indicator LEDs.
redLight = PWMLED(18)
blueLight = PWMLED(23)


class ManagedDisplay:
    """Manage the 16x2 LCD display."""

    def __init__(self):
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)

        self.lcd_columns = 16
        self.lcd_rows = 2

        self.lcd = characterlcd.Character_LCD_Mono(
            self.lcd_rs,
            self.lcd_en,
            self.lcd_d4,
            self.lcd_d5,
            self.lcd_d6,
            self.lcd_d7,
            self.lcd_columns,
            self.lcd_rows
        )

        self.lcd.clear()

    def cleanupDisplay(self):
        self.lcd.clear()
        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()

    def clear(self):
        self.lcd.clear()

    def updateScreen(self, message):
        self.lcd.clear()
        self.lcd.message = message


screen = ManagedDisplay()


class TemperatureMachine(StateMachine):
    """A state machine designed to manage the thermostat."""

    off = State(initial=True)
    heat = State()
    cool = State()

    # Required default set point.
    setPoint = 72

    cycle = (
        off.to(heat) |
        heat.to(cool) |
        cool.to(off)
    )

    def on_enter_heat(self):
        # Update the heating indicator based on room temperature.
        self.updateLights()

        if DEBUG:
            print("* Changing state to heat")

    def on_exit_heat(self):
        # Make certain the red LED is disabled when leaving heat mode.
        redLight.off()

    def on_enter_cool(self):
        # Update the cooling indicator based on room temperature.
        self.updateLights()

        if DEBUG:
            print("* Changing state to cool")

    def on_exit_cool(self):
        # Make certain the blue LED is disabled when leaving cool mode.
        blueLight.off()

    def on_enter_off(self):
        # Both LEDs are off while the thermostat is off.
        redLight.off()
        blueLight.off()

        if DEBUG:
            print("* Changing state to off")

    def processTempStateButton(self):
        if DEBUG:
            print("Cycling Temperature State")

        # Move OFF -> HEAT -> COOL -> OFF.
        self.cycle()

    def processTempIncButton(self):
        if DEBUG:
            print("Increasing Set Point")

        self.setPoint += 1
        self.updateLights()

    def processTempDecButton(self):
        if DEBUG:
            print("Decreasing Set Point")

        self.setPoint -= 1
        self.updateLights()

    def updateLights(self):
        # Compare whole-degree Fahrenheit temperature to the set point.
        temp = floor(self.getFahrenheit())

        # Stop any previous LED action before applying the current state.
        redLight.off()
        blueLight.off()

        if DEBUG:
            print(f"State: {self.current_state.id}")
            print(f"SetPoint: {self.setPoint}")
            print(f"Temp: {temp}")

        if self.current_state == self.heat:
            # Heating is actively required when the room is below set point.
            if temp < self.setPoint:
                redLight.pulse()
            else:
                redLight.on()

        elif self.current_state == self.cool:
            # Cooling is actively required when the room is above set point.
            if temp > self.setPoint:
                blueLight.pulse()
            else:
                blueLight.on()

        else:
            # OFF state leaves both LEDs disabled.
            redLight.off()
            blueLight.off()

    def run(self):
        myThread = Thread(target=self.manageMyDisplay)
        myThread.start()

    def getFahrenheit(self):
        t = thSensor.temperature
        return ((9 / 5) * t) + 32

    def setupSerialOutput(self):
        # Required comma-delimited format:
        # state,current temperature,set point
        output = (
            f"{self.current_state.id},"
            f"{self.getFahrenheit():.1f},"
            f"{self.setPoint}\n"
        )
        return output

    endDisplay = False

    def manageMyDisplay(self):
        counter = 1
        altCounter = 1

        while not self.endDisplay:
            if DEBUG:
                print("Processing Display Info...")

            current_time = datetime.now()

            # First LCD line: date and current time.
            lcd_line_1 = current_time.strftime("%m/%d %H:%M:%S") + "\n"

            # Second LCD line alternates between current temperature
            # and thermostat state/set point.
            if altCounter < 6:
                current_temp = self.getFahrenheit()
                lcd_line_2 = f"Temp: {current_temp:.1f} F"
                altCounter += 1
            else:
                state_text = self.current_state.id.capitalize()
                lcd_line_2 = f"{state_text} SP:{self.setPoint} F"
                altCounter += 1

                if altCounter >= 11:
                    # Refresh status lights every 10 seconds.
                    self.updateLights()
                    altCounter = 1

            # Keep the second line within the LCD's 16-character width.
            lcd_line_2 = lcd_line_2[:16]
            screen.updateScreen(lcd_line_1 + lcd_line_2)

            if DEBUG:
                print(f"Counter: {counter}")

            # Send thermostat status to the server every 30 seconds.
            if (counter % 30) == 0:
                ser.write(self.setupSerialOutput().encode("utf-8"))
                counter = 1
            else:
                counter += 1

            sleep(1)

        screen.cleanupDisplay()


# Setup the thermostat state machine and display thread.
tsm = TemperatureMachine()
tsm.run()

# GPIO 24: cycle OFF -> HEAT -> COOL -> OFF.
greenButton = Button(24)
greenButton.when_pressed = tsm.processTempStateButton

# GPIO 25: increase set point by 1 degree Fahrenheit.
redButton = Button(25)
redButton.when_pressed = tsm.processTempIncButton

# GPIO 12: decrease set point by 1 degree Fahrenheit.
blueButton = Button(12)
blueButton.when_pressed = tsm.processTempDecButton

repeat = True

while repeat:
    try:
        sleep(30)

    except KeyboardInterrupt:
        print("Cleaning up. Exiting...")

        repeat = False
        tsm.endDisplay = True

        # Turn off status LEDs and close UART cleanly.
        redLight.off()
        blueLight.off()

        if ser.is_open:
            ser.close()

        sleep(1)
