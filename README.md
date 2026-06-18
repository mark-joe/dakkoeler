# dakkkoeler (aka roof cooler)
This is not a general working solution for you. You can use it as inspiration. 
This repository features as the source for over the air updates.

Raspberry Pico program to read temperature of roof and if it is too hot, open water valve to cool down

Features ds18x20 as temperature probe, a Panasonic JW2SN-DC5V relay (via 470 Ohm and BC337) to steer water valve (JP fluid control CS1 230V AC).

select strongest WiFi, NTP time, over the air update (OTA), and MQTT to read and write data and instructions

