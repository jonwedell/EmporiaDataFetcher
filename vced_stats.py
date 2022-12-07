#!/usr/bin/env python3

import json
import math
import os
import pathlib
import sys
import time

import grpc

import partner_api2_pb2_grpc as api
from partner_api2_pb2 import *

# Load the config
config_path = os.path.normpath(os.path.join(pathlib.Path(__file__).parent.resolve(), 'config.json'))
with open(config_path, 'r') as config_file:
    config = json.load(config_file)

# Establish a connection to the server...
creds = grpc.ssl_channel_credentials()
channel = grpc.secure_channel(f"{config['api_root']}:{config['api_port']}", creds)
# client stub (blocking)
stub = api.PartnerApiStub(channel)

request = AuthenticationRequest()
request.partner_email = config['username']
request.password = config['password']
auth_response = stub.Authenticate(request=request)

auth_token = auth_response.auth_token

# get list of devices managed by partner
inventoryRequest = DeviceInventoryRequest()
inventoryRequest.auth_token = auth_token
inventoryResponse = stub.GetDevices(inventoryRequest)

# Devices include both outlets and vue meters...
devices = inventoryResponse.devices

# Get the list of vue2s
vue2_list = [dev for dev in devices if dev.model == DeviceInventoryResponse.Device.DeviceModel.Vue2 and dev.device_connected]

# Prepare the results
results = {}


def get_heater_energy(vue2: DeviceInventoryResponse.Device.DeviceModel.Vue2):
    deviceUsageRequest = DeviceUsageRequest()
    deviceUsageRequest.auth_token = auth_token

    now = math.ceil(time.time())  # seconds as integer
    deviceUsageRequest.start_epoch_seconds = now - 900  # one fifteen minute period
    deviceUsageRequest.end_epoch_seconds = now
    deviceUsageRequest.scale = DataResolution.FifteenMinutes
    deviceUsageRequest.channels = DeviceUsageRequest.UsageChannel.MAINS
    deviceUsageRequest.manufacturer_device_ids.append(vue2.manufacturer_device_id)

    usage_response = stub.GetUsageData(deviceUsageRequest)

    for device_usage in usage_response.device_usages:
        mains_usage = sum([_.usages[0] for _ in device_usage.channel_usages])
        print(device_usage.bucket_epoch_seconds[0], mains_usage)


def get_energy_summary():
    usage_request = DeviceUsageRequest()
    usage_request.auth_token = auth_token

    now = math.ceil(time.time())  # seconds as integer
    usage_request.start_epoch_seconds = now - 900  # one fifteen minute period
    usage_request.end_epoch_seconds = now
    usage_request.scale = DataResolution.FifteenMinutes
    usage_request.channels = DeviceUsageRequest.UsageChannel.MAINS
    usage_request.manufacturer_device_ids.extend([_.manufacturer_device_id for _ in devices])

    usage_response = stub.GetUsageData(usage_request)

    usages = []
    for device_usage in usage_response.device_usages:
        mains_usage = sum([_.usages[0] for _ in device_usage.channel_usages])
        usages.append(mains_usage)

    print(usages)

if __name__ == "__main__":

    get_energy_summary()
    sys.exit(0)

    # display device information
    print(f'Your partner account has {len(inventoryResponse.devices)} devices associated to it')
    print("*******\n")
    print(f'Your partner account has {len(vue2_list)} Vue2s associated to it')
    if len(vue2_list) > 0:
        vue_pos = 0
        vue2 = vue2_list[vue_pos]
        while not vue2.device_name == 'Vue':
            vue_pos += 1
            vue2 = vue2_list[vue_pos]
        model = vue2.model
        print("Here are the details of the first one")
        print(f'ManufacturerDeviceId: {vue2.manufacturer_device_id}')
        print(f'               Model: {DeviceInventoryResponse.Device.DeviceModel.Name(model)}')
        print(f'                Name: {vue2.device_name}')
        print(f'     DeviceConnected: {vue2.device_connected}')

        print(f'Here are the circuit_infos describing the circuits available on this device:');
        for circuitInfo in vue2.circuit_infos:
            # this print converts to the correct enum value and then concatenates all 5 of these strings onto a single line
            print(f'{circuitInfo.channel_number:2}'
                  f'{DeviceInventoryResponse.Device.CircuitInfo.CircuitType.Name(circuitInfo.type):20}'
                  f'{DeviceInventoryResponse.Device.CircuitInfo.EnergyDirection.Name(circuitInfo.energy_direction):20}'
                  f'{circuitInfo.sub_type:20}'
                  f'{circuitInfo.name:20}')

        # 'Clothes Dryer', 'Cooktop/Range/Oven/Stove', 'Clothes Washer', 'Battery', 'Water Heater', 'Humidifier/Dehumidifier', 'Fridge/Freezer', 'Air Conditioner', 'Boiler', 'Lights', 'Sub Panel', 'Heat Pump', 'Dishwasher', 'Other', 'Microwave', 'Pump', 'Garage/Shop/Barn/Shed', 'Kitchen', 'Solar/Generation', 'Room/Multi-use Circuit', 'Electric Vehicle/RV', 'Hot Tub/Spa', 'Computer/Network', 'Furnace'

        deviceUsageRequest = DeviceUsageRequest()
        deviceUsageRequest.auth_token = auth_token

        now = math.ceil(time.time())  # seconds as integer
        deviceUsageRequest.start_epoch_seconds = now - 3600  # one hour of seconds
        deviceUsageRequest.end_epoch_seconds = now
        deviceUsageRequest.scale = DataResolution.FifteenMinutes
        deviceUsageRequest.channels = DeviceUsageRequest.UsageChannel.MAINS
        deviceUsageRequest.manufacturer_device_ids.append(vue2.manufacturer_device_id)
        print(deviceUsageRequest)
        usageResponse = stub.GetUsageData(deviceUsageRequest)

        for usage in usageResponse.device_usages:
            print("Energy (kWhs) & Power (kWatts) on the 3 mains channels over recent 15 minute buckets:");
            cnt = len(usage.bucket_epoch_seconds)
            for i in range(cnt):
                print(f'{usage.bucket_epoch_seconds[i]}: kWhs / kWatts')
                for j in range(len(usage.channel_usages)):
                    kWhs = usage.channel_usages[j].usages[i];
                    # multiply by 4 to get to power since this is 15min energy; using 2 kWhs of energy in 15 minutes is consuming at a 8 kWatts rate
                    kWatts = kWhs * 4;
                    channel = usage.channel_usages[j].channel
                    print(f'  ({channel}) {kWhs:.2f}/{kWatts:.2f}')
