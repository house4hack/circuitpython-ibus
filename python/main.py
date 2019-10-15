import time
import ibus
import sys
import busio
import board

uart = busio.UART(board.TX, board.RX, baudrate=115200, timeout=ibus.PROTOCOL_GAP)

class IBUSsensor():
    def __init__(self):
        self.counter = 0

    def update_measurements(self):
        self.counter += 1
        if self.counter >= 1000:
            self.counter = 0

        measurements = [self.counter]
        return measurements


class IBUSservo():
    def __init__(self, channel):
        self.channel = channel

    def servo_cb(self, data_arr):
        if data_arr[self.channel]> 1500:
            print("On")
        else:
            print("Off")


        

sensor_types = [ibus.IBUSS_ALT]

doSERVO = False

if not doSERVO:
    sensor = IBUSsensor()
    ib = ibus.IBUS(uart, sensor_types, sensor.update_measurements, do_log = False)
    ib.start_loop()
else:
    servo = IBUSservo(1)
    ib = ibus.IBUS(uart, sensor_types, servo_cb=servo.servo_cb, do_log=True)
    ib.start_loop()




