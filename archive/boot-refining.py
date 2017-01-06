# This file is executed on every boot (including wake-boot from deepsleep)

# Garbage collection

import gc
import micropython
import machine
import time
import socket
import network
import ubinascii

#int_counter = 0
flag_queue = []
#pin_flag = None
light = None
uid = None
p = None
gc.collect()

# This is for the web based python console. I figure we don't need this right now
# but it might be helpful later once we get the wifi going and aren't hooked up to
# a computer.

#import webrepl
#webrepl.start()

# Now let's mess with networking. The ESP8266 actually has two interfaces: one that 
# can act as an AP and another that can connect to an existing network. I /think/ they
# both can stay on.

# The challenge here will be coming up with a way to automatically do this. Maybe we 
# need to add bluetooth or something so that you can set this up from a phone? We 
# certainly can't expect people to edit this file.

def do_connect():
    import network
    global uid
    sta_if = network.WLAN(network.STA_IF)
    ap_if = network.WLAN(network.AP_IF)
    if not sta_if.isconnected():
        print('Connecting to network...')
        sta_if.active(True)
        sta_if.connect('Railroad', '4029816110')
        while not sta_if.isconnected():
            pass
    print('network config:', sta_if.ifconfig())
    mac = ubinascii.hexlify(sta_if.config('mac'),':').decode()
    uid = mac.replace(":", "")
    if sta_if.isconnected():
        ap_if.active(False)

# Now we'll call that method.
print("After do_connect defined")
do_connect()

# We need this in case there is a problem in the interrupt handler, otherwise we won't
# see any exceptions. More info here: 
# http://docs.micropython.org/en/latest/pyboard/reference/isr_rules.html#micropython-issues

micropython.alloc_emergency_exception_buf(100)

# We can keep this in the final version if we want, and have a single LED to indicate
# switch activity (or, more importantly, the fact that we caught the activity)

# The ESP8266 has an LED on it at GPIO 16 (D0). We can probably just use that. 

light = machine.Pin(16, machine.Pin.OUT)

# This method is called by the main loop and handles sending the information to the cloud.
# See the notes for changes that need to be made to make it more elegant/robust. 

# Assuming this can take longer than the the loop speed of the main loop and that multiple
# switch events could happen quickly, should we set up a queue? Or would python already
# queue up the calls to this method?

def post_to_cloud(p):
    global uid
    pin_num = str(p)
    print("posting")
    #todo Need to redo this so that it a) retries on fail and b) doesn't resolve the host address each time
    url = 'http://data.sparkfun.com/input/RMxK6xlqr8CbmMnQAnoJ?private_key=lzEe5EopAVcYAVvWEv7N&id=%s&pin=%s' % (uid, pin_num[4])
    _, _, host, path = url.split('/', 3)
    addr = socket.getaddrinfo(host, 80)[0][-1]
    so = socket.socket()
    so.connect(addr)
    so.send(bytes('GET /%s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, host), 'utf8'))
    if data:
        print(str(data, 'utf8'), end='')

# This is our interrupt handler, also called an Interrupt Service Routine (ISR). It's called
# when an interrupt happens. The interrupt passes the GPIO pin number to this method, and we
# use that to set a var that the main loop looks for. When the main loop sees that var, it
# takes over the processing.

def irq_handler(p):
    global flag_queue
    #state = machine.disable_irq()
    print("irq in")
    #global int_counter
    #global pin_flag
    if not len(flag_queue)==4:
        flag_queue.insert(0, p)
    else:
        print("ignoring")
    #pin_flag = p
    print("irq out")
    time.sleep_ms(20)
    #machine.enable_irq(state) # disable works, but this crashes

# This is the main loop. Things happen here.

def main_loop(**kwargs):
    #global pin_flag
    global flag_queue
    print("Main_loop started")

# Assigning names to each GPIO used for coin switch interrupts. These pins are hooked directly 
# to the transistors on the MC board. 

    coin1 = machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_UP) #Left
    coin2 = machine.Pin(4, machine.Pin.IN, machine.Pin.PULL_UP)
    coin3 = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP) #Center
    coin4 = machine.Pin(2, machine.Pin.IN, machine.Pin.PULL_UP)

# These are our interrupts. They're set up to watch for the GPIO to rise from low to high
# and has the int_handler method as the callback. These are super sensitive, so we may need 
# to add code or hardware to debounce.

    coin1.irq(trigger=coin1.IRQ_FALLING, handler=irq_handler)
    coin2.irq(trigger=coin2.IRQ_FALLING, handler=irq_handler)
    coin3.irq(trigger=coin3.IRQ_FALLING, handler=irq_handler)
    coin4.irq(trigger=coin4.IRQ_FALLING, handler=irq_handler)
    
    while True:
        light.high() # Resets LED
        if flag_queue:
            #print("flag in")
            light.low() # Indicates activity for one loop.
            print(flag_queue)
            try: # Cheating. Need a better handler that will re-post if error
                post_to_cloud(flag_queue.pop())
            except:
                print("something went wrong posting")
            #post_to_cloud(pin_flag)
            #pin_flag = None
            #print("flag OUT")
        time.sleep(0.1)

main_loop()

# Almost all of this should be moved to main.py at some point. This file is just to set up
# all the system stuff.

