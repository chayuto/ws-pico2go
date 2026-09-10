from machine import Pin
import machine
import time
import rp2

@rp2.asm_pio(out_shiftdir=0, autopull=True, pull_thresh=12, autopush=True, push_thresh=12, sideset_init=(rp2.PIO.OUT_LOW), out_init=rp2.PIO.OUT_LOW)
def spi_cpha0():
    out(pins, 1)             .side(0x0)   [1]
    in_(pins, 1)             .side(0x1)   [1]
        
class TRSensor():
    def __init__(self):
        self.numSensors = 5
        self.calibratedMin = [0] * self.numSensors
        self.calibratedMax = [1023] * self.numSensors
        self.last_value = 0
        self.Clock     = 6
        self.Address   = 7
        self.DataOut   = 27
        self.CS        = Pin(28, Pin.OUT)
        self.CS.value(1)
        self.sm = rp2.StateMachine(1, spi_cpha0, freq=4*200000, sideset_base=Pin(self.Clock, Pin.OUT), out_base=Pin(self.Address, Pin.OUT), in_base=Pin(self.DataOut, Pin.IN))
        self.sm.active(1)
        
    """
    Reads the sensor values into an array. There *MUST* be space
    for as many values as there were sensors specified in the constructor.
    Example usage:
    unsigned int sensor_values[8];9
    sensors.read(sensor_values);
    The values returned are a measure of the reflectance in abstract units,
    with higher values corresponding to lower reflectance (e.g. a black
    surface or a void).
    """     
    def AnalogRead(self):
        value = [0]*(self.numSensors+1)
        
        #Read Channel~channe5 AD value
        for j in range(0,self.numSensors+1):
            self.CS.value(0)
            #set channe
            self.sm.put(j << 28)
            #get last channe value
            value[j] = self.sm.get() & 0xfff
            self.CS.value(1)
            value[j] >>= 2
        time.sleep_ms(2)
        return value[1:]
    
    """
    Reads the sensors 10 times and uses the results for
    calibration.  The sensor values are not returned; instead, the
    maximum and minimum values found over time are stored internally
    and used for the readCalibrated() method.
    """
    def calibrate(self):
        max_sensor_values = [0]*self.numSensors
        min_sensor_values = [0]*self.numSensors
        for j in range(0,10):
        
            sensor_values = self.AnalogRead();
            
            for i in range(0,self.numSensors):
            
                # set the max we found THIS time
                if((j == 0) or max_sensor_values[i] < sensor_values[i]):
                    max_sensor_values[i] = sensor_values[i]

                # set the min we found THIS time
                if((j == 0) or min_sensor_values[i] > sensor_values[i]):
                    min_sensor_values[i] = sensor_values[i]

        # record the min and max calibration values
        for i in range(0,self.numSensors):
            if(min_sensor_values[i] > self.calibratedMin[i]):
                self.calibratedMin[i] = min_sensor_values[i]
            if(max_sensor_values[i] < self.calibratedMax[i]):
                self.calibratedMax[i] = max_sensor_values[i]
        
    """
    Returns values calibrated to a value between 0 and 1000, where
    0 corresponds to the minimum value read by calibrate() and 1000
    corresponds to the maximum value.  Calibration values are
    stored separately for each sensor, so that differences in the
    sensors are accounted for automatically.
    
    """  
    def readCalibrated(self):
        value = 0
        sensor_values = self.AnalogRead()
        
        for i in range (0,self.numSensors):
            denominator = self.calibratedMax[i] - self.calibratedMin[i]

            if(denominator != 0):
                value = (sensor_values[i] - self.calibratedMin[i])* 1000 / denominator

            if(value < 0):
                value = 0
            elif(value > 1000):
                value = 1000

            sensor_values[i] = int(value)

        return sensor_values

    """
    Operates the same as read calibrated, but also returns an
    estimated position of the robot with respect to a line. The
    estimate is made using a weighted average of the sensor indices
    multiplied by 1000, so that a return value of 0 indicates that
    the line is directly below sensor 0, a return value of 1000
    indicates that the line is directly below sensor 1, 2000
    indicates that it's below sensor 2000, etc.  Intermediate
    values indicate that the line is between two sensors.  The
    formula is:

       0*value0 + 1000*value1 + 2000*value2 + ...
       --------------------------------------------
             value0  +  value1  +  value2 + ...

    By default, this function assumes a dark line (high values)
    surrounded by white (low values).  If your line is light on
    black, set the optional second argument white_line to true.  In
    this case, each sensor value will be replaced by (1000-value)
    before the averaging.
    """
    def readLine(self, white_line = 0):
        sensor_values = self.readCalibrated()
        avg = 0
        sum = 0
        on_line = 0
        for i in range(0,self.numSensors):
            value = sensor_values[i]
            if(white_line):
                value = 1000-value
            # keep track of whether we see the line at all
            if(value > 200):
                on_line = 1
                
            # only average in values that are above a noise threshold
            if(value > 50):
                avg += value * (i * 1000);  # this is for the weighted total,
                sum += value;               # this is for the denominator 

        if(on_line != 1):
            # If it last read to the left of center, return 0.
            if(self.last_value < (self.numSensors - 1)*1000/2):
                #print("left")
                self.last_value = 0;

            # If it last read to the right of center, return the max.
            else:
                #print("right")
                self.last_value = (self.numSensors - 1)*1000
        else:
            self.last_value = avg/sum

        return int(self.last_value),sensor_values

if __name__ == '__main__':

    print("\nTRSensor Test Program ...\r\n")
    TRS=TRSensor()
    while True:
        print(TRS.AnalogRead())
        time.sleep(0.1)
                