# This file is executed on every boot (including wake-boot from deepsleep)

# Be careful when editing for style here. Micropython is Diet Python. There are
# things that are simply not there and are worked around, or that follow
# examples directly from the micropython docs.

#### todo Major things to fix:

# This file is a fucking disaster. Need to part it out sooner than later.

import micropython
import machine
import time
import socket
import network
import ubinascii
import uhttpd
import http_file_handler
import webrepl
import default_api
import http_api_handler

# Garbage collection <- This was in the file to start, so I left it.

import gc
gc.collect() # What the hell is the point of running this first?

# setup vars <- I haven't learned a more reliable way of doing this yet.

pin_flag = None
irq_enable = True
flag_queue = []
#light = None
uid = None
p = None
pin_num = None
addr = None
host = None
path = None
state = None
int_retries = 0
time_at_last_heartbeat = 0
debounce_ms = 50
wifi_ssid = "default"
wifi_password = "wifidefault"
ap_ssid = "MissionCointrol"
ap_password = "adminDefault"
time_between_heartbeats_in_minutes = 3
datastore_fqdn = 'http://data.missionpinball.org/'
datastore_ip = '127.0.0.1'
webrepl_enable = "off"
use_webrepl = False

# datastore_logging_url must contain the domain name, but it isn't used for
# resolution. It's used after we resolve the address to get past host header
# checks.

datastore_logging_url = \
    "http://data.sparkfun.com/input/RMxK6xlqr8CbmMnQAnoJ?" \
    "private_key=lzEe5EopAVcYAVvWEv7N"

# We need this in case there is a problem in the interrupt handler, otherwise
# we won't see any exceptions. More info here:
# http://docs.micropython.org/en/latest/pyboard/reference/isr_rules.html#micropython-issues

micropython.alloc_emergency_exception_buf(100)

# The ESP8266 has an LED on it at GPIO 16 (D0). We'll use that to indicate that
# we caught switch activity and are uploading the data. Light turns on when
# switch is hit, off when data is finished uploading.

light = machine.Pin(16, machine.Pin.OUT)

def import_config():
    global wifi_ssid
    global wifi_password
    global ap_ssid
    global ap_password
    global debounce_ms
    global time_between_heartbeats_in_minutes
    global datastore_fqdn
    global datastore_ip
    global use_webrepl
    global webrepl_enable
    global datastore_logging_url

    try:
        config_dict = {}
        with open("/config.txt", "r") as config_file:
            for line in config_file:
                list = line.split(": ")
                config_dict[list[0]] = list[1].replace("\n", "")
        print(config_dict)
        wifi_ssid = str(config_dict["wifi_ssid"])
        wifi_password = str(config_dict["wifi_password"])
        ap_ssid = str(config_dict["ap_ssid"])
        ap_password = str(config_dict["ap_password"])
        time_between_heartbeats_in_minutes = int(config_dict[
                                        "time_between_heartbeats_in_minutes"])
        datastore_fqdn = str(config_dict["datastore_fqdn"]).replace("%3A", ":")
        datastore_fqdn = datastore_fqdn.replace("%2F", "/")
        datastore_ip = str(config_dict["datastore_ip"])
        try:
            webrepl_enable = str(config_dict["webrepl_enable"])
        except KeyError:
            webrepl_enable = "off"
        datastore_logging_url = str(
            config_dict["datastore_logging_url"]).replace("%3A", ":")
        datastore_logging_url = datastore_logging_url.replace("%2F", "/")

        if webrepl_enable == "on":
            use_webrepl = True
        else:
            use_webrepl = False
    except OSError:
        pass


# This is for the web based python console. It's helpful for when you have it
# plugged into a machine. You need to know the ESP8266 IP address, then visit
# http://micropython.org/webrepl/

def start_webrepl():
    if use_webrepl:
        webrepl.start()
    else:
        webrepl.stop()


# Now let's mess with networking. The ESP8266 actually has two interfaces:
# one that can act as an AP and another that can connect to an existing
# network.

def connect_sta():
    # Set up WLAN
    global uid
    global wifi_ssid
    global wifi_password
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        if not wifi_ssid == "default":
            print('Connecting to network...')
            sta_if.active(True)
            sta_if.connect(wifi_ssid, wifi_password)
            while not sta_if.isconnected():
                pass
    print('WiFi config: ', sta_if.ifconfig())
    mac = ubinascii.hexlify(sta_if.config('mac'),':').decode()
    uid = mac.replace(":", "")


def  setup_ap():
    # Set up AP

    global ap_ssid
    global ap_password

    # Turn off default AP connection
    network.WLAN(network.AP_IF).active(False)

    # Set up a new one
    ap_if = network.WLAN(network.AP_IF)
    if not ap_if.active():
        print('Setting up Access Point...')
        ap_if.active(True)
        ap_if.config(essid=ap_ssid, channel=11, password=ap_password)
    print("Access Point config: ", ap_if.ifconfig())


