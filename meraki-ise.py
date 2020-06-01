#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import signal
from asyncio.tasks import FIRST_COMPLETED
from csv import DictReader
from ipaddress import ip_address, ip_network
from typing import Optional

import meraki
import meraki.exceptions
import yaml
from websockets import ConnectionClosed

from group_mapper import GroupMapper
from pxgrid import PxgridConfig, PxgridSessionPubsub, PxgridSessionService

__author__ = "Felix Kaechele, Ryan LaTorre"
__email__ = "fkaechel@cisco.com, rylatorr@cisco.com"
__copyright__ = "Copyright (c) 2020 Cisco and/or its affiliates"
__license__ = "Cisco Sample Code License"

session_service = None

logging.getLogger().setLevel(logging.INFO)
#logging.getLogger().setLevel(logging.DEBUG)
# The Meraki logger is very talkative, set it to ERROR only
logging.getLogger('meraki').setLevel(logging.ERROR)
logger = logging.getLogger("meraki_ise")

class MerakiConfig:
    def __init__(self, config):
        self.api_key = config['meraki_api_key']


class ExampleGroupMapper(GroupMapper):
    """
    This is an example implementation of the Group mapper.
    This can be used with profile selectors that are strings such as the 'endpointProfile' from the pxGrid message
    """

    def __init__(self, config: dict, cache_expire: int = 28800):
        super().__init__(config, cache_expire)
        self._profile_key = 'endpointProfile'

    def map_to_networkid(self, ip: str):
        cached_networks = self.redis.get('networks')
        if not cached_networks:
            with open(self.config.get('networks_file_path', 'config/networks.csv'), 'r') as csv_file:
                csv_reader = DictReader(csv_file)
                networks = list(csv_reader)
                self.redis.set('networks', json.dumps(networks), ex=self.cache_expire)
        else:
            networks = json.loads(cached_networks)

        for network in networks:
            if ip_address(ip) in ip_network(network['subnet']):
                return network['Network ID']

        logger.error(f"Unable to map {ip} to an existing Meraki Network")

    def map_to_groupid(self, session: dict) -> Optional[str]:
        profile_map = self.config.get('profile_map')
        if profile_map:
            group = profile_map.get(session[self._profile_key])
            if group:
                return str(group)
        return None


class AuthzProfileMapper(ExampleGroupMapper):
    """
    This is a more specialized implementation that works on the selectedAuthzProfiles element from the pxGrid message
    which is a list of strings and not a simple string.
    """

    def __init__(self, config: dict, cache_expire: int = 28800):
        super().__init__(config, cache_expire)
        self._profile_key = 'selectedAuthzProfiles'

    def map_to_groupid(self, session: dict) -> Optional[str]:
        profile_map = self.config.get('profile_map')
        # make profile name case insensitive
        profile_map = {k.lower(): v for k, v in profile_map.items()}
        #logger.debug(f"profile_map is ({profile_map})")
        if profile_map:
            # 'selectedAuthzProfiles' is a list, so we need to iterate through it
            # Demo code laziness: This will perform provisioning upon first match.
            # So if a user has more than one matching profile only the first one will be
            # used to determine how to provision that user.
            for profile in session[self._profile_key]:
                group = profile_map.get(profile.lower())
                if group:
                    return str(group)
        return None


def provision_client(network_id: str, mac: str, username: str, mapped_group: str):
    clients = [{'mac': mac, 'name': username}]
    device_policy = 'Group policy'
    dashboard = meraki.DashboardAPI(meraki_config.api_key, output_log=False, print_console=False)
    return dashboard.networks.provisionNetworkClients(network_id,
                                                     clients,
                                                     device_policy,
                                                     groupPolicyId=str(mapped_group))


async def future_read_message(pubsub_service, future):
    try:
        message = await pubsub_service.read_message()
        future.set_result(message)
    except ConnectionClosed:
        logging.error('Websocket connection closed')


async def subscribe_loop(pubsub_service: PxgridSessionPubsub, mapper: GroupMapper):
    await pubsub_service.connect()
    while True:
        future = asyncio.Future()
        future_read = future_read_message(pubsub_service, future)
        try:
            await asyncio.wait([future_read], return_when=FIRST_COMPLETED)
        except asyncio.CancelledError:
            await pubsub_service.destroy()
            break
        else:
            message = future.result()
            if 'sessions' in message:
                mapped_users = mapper.map(message)
                for user in mapped_users:
                    try:
                        provision_client(*user)
                        logging.info(f"Provisioning user {user[2]} with MAC {user[1]} into group {user[3]}")
                    except meraki.exceptions.APIError as e:
                        logger.error(
                            f"Meraki API error while provisioning client {user[2]} ({user[1]}) into network {user[0]}: {e}")


if __name__ == '__main__':
    import urllib3

    # Silence urllib3 warnings about ignoring certificate verification
    # Will probably be forgotten to be removed in production anyway,
    # so not bothering with stating that this is dangerous in a production environment.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    pxgrid_config = PxgridConfig(yaml_config)

    session_service = PxgridSessionService(pxgrid_config)
    session_pubsub = PxgridSessionPubsub(session_service)
    #group_mapper = ExampleGroupMapper(yaml_config)
    group_mapper = AuthzProfileMapper(yaml_config)

    loop = asyncio.get_event_loop()
    subscribe_task = asyncio.ensure_future(subscribe_loop(session_pubsub, group_mapper))

    # Setup signal handlers
    loop.add_signal_handler(signal.SIGINT, subscribe_task.cancel)
    loop.add_signal_handler(signal.SIGTERM, subscribe_task.cancel)

    # Event loop
    loop.run_until_complete(subscribe_task)
