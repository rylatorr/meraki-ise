#!/usr/bin/env python3
from sanic import Sanic
from sanic import response
import json
import argparse
from sanic.log import logger, logging
import meraki
import meraki.exceptions
import yaml

from group_mapper_csrv import GroupMapper

__author__ = "Felix Kaechele, Ryan LaTorre"
__email__ = "fkaechel@cisco.com, rylatorr@cisco.com"
__copyright__ = "Copyright (c) 2020 Cisco and/or its affiliates"
__license__ = "Cisco Sample Code License"

app = Sanic("meraki-csrv")

logging.getLogger().setLevel(logging.INFO)
# The Meraki logger is very talkative, set it to ERROR only
logging.getLogger('meraki').setLevel(logging.ERROR)
logger.setLevel(logging.INFO)

class MerakiConfig:
    def __init__(self, config):
        self.api_key = config['meraki_api_key']

def provision_client(network_id: str, mac: str, username: str, mapped_group: str):
    dashboard = meraki.DashboardAPI(meraki_config.api_key, output_log=False, print_console=False)

    return dashboard.clients.provisionNetworkClients(networkId=network_id,
                                                     mac=mac,
                                                     name=username,
                                                     devicePolicy="Group policy",
                                                     groupPolicyId=str(mapped_group))

@app.route("/")
async def test(request):
    return response.json({"hello": "world"})

@app.route("/api/user-login", methods=['POST'])
async def userLogin(request):
    message = json.loads(request.body)
    logger.debug(f'Message is: {message}')
    if 'macAddress' in message:
        mapper = group_mapper
        mapped_users = mapper.map(message)
        logger.debug(f'mapped_user is {mapped_users}')
        for user in mapped_users:
            try:
                provision_client(*user)
                logging.info(f"Provisioning user {user[2]} with MAC {user[1]} into group {user[3]}")
            except meraki.exceptions.APIError as e:
                logger.error(
                    f"Meraki API error while provisioning client {user[2]} ({user[1]}) into network {user[0]}: {e}")

    return response.json(message, status=200)

if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-c', '--config', help='Path to configuration file')
    arg_parser.add_argument('-n', '--networks', help='Path to network definition CSV file')
    parsed_args = arg_parser.parse_args()

    config_file_path = 'config/config.yaml'
    if parsed_args.config:
        config_file_path = parsed_args.config

    with open(config_file_path, 'r') as config_file:
        yaml_config = yaml.safe_load(config_file)

    networks_file_path = 'config/networks.csv'
    if parsed_args.networks:
        networks_file_path = parsed_args.networks
        yaml_config['networks_file_path'] = networks_file_path

    if 'networks_file_path' not in yaml_config:
        yaml_config['networks_file_path'] = networks_file_path

    meraki_config = MerakiConfig(yaml_config)

    group_mapper = GroupMapper(yaml_config)

    app.run(host="0.0.0.0", port=8080)