# This method builds the index.html file at boot, automatically populating the
# form object values with real information. That info is not real time - this
# file is generated at boot only, but that's ok because all of the info is only
# used at boot. So, this is a true snapshot of the configuration of this device

def build_config_index():
    print("building HTML")
    global wifi_ssid
    global wifi_password
    global ap_ssid
    global ap_password
    global addr
    global time_between_heartbeats_in_minutes
    global datastore_fqdn
    global datastore_ip

    # Check status of WebREPL
    try:
        wr_status = webrepl.listen_s
        if not str(wr_status)[14:15] == "0":
            web_repl_enabled = "unchecked"
        else:
            web_repl_enabled = "checked"
    except NameError:
        web_repl_enabled = "unchecked"

    html = """<!doctype html>
        <html>
        <head>
        <meta charset="UTF-8">
        <title>Mission Cointrol Configuration Manager</title>
        </head>
        
        <body>
         <form action="/api/submit.something" method="get">
          <h1>Current System Information</h1>
          <h2>Administration Configuration</h2>
           <label for="ap_ssid">Administration wireless network name (SSID):
           <i> This should be different for every game you have! </i></label>
           <input type="text" name="ap_ssid" id="ap_ssid" 
           value="{ap_ssid}"><br />
           <label for="ap_password">Administration wireless network password:
            </label><input type="text" name="ap_password" id="ap_password" 
            value="{ap_password}"><br />
           <label for="webrepl_enable">WebREPL enabled: </label>
           <input type="checkbox" name="webrepl_enable" id="webrepl_enable"
           {webrepl_enable}>
         
          <h2>Internet Connection Settings</h2>
           <label for="wifi_ssid">WiFi Network Name (SSID): </label>
           <input type="text" name="wifi_ssid" id="wifi_ssid" 
           value="{wifi_ssid}"><br />
           <label for="wifi_password">WiFi Network Password: </label>
           <input type="text" name="wifi_password" id="wifi_password" 
           value="{wifi_password}"><br />
           
          <h2>Data Collection Settings</h2> 
           <label for="time_between_heartbeats_in_minutes">Heartbeat Interval: 
           </label><input type="text" name="time_between_heartbeats_in_minutes"
            id="time_between_heartbeats_in_minutes" 
           value="{time_between_heartbeats_in_minutes}"><br />
           <label for="datastore_fqdn">Datastore FQDN: </label><input
           type="text" name="datastore_fqdn" id="datastore_fqdn"
           value="{datastore_fqdn}"><br />
           <label for="datastore_ip">Datastore IP Address: </label><input
           type="text" name="datastore_ip" id="datastore_ip"
           value="{datastore_ip}"><br />
           <label for="datastore_logging_url">Datastore Logging URL: </label>
           <input type="text" name="datastore_logging_url"
           id="datastore_logging_url" value="{datastore_logging_url}"><br />
          <br />
          
           <input type="submit" name="submit" id="submit" value="Submit">
           <input type="submit" name="cancel" id="cancel" value="Cancel">
         </form>
        </body>
        </html>""".format(ap_ssid=ap_ssid, ap_password=ap_password,
                          webrepl_enable=web_repl_enabled,
                          wifi_ssid=wifi_ssid,
                          wifi_password=wifi_password,
                          time_between_heartbeats_in_minutes=
                                     time_between_heartbeats_in_minutes,
                          datastore_fqdn=datastore_fqdn,
                          datastore_ip=datastore_ip,
                          datastore_logging_url=datastore_logging_url)

    f = open('www/index.html', 'w')
    f.write(html)
    f.close()


# I added this to break DNS resolution out of the post_to_cloud method. DNS
# resolution is slow, almost never works, and it causes a crash. So this method
# tries to resolve it, and if it can't it builds the tuple that the socket
# wants with a hardcoded IP address

def setup_data_connection():
    global addr
    global datastore_fqdn
    global datastore_ip

    try:
        addr = socket.getaddrinfo(datastore_fqdn, 80)[0][-1]
    except OSError:
        print("Couldn't resolve address. Hardcoding...")
        addr = datastore_ip, 80


# This method sets up the admin web interface. Pretty simple now, but we'll
# be adding an API file handler soon that will make this a bit more complex

def setup_httpd():
    api_handler = http_api_handler.Handler([(['submit.something'],
                                default_api.Handler())])

    admin_server = uhttpd.Server([('/api', api_handler), ('/',
                                http_file_handler.Handler('/www'))],
                                config={'bind_addr': '192.168.4.1'})
    admin_server.start()


