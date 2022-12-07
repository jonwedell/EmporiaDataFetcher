import math
import time
import sys
import grpc
import partner_api2_pb2_grpc as api
from partner_api2_pb2 import *

if len(sys.argv) != 3:
    print('usage: ' + sys.argv[0] + ' partnerEmail (the email you use to login to the portal at http://partner.emporiaenergy.com) password (that you use for the portal)')
    sys.exit(1)

partnerApiEndpoint = 'partner.emporiaenergy.com:50052'  # this is the V2 of the Partner API

creds = grpc.ssl_channel_credentials()
channel = grpc.secure_channel(partnerApiEndpoint, creds)

# client stub (blocking)
stub = api.PartnerApiStub(channel)

request = AuthenticationRequest()
request.partner_email = sys.argv[1]
request.password = sys.argv[2]
auth_response = stub.Authenticate(request=request)

auth_token = auth_response.auth_token

# get list of devices managed by partner
inventoryRequest = DeviceInventoryRequest()
inventoryRequest.auth_token = auth_token
inventoryResponse = stub.GetDevices(inventoryRequest)

# display device information
print(f'Your partner account has {len(inventoryResponse.devices)} devices associated to it')
print("*******\n")

devices = inventoryResponse.devices

vue2_list = [dev for dev in devices if dev.model == DeviceInventoryResponse.Device.DeviceModel.Vue2]

print(f'Your partner account has {len(vue2_list)} Vue2s associated to it')
if len(vue2_list) > 0:
    vue2 = vue2_list[0]
    model = vue2.model
    print("Here are the details of the first one")
    print(f'ManufacturerDeviceId: {vue2.manufacturer_device_id}')
    print(f'               Model: {DeviceInventoryResponse.Device.DeviceModel.Name(model)}')
    print(f'                Name: {vue2.device_name}')
    print(f'     DeviceConnected: {vue2.device_connected}')

    print(f'Here are the circuit_infos describing the circuits available on this device:' );
    for circuitInfo in vue2.circuit_infos:
        # this print converts to the correct enum value and then concatenates all 5 of these strings onto a single line
        print( f'{circuitInfo.channel_number:2}'
               f'{DeviceInventoryResponse.Device.CircuitInfo.CircuitType.Name(circuitInfo.type):20}' 
               f'{DeviceInventoryResponse.Device.CircuitInfo.EnergyDirection.Name(circuitInfo.energy_direction):20}'
               f'{circuitInfo.sub_type:20}'
               f'{circuitInfo.name:20}' )

    deviceUsageRequest = DeviceUsageRequest()
    deviceUsageRequest.auth_token = auth_token

    now = math.ceil(time.time()) # seconds as integer
    deviceUsageRequest.start_epoch_seconds = now - 3600 # one hour of seconds
    deviceUsageRequest.end_epoch_seconds = now
    deviceUsageRequest.scale = DataResolution.FifteenMinutes
    deviceUsageRequest.channels = DeviceUsageRequest.UsageChannel.MAINS
    deviceUsageRequest.manufacturer_device_ids.append(vue2.manufacturer_device_id)

    usageResponse = stub.GetUsageData(deviceUsageRequest)

    for usage in usageResponse.device_usages:
        print("Energy (kWhs) & Power (kWatts) on the 3 mains channels over recent 15 minute buckets:");
        cnt = len(usage.bucket_epoch_seconds)
        for i in range(cnt):
            print(f'{usage.bucket_epoch_seconds[i]}: kWhs / kWatts')
            for j in range(len(usage.channel_usages)):
                kWhs = usage.channel_usages[j].usages[ i ];
                # multiply by 4 to get to power since this is 15min energy; using 2 kWhs of energy in 15 minutes is consuming at a 8 kWatts rate
                kWatts = kWhs * 4;
                channel  = usage.channel_usages[j].channel
                print( f'  ({channel}) {kWhs:.2f}/{kWatts:.2f}')

outlet_list = [dev for dev in devices if dev.model == DeviceInventoryResponse.Device.DeviceModel.Outlet]
print(f'Your partner account has {len(outlet_list)} Outlets associated to it')
if len(outlet_list) > 0:
    outlet = outlet_list[0]
    listDevicesRequest = ListDevicesRequest()
    listDevicesRequest.auth_token = auth_token
    listDevicesRequest.manufacturer_device_ids.append(outlet.manufacturer_device_id)

    listDevicesResponse = stub.ListOutlets(listDevicesRequest)
    first_outlet = listDevicesResponse.outlets[0]

    model = outlet.model

    print("Here are the details of the first outlet")
    print(f' ManufacturerDeviceId: {outlet.manufacturer_device_id}')
    print(f'                Model: {DeviceInventoryResponse.Device.DeviceModel.Name(model)}')
    print(f'                 Name: {outlet.device_name}')
    print(f'     Device Connected: {outlet.device_connected}')
    print(f'            Outlet On: {first_outlet.on}')

    # toggle outlet state
    first_outlet.on = not first_outlet.on

    updateOutletRequest = UpdateOutletsRequest()
    updateOutletRequest.auth_token = auth_token
    updateOutletRequest.outlets.append(first_outlet)

    updateOutletResponse = stub.UpdateOutlets(updateOutletRequest)

    print( f'updateOutletsResponse indicates the on/off flag is {updateOutletResponse.outlets[0].on}')

    listDevicesRequest = ListDevicesRequest()
    listDevicesRequest.auth_token = auth_token
    listDevicesRequest.manufacturer_device_ids.append(outlet.manufacturer_device_id)

charger_ids = [dev.manufacturer_device_id for dev in devices if dev.model == DeviceInventoryResponse.Device.DeviceModel.EVCharger]
battery_ids = [dev.manufacturer_device_id for dev in devices if dev.model == DeviceInventoryResponse.Device.DeviceModel.Battery]

listDevicesRequest = ListDevicesRequest()
listDevicesRequest.auth_token = auth_token
for id in charger_ids:
    listDevicesRequest.manufacturer_device_ids.append( id)
listDevicesResponse = stub.ListEVChargers(listDevicesRequest)
print( f"Your partner account has {len(listDevicesResponse.evchargers)} EV Chargers associated to it." )


listDevicesRequest = ListDevicesRequest()
listDevicesRequest.auth_token = auth_token
for id in battery_ids:
    listDevicesRequest.manufacturer_device_ids.append(id)
listDevicesResponse = stub.ListBatteries(listDevicesRequest)
print( f"Your partner account has {len(listDevicesResponse.batteries)} Batteries associated to it." )
