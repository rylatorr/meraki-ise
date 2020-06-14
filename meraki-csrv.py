#!/usr/bin/env python3
from sanic import Sanic
from sanic import response
from sanic_httpauth import HTTPBasicAuth
import hashlib
import ssl
import json
import argparse
from sanic.log import logger, logging
import meraki
import meraki.exceptions
import yaml

from group_mapper_csrv import GroupMapper

__author__ = "Ryan LaTorre"
__email__ = "rylatorr@cisco.com"
__copyright__ = "Copyright (c) 2020 Cisco and/or its affiliates"
__license__ = "Cisco Sample Code License"

app = Sanic("meraki-csrv")
auth = HTTPBasicAuth()

# The root logger
#logging.getLogger().setLevel(logging.INFO)
logging.getLogger().setLevel(logging.DEBUG)
# The Meraki logger is very talkative, set it to ERROR only
logging.getLogger('meraki').setLevel(logging.ERROR)
#logger.setLevel(logging.INFO)
logger.setLevel(logging.DEBUG)

class MerakiConfig:
    def __init__(self, config):
        self.api_key = config['meraki_api_key']

def provision_client(network_id: str, mac: str, username: str, mapped_group: str):
    clients = [{'mac': mac, 'name': username}]
    device_policy = 'Group policy'
    dashboard = meraki.DashboardAPI(meraki_config.api_key, output_log=False, print_console=False)
    return dashboard.networks.provisionNetworkClients(network_id,
                                                     clients,
                                                     device_policy,
                                                     groupPolicyId=str(mapped_group))

# used for HTTP auth
def hash_password(salt, password, yaml_config):
    salted = password + salt
    return hashlib.sha512(salted.encode("utf8")).hexdigest()


@auth.verify_password
def verify_password(username, password):
    if username in users:
        return users.get(username) == hash_password(app_salt, password, yaml_config)
    return False

@app.route("/testauth")
@auth.login_required
def testauth(request):
    return response.json({"Hello ": auth.username(request)})


@app.route("/")
async def test(request):
    return response.json({"hello": "world"})

@app.route("/api/user-login", methods=['POST'])
@auth.login_required
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

    yaml_config['networks_file_path'] = networks_file_path

    # Retrieve authorized HTTP users
    app_salt = yaml_config.get('app_salt')
    users = yaml_config.get('http_users')
    for k, v in users.items():
        users[k] = hash_password(app_salt, v, yaml_config)
    logger.debug(f'users dict is {users}')

    if yaml_config['use_ssl']:
        # run on HTTPS
        context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)

        context.load_cert_chain(yaml_config.get('csrv_server_cert', 'config/meraki-csrv.crt'),
                                keyfile=yaml_config.get('csrv_server_key', 'config/meraki-csrv.key'))
        app.go_fast(host="0.0.0.0", port=8443, ssl=context, debug=True)
    else:
        # run on HTTP
        app.run(host="0.0.0.0", port=8080)