# This method is called by the main loop and handles sending the information to
# the cloud. It watches for HTTP responses for 502 or 503 and, if it sees those
# it will retry up to 10 times. After 10 times, it will just stop (otherwise
# it will crash by reaching a recursion limit).

def post_to_cloud(p):
    global uid
    global pin_num
    global addr
    global host
    global path
    global int_retries
    global datastore_logging_url
    pin_num = str(p)
    params = '&id=%s&pin=%s' % (uid, pin_num[4])
    url = datastore_logging_url + params
    _, _, host, path = url.split('/', 3)
    if network.WLAN(network.STA_IF).active():
        try:
            print("posting")
            so = socket.socket()
            so.connect(addr)
            print("Socket connected")
            so.send(bytes('GET /%s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path,
                                                            host), 'utf8'))
            data = so.recv(12)
            so.close()
            if data:
                result = data.decode("utf-8")
                print("result: ", result) #[-9:])
                if result[-3:] == "503" or result[-3:] == "502":
                    if int_retries < 10:
                        print("Retrying...")
                        int_retries += 1
                        time.sleep_ms(2000)
                        post_to_cloud(pin_num)
                data = None
                result = None
        except:
            pass
    int_retries = 0


# We need to send a heartbeat every so often. time.ticks_diff is a uPython
# thing. If there is no coin activity, the beats should come right on time, but
# if there is coin switch activity between beats, it might be delayed by a few
# seconds by other activity in the main_loop. Really, this only matters for
# the logic we have on the web app, so there we just have to wait for a few
# missed beats before sending an alert.

def heartbeat(curr_time):
    global time_at_last_heartbeat

    if time.ticks_diff(curr_time, time_at_last_heartbeat) >= \
            (time_between_heartbeats_in_minutes * 60000) or \
                    time_at_last_heartbeat == 0:

        flag_queue.insert(0, '    9')
        time_at_last_heartbeat = curr_time


# This is our interrupt handler, also called an Interrupt Service Routine (ISR)
# It's called when an interrupt happens. The interrupt passes the GPIO pin
# number to this method, and we use that to set a var that the main loop looks
# for. When the main loop sees that var, it takes over the processing.

def irq_handler(p):
    global irq_enable
    global pin_flag

    # We set the irq_enable to False here. The IRQ remains active, but the
    # pin_flag = p code doesn't run again until after we debounce the first
    # activity and set the irq_enable flag to True in the main_loop.

    if irq_enable:
        print("IRQ")
        irq_enable = False
        pin_flag = p


# This is the main loop. Things happen here.

def main_loop(**kwargs):
    global pin_flag
    global flag_queue
    global state
    global debounce_ms
    global irq_enable
    print("Main_loop started")
    switch_active = 0

    while True:
        light.high() # Resets LED

        # This waits 'debounce_ms' before inserting the activity into the flag
        # queue. After the debounce loop runs, we reset pin_flag and set
        # irq_enable to True, which allows the IRQ handler to set the pin_flag
        # again.

        # This is very similar to other suggested ways of debouncing w/ uPython

        if pin_flag:

            while switch_active < debounce_ms:
                switch_active += 1
                time.sleep_ms(1)

            flag_queue.insert(0, pin_flag)
            pin_flag = None
            irq_enable = True
            switch_active = 0
            light.low() # Confirms that we caught a coin switch event

        if flag_queue:
            print(flag_queue)
            post_to_cloud(flag_queue.pop())
        heartbeat(time.ticks_ms()) # PyCharm doesn't like this, but it's legit


# Needed a place to set up interrupts.

def setup_interrupts():
    # Assigning names to each GPIO used for coin switch interrupts.

    coin1 = machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_UP) #Left
    coin2 = machine.Pin(4, machine.Pin.IN, machine.Pin.PULL_UP) #Center
    coin3 = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP) # This causes problems. Need to look into how to use GPIOs more
    coin4 = machine.Pin(2, machine.Pin.IN, machine.Pin.PULL_UP) # This causes problems

    # These are our interrupts. They're set up to watch for the GPIO to rise
    # from low to high and has the irq_handler method as the callback.

    coin1.irq(trigger=coin1.IRQ_RISING, handler=irq_handler)
    coin2.irq(trigger=coin2.IRQ_RISING, handler=irq_handler)
    coin3.irq(trigger=coin3.IRQ_RISING, handler=irq_handler)
    coin4.irq(trigger=coin4.IRQ_RISING, handler=irq_handler)


# And this pulls it all together

def init():
    import_config()
    setup_interrupts()
    setup_ap()
    start_webrepl()
    connect_sta()
    setup_data_connection()
    setup_httpd()
    build_config_index()
    main_loop()


init()

# Almost all of this should be moved to main.py at some point. This file is
# just to set up all the system stuff.

