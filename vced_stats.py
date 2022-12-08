#!/usr/bin/env python3
import json
import math
import os
import pathlib
import sys
import time
from contextlib import closing
from typing import List

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

# Get the list of active vue2 devices
devices = [dev for dev in inventoryResponse.devices if dev.model == DeviceInventoryResponse.Device.DeviceModel.Vue2]


def write_to_db():
    with closing(mysql.connector.connect(**config['db'])) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute('INSERT INTO xyz (x, y, z) VALUES (?,?,?)',
                        [0, 0, 0])
            result = cur.fetchall()


def usage_request(vue2: DeviceInventoryResponse.Device.DeviceModel.Vue2, now: int) -> List[dict]:
    """ Creates and executes a usage request getting details for a particular
    device. Returns usage for all circuits as a list of dictionaries, with
     the circuit info combined with usage. (Why didn't they design the API this
     way?) """

    usage_request = DeviceUsageRequest()
    usage_request.auth_token = auth_token
    usage_request.start_epoch_seconds = now - 900  # one fifteen minute period
    usage_request.end_epoch_seconds = now
    usage_request.scale = DataResolution.FifteenMinutes
    usage_request.channels = DeviceUsageRequest.UsageChannel.ALL
    usage_request.manufacturer_device_ids.append(vue2.manufacturer_device_id)

    usage_response = stub.GetUsageData(usage_request)

    response = []
    for circuit in vue2.circuit_infos:
        circuit_data = {'channel_number': circuit.channel_number,
                        'direction': circuit.energy_direction}
        if circuit.channel_number < 4:
            circuit_data['type'] = 'Mains'
        else:
            circuit_data['type'] = circuit.sub_type
        for channel in usage_response.device_usages[0].channel_usages:
            if channel.channel == circuit.channel_number:
                circuit_data['usage'] = channel.usages[0]
        # Only return circuits with usage
        if 'usage' in circuit_data:
            response.append(circuit_data)

    return response


# (Currently known) Circuit types
def get_usage_by_circuit_type(usage_data: List[dict], circuit_type: str):
    """
    Currently known circuit types:
    'Clothes Dryer', 'Cooktop/Range/Oven/Stove', 'Clothes Washer', 'Battery',
    'Water Heater', 'Humidifier/Dehumidifier', 'Fridge/Freezer','Air Conditioner',
    'Boiler', 'Lights', 'Sub Panel', 'Heat Pump', 'Dishwasher', 'Other', 'Microwave',
    'Pump', 'Garage/Shop/Barn/Shed', 'Kitchen', 'Solar/Generation', 'Room/Multi-use Circuit',
    'Electric Vehicle/RV', 'Hot Tub/Spa', 'Computer/Network', 'Furnace'
    """
    total_usage = 0
    found_circuits = 0

    for device in usage_data:
        for circuit in device:
            if circuit['type'] == circuit_type:
                total_usage += circuit['usage']
                found_circuits += 1
    return total_usage, found_circuits


def get_detailed_energy_details():

    now = math.ceil(time.time())

    print(usage_request(devices[0], now))

    #all_usages = [usage_request(device, now) for device in devices[:5]]
    pass


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


if __name__ == "__main__":

    #get_detailed_energy_details()
    get_energy_summary()
    sys.exit(0)
