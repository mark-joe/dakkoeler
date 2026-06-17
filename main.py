import network
import utime
from machine import Pin, ADC, WDT
from netman import connectWiFi
from ms_utils import blinkN, which_pico, get_datetime, set_SMPS_PWM, is_dst
import ntptime2
from secrets import secrets
from umqttsimple import MQTTClient
import onewire
import ds18x20
import json
import collections
import math
from ota import OTAUpdater

# https://raw.githubusercontent.com/mark-joe/dakkoeler/refs/heads/main/version.json

# Check for OTA updates
#    repo_name = "pico-OTA"
#    branch = "main"
#    firmware_url = f"https://github.com/dblanding/{repo_name}/{branch}/"
#    ota_updater = OTAUpdater(firmware_url, "main.py", "ota.py")
#    ota_updater.download_and_install_update_if_available()

# the next is just for mqtt output
f = open('version.json')
version = json.load(f)
VERSION = version['version']
f.close()

DEBUG = True

PROJECT = 'dakkoeler'
keepalive = 600 # mqtt, publish is div 10
use_WDT = True
if DEBUG: 
    keepalive = 60
    use_WDT = False
NTP_UPDATE_INTERVAL = 86400
HIGH_TEMP = 40.0

def mqtt_connect(): 
    mqtt_server = secrets['mqtt_server']
    client = MQTTClient(pico_id, mqtt_server, keepalive=keepalive, user=secrets['mqtt_user'], password=secrets['mqtt_password'])
    client.connect()
    print('Connected to %s MQTT Broker'%(mqtt_server))
    blinkN(5,led)
    return client

def reconnect():
    print('Failed to connect to MQTT Broker. Rebooting ...')
    utime.sleep(10)
    machine.reset()
    
def sub_cb(topic, msg):
    global updown
    global HIGH_TEMP
        
    if use_WDT: wdt.feed()
    if DEBUG: print("New message on topic {}".format(topic.decode('utf-8')))
    if DEBUG: print("Message: {}".format(msg.decode('utf-8')))

    if topic.decode('utf-8') == 'sun/updown':
        updown = json.loads(msg)
    if topic.decode('utf-8') == 'dakkoeler/set_high_temp':
        HIGH_TEMP = float(msg.decode('utf-8'))
    if topic.decode('utf-8') == 'dakkoeler/restart':
        print("mqtt restart pico")
        blinkN(5)
        machine.reset()

set_SMPS_PWM()
led = Pin('LED', Pin.OUT)
blinkN(2, led)

# physical pin 6 -> gpio 4
p = Pin(4, Pin.IN, Pin.PULL_UP)
# onewire needs external pullup resistor of 4K7, the pico ones are too high, and hence too slow
ow = onewire.OneWire(p)
ds = ds18x20.DS18X20(ow)
roms = ds.scan()
# if len(roms) == 0: PROJECT = PROJECT + '-test'

bootlog = "boot.txt"
fp = open(bootlog,"a")
fp.write("restart -- ")

wlan = connectWiFi(secrets['wlan_ssid'],secrets['wlan_password'],secrets['wlan_country'])
pico_id = which_pico(wlan)
print("pico_id", pico_id)
fp.write("wifi is up -- ")
blinkN(3,led)
    
ntptime2.settime()
(date,tme)=get_datetime()
last_ntp_update = utime.time()
fp.write("ntp: " + date + " " + tme + ' (UTC) -- ')
last_boot = date + " " + tme + ' (UTC)'
blinkN(4,led)

# Check for OTA updates
repo_name = PROJECT
branch = "main"
firmware_url = f"https://github.com/mark-joe/{repo_name}/{branch}/"
ota_updater = OTAUpdater(firmware_url,"main.py")
# ota_updater.check_for_updates()
ota_updater.download_and_install_update_if_available()

try:
    client = mqtt_connect()
except OSError as e:
    reconnect()

fp.write("mqtt is up\n")
fp.close()

water_switch = Pin(10, Pin.OUT)
water_switch.off()
onoff = False
for i in range(3):
    water_switch.on()
    utime.sleep(.75)
    water_switch.off()
    utime.sleep(.75)

