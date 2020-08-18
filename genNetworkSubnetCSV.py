import csv
from datetime import datetime
import os
from ipaddress import ip_network, ip_address
import meraki
import argparse
import yaml

subnetMapList = []

class MerakiConfig:
    def __init__(self, config):
        self.api_key = config['meraki_api_key']
        self.org_name = config['meraki_org_name']

def getNetworkId(ipaddr):
    for x in subnetMapList:
        if ip_address(ipaddr) in ip_network(x['subnet']):
            print(f'\n{ipaddr} is in {x["networkId"]}')
            return x["networkId"]

def main():
    # Instantiate a Meraki dashboard API session
    dashboard = meraki.DashboardAPI(
        api_key=meraki_config.api_key,
        output_log=False
        #log_file_prefix=os.path.basename(__file__)[:-3],
        #log_path='',
        #print_console=False
    )

    # Get list of organizations to which API key has access
    # ORG_NAME = 'rylatorr'
    # ORG_NAME = 'Canadian Customer Corp'
    ORG_NAME = meraki_config.org_name
    organizations = dashboard.organizations.getOrganizations()

    # Iterate through list of orgs to get the one I want
    for org in organizations:
        org_index = next((index for (index, d) in enumerate(organizations) if d['name'] == ORG_NAME), None)
        org_id = organizations[org_index]['id']

    #print('org ID is ' + org_id)
    #org_id = org['id']

    # Get list of devices in organization
    try:
        devices = dashboard.organizations.getOrganizationDevices(org_id)
    except meraki.APIError as e:
        print(f'Meraki API error: {e}')
    except Exception as e:
        print(f'some other error: {e}')

    # Set up output CSV
    output_file = open(networks_file_path, mode='w', newline='\n')
    field_names = ['Network ID', 'VLID', 'VLAN Name', 'subnet']
    csv_writer = csv.DictWriter(output_file, field_names, delimiter=',', quotechar='"',
                                quoting=csv.QUOTE_ALL)
    csv_writer.writeheader()

    # Iterate through devices
    total = len(devices)
    counter = 1
    print(f'  - iterating through {total} devices in organization {org_id}')
    for device in devices:
        print(f'Checking if {device["name"]} is an MX ({counter} of {total})')
        # If the device is an MX, try getting the VLANs
        if device['model'][:2] in ('MX', 'Z1', 'Z3') and device['networkId'] is not None:
            # Get network VLANs
            try:
                networkVLANs = dashboard.appliance.getNetworkApplianceVlans(device["networkId"])
            except meraki.APIError as e:
                print(f'Meraki API error: {e}')
            except Exception as e:
                print(f'some other error: {e}')
            else:
                # Write rows
                for vlan in networkVLANs:
                    # Add to the master list
                    subnetMapList.append({'subnet':vlan["subnet"], 'networkId': vlan["networkId"]})
                    csv_writer.writerow({'Network ID': vlan["networkId"], 'VLID': vlan["id"], 'VLAN Name': vlan["name"], 'subnet': vlan["subnet"]})
        counter += 1
    output_file.close()

if __name__ == '__main__':
    start_time = datetime.now()

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-c', '--config', help='Path to configuration file')
    arg_parser.add_argument('-n', '--networks', help='Path to network definition CSV file')
    parsed_args = arg_parser.parse_args()

    config_file_path = 'config/config.yaml'
    if parsed_args.config:
        config_file_path = parsed_args.config

    networks_file_path = 'config/networks.csv'
    if parsed_args.config:
        networks_file_path = parsed_args.config

    with open(config_file_path, 'r') as config_file:
        yaml_config = yaml.safe_load(config_file)

    meraki_config = MerakiConfig(yaml_config)

    main()
    end_time = datetime.now()
    print(f'\nScript complete, total runtime {end_time - start_time}')
