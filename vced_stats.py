#!/usr/bin/env python3

import json
import math
import os
import pathlib
import sys
import time
from contextlib import closing

import grpc

import mysql.connector


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


def write_to_db():
    with closing(mysql.connector.connect(**config['db'])) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute('INSERT INTO xyz (x, y, z) VALUES (?,?,?)',
                        [0, 0, 0])
            result = cur.fetchall()


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
    usage_request.channels = DeviceUsageRequest.UsageChannel.MAINS # Change to ALL when getting individual circuits
    usage_request.manufacturer_device_ids.extend([_.manufacturer_device_id for _ in devices])

    usage_response = stub.GetUsageData(usage_request)

    usages = []
    timestamp = None
    for device_usage in usage_response.device_usages:
        mains_usage = sum([_.usages[0] for _ in device_usage.channel_usages])
        usages.append(mains_usage)

        # Determine what period this data is for
        if device_usage.bucket_epoch_seconds[0] != timestamp:
            if timestamp is not None:
                print('Mismatched data...', timestamp, device_usage.bucket_epoch_seconds[0])
            timestamp = device_usage.bucket_epoch_seconds[0]

    print(timestamp, sum(usages), len(usages))

    #
    #
    # print(f'Here are the circuit_infos describing the circuits available on this device:');
    # for circuitInfo in vue2.circuit_infos:
    #     # this print converts to the correct enum value and then concatenates all 5 of these strings onto a single line
    #     print(f'{circuitInfo.channel_number:2}'
    #           f'{DeviceInventoryResponse.Device.CircuitInfo.CircuitType.Name(circuitInfo.type):20}'
    #           f'{DeviceInventoryResponse.Device.CircuitInfo.EnergyDirection.Name(circuitInfo.energy_direction):20}'
    #           f'{circuitInfo.sub_type:20}'
    #           f'{circuitInfo.name:20}')


if __name__ == "__main__":

    get_energy_summary()
    sys.exit(0)