updown = None
client.set_callback(sub_cb)
topic_sub = b'sun/updown'
client.subscribe(topic_sub, qos=0)
topic_sub = b'dakkoeler/set_high_temp'
client.subscribe(topic_sub, qos=0)
topic_sub = b'dakkoeler/restart'
client.subscribe(topic_sub, qos=0)

wdt = None
if use_WDT: wdt = WDT(timeout=5000)  # max 8388 millisecs
last_publish = utime.time()     # in seconds

while True:  # loop takes about 2 seconds
    try:
        while client.check_msg() != None: utime.sleep(0.2)
    except OSError as error:
        (date,tme)=get_datetime()
        fp = open("errors.txt","a")
        fp.write(date + " " + tme + " " + error + "\n")
        fp.close()
        print(error)
    
    if use_WDT: wdt.feed()

    diff_publish = utime.time() - last_publish
    if diff_publish > (keepalive / 10):
        if DEBUG: print("time for a publish", diff_publish)
        last_publish = utime.time()
        client.publish("%s/last_boot"%PROJECT, last_boot, retain=False, qos=0)
        client.publish("%s/temperature"%PROJECT, "%.1f" % temp, retain=False, qos=0)
        client.publish("%s/high_temp"%PROJECT, "%.1f" % HIGH_TEMP, retain=False, qos=0)
        client.publish("%s/wlan_ssid"%PROJECT, wlan.config('ssid'), retain=False, qos=0)
        client.publish("%s/wlan_rssi"%PROJECT, str(wlan.status('rssi')), retain=False, qos=0)
        client.publish("%s/wlan_ip"%PROJECT, str(wlan.ifconfig()[0]), retain=False, qos=0)
        client.publish("%s/whoami"%PROJECT, pico_id, retain=False, qos=0)
        (date,tme)=get_datetime()
        client.publish("%s/heartbeat"%PROJECT, date + " " + tme + ' (UTC)')
        client.publish("%s/water_switch"%PROJECT, str(onoff), retain=False, qos=0)
        client.publish("%s/version"%PROJECT, str(VERSION), retain=False, qos=0)
        if updown != None: client.publish("%s/sunset"%PROJECT, updown['sunset'] + ' (UTC)', retain=False, qos=0)

        dic = collections.OrderedDict()
        dic['last_boot']=last_boot
        dic['last_temperature']=temp
        dic['wlan_ssid']=wlan.config('ssid')
        dic['wlan_RSSI']=wlan.status('rssi')
        dic['wlan_ip']=str(wlan.ifconfig()[0])
        dic['whoami']=pico_id
        dic['version']=VERSION
        dic['heartbeat']=date + " " + tme + ' (UTC)'
        dic['water_switch']=onoff
        if updown != None: dic['sunset']=updown['sunset'] + ' (UTC)'

        s = json.dumps(dic)
        client.publish("%s/json"%PROJECT, s, retain=False, qos=1) # QOS set to 1 to verify connection

    if len(roms)>0:
        try:
            ds.convert_temp()  # max 750 ms it takes
            utime.sleep(1.0)
            temp = ds.read_temp(roms[0])
        except Exception as error:
            (date,tme)=get_datetime()
            fp = open("errors.txt","a")
            fp.write(date + " " + tme + " " + error + "\n")
            fp.close()
            print(error)
            temp = -1.0
    else:
        temp = 55.5
        utime.sleep(1.0)

    unix_time = utime.time()       
    if unix_time > (last_ntp_update + NTP_UPDATE_INTERVAL):
        pre = utime.time()
        ntptime2.settime(wdt)  # wdt is on
        delta = utime.time() - pre
        last_ntp_update = utime.time()
        (date,tme)=get_datetime()
        if DEBUG:
            print("ntp post update: delta:%d " % delta + date + " " + tme + ' (UTC) -- ')
        fp = open(bootlog,"a")
        fp.write("ntp post update: delta:%d " % delta + date + " " + tme + ' (UTC) \n')
        fp.close()

    onoff = bool(water_switch.value())
    if temp > HIGH_TEMP:
        if not onoff:
            water_switch.on()
    else:
        if onoff:
            water_switch.off()
        
    if DEBUG:
        (date,tme)=get_datetime()
        print(date + " " + tme + ' (UTC)')
        print("Read temp", temp)
        print("RSSI", str(wlan.status('rssi')))
    blinkN(1,led)
