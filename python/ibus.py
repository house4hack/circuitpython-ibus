import time

IBUSS_INTV    = 0 # Internal voltage (in 0.01)
IBUSS_TEMP    = 1 # Temperature (in 0.1 degrees, where 0=-40'C)
IBUSS_RPM     = 2 # RPM
IBUSS_EXTV    = 3 # External voltage (in 0.1V)
IBUSS_VIBB    = 4 # Not defined, used by vibration MSB = Left, LSB = Right
IBUSS_MAXALT  = 5
IBUSS_ALT     = 6

BASE_TEMP = -40
BASE_ALT  = -100

#protocol constants
PROTOCOL_GAP = 0.003
PROTOCOL_SERVO = 0x40
PROTOCOL_PING = 0x80
PROTOCOL_TYPES = 0x90
PROTOCOL_MEAS = 0xA0
PROTOCOL_CHANNELS = 14
PROTOCOL_OVERHEAD = 3
PROTOCOL_LENGTH = 0x20

# read state engine
MEASURE = -1
NEW = 0
READING = 1
DONE = 2


class IBUS():

    def __init__(self, uart, sensor_types, user_fn=None, servo_cb=None, do_log = False):
        self.uart = uart
        self.sensor_types = sensor_types
        self.user_fn = user_fn
        self.servo_cb = servo_cb
        self.type_msgs = [self.make_type_msg(PROTOCOL_TYPES + 1 + adr, st) for adr, st in enumerate(sensor_types)]
        self.ping_msgs = [self.make_ping_msg(PROTOCOL_PING + 1 +adr) for adr, _ in enumerate(sensor_types)]
        default_measurements = [0] * len(sensor_types)
        self.meas_msgs = self.update_measurements(default_measurements)
        self.log_print = 0
        self.do_log = do_log

    def log(self, value):
        if self.do_log:
            if self.log_print==0:
                print(value)
                self.log_print = 100
            else:
                self.log_print -=1
            if self.log_print % 100 ==0:
                print(".")


    def read_not_none(self):
        data = self.uart.read(1)
        while data is None:
            data = self.uart.read(1)
        return data 


    def write_and_ignore(self, data, length=None):
        length = len(data)
        self.uart.write(data, length)
        time.sleep(PROTOCOL_GAP)
        self.uart.reset_input_buffer()



    def checksum(self, arr,initial= 0):
        sum = initial
        for a in arr:
            sum += a
        checksum = 0xFFFF - sum
        chA = checksum >> 8
        chB = checksum & 0xFF
        return chA, chB

    def calc_checksum(self, arr):
        chA, chB = self.checksum(arr)
        arr[-1] = chA
        arr[-2] = chB
        return arr

    def make_measure_msg(self, address, value):
        msg = bytearray([0x06, address, 0x00, 0x00, 0x00, 0x00])
        msg[2] = value & 0xFF
        msg[3] = value >> 8
        msg = self.calc_checksum(msg)
        return msg


    def make_type_msg(self, address, sens_type):
        msg = bytearray([0x06, address, sens_type, 0x02, 0x00, 0x00])
        msg = self.calc_checksum(msg)
        return msg

    def make_ping_msg(self, address):
        msg = bytearray([0x04, address, 0x00, 0x00])
        msg = self.calc_checksum(msg)
        return msg


    def clear_buffer(self):
        self.uart.reset_input_buffer()
        

    def prep_measurement(self, adr, val):
        if self.sensor_types[adr] == IBUSS_TEMP:
            val = int((val - BASE_TEMP)*10)
        elif self.sensor_types[adr] == IBUSS_INTV:
            val = int(val * 100)
        elif self.sensor_types[adr] == IBUSS_ALT:
            val = int((val - BASE_ALT)*10)
        else:
            val = int(val)
        return val

    def update_measurements(self, measurements):
        prep = [self.prep_measurement(i, val) for i, val in enumerate(measurements)]
        meas_msgs = [self.make_measure_msg(PROTOCOL_MEAS + 1 + adr, val) for adr, val in enumerate(prep)]
        return meas_msgs


    def decode_servo(self, servo_data):
        result = [0] * PROTOCOL_CHANNELS
        for i in range(PROTOCOL_CHANNELS):
            result[i] = servo_data[i*2 + 1] | ( servo_data[i*2 + 2] << 8)
            
        return result

    def start_loop(self):
        state = MEASURE

        expected_len = 0
        last_command = 0
        last_read = time.monotonic()

        while True: 
            if state == MEASURE:
                self.log("updated")
                #  Any measurement logic goes here #
                if self.user_fn is not None:
                    measurements = self.user_fn()

                    self.meas_msgs = self.update_measurements(measurements)
                    self.clear_buffer()
                state = NEW

            data = self.read_not_none()

            if (state != NEW) and (time.monotonic() - last_read > 0.1):
                state = NEW
                if self.do_log:
                    print("reset ")

            if state == NEW:
                expected_len = data[0]-1
                if expected_len < PROTOCOL_LENGTH and expected_len >= PROTOCOL_OVERHEAD:
                    data_arr = bytearray(expected_len)
                    total_read = self.uart.readinto(data_arr)
                    if total_read == expected_len:
                        state = DONE
                    else: 
                        if self.do_log:
                            print('<<<<<')
                            print(total_read, expected_len)
                        state = NEW

            if state == DONE: 

                cmd = data_arr[0] & 0xf0
                adr = data_arr[0] & 0x0f


                chA_r = data_arr[-1]
                chB_r = data_arr[-2]
                chA, chB = self.checksum(data_arr[:-2], expected_len+1)
                if(chA_r == chA) and (chB_r == chB_r):
                    
                    
                    if cmd == PROTOCOL_PING:
                        # ping
                        if adr <= len(self.sensor_types):
                            self.write_and_ignore(self.ping_msgs[adr-1])
                        
                    elif cmd == PROTOCOL_TYPES:
                        # sensor type
                        self.write_and_ignore(self.type_msgs[adr-1])

                    elif cmd == PROTOCOL_MEAS:
                        # sensor reading
                        self.write_and_ignore(self.meas_msgs[adr-1])

                    elif cmd == PROTOCOL_SERVO:
                        # servos
                        if self.servo_cb is not None:
                            self.servo_cb(self.decode_servo(data_arr))

                    if cmd == PROTOCOL_MEAS and adr == len(self.sensor_types):
                        state = MEASURE
                    else:
                        state = NEW

                else:
                    if self.do_log:
                        print("Checksum failed")
                        print(hex(last_command))
                        print(data_arr)
                    state = NEW

                last_command = cmd +adr

            last_read= time.monotonic()

