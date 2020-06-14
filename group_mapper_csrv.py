import json
from sanic.log import logger, logging
from typing import List, Tuple
from ipaddress import ip_address, ip_network
from csv import DictReader
from typing import Optional
import redis

class GroupMapper:
    def __init__(self, config: dict, cache_expire: int = 28800):
        self.config = config
        self.redis = redis.Redis(host=config.get('redis_host', 'localhost'), port=config.get('redis_port', 6379),
                                 db=config.get('redis_db', 0))
        self.cache_expire = cache_expire
        self._profile_key = 'role'

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
        #logger.debug(f"hit map_to_groupid. roles are . {session[self._profile_key]}")
        # CP send roles as a single string  with multiple comma-separated values. Split into list and trim whitespace
        roleslist = session[self._profile_key].split(',')
        roleslist = [x.strip(' ') for x in roleslist]
        logger.debug(f"roles are {roleslist}")
        profile_map = self.config.get('profile_map')
        # make profile name case insensitive
        profile_map = {k.lower(): v for k, v in profile_map.items()}
        logger.debug(f"profile_map is ({profile_map})")
        if profile_map:
            for profile in roleslist:
                group = profile_map.get(profile.lower())
                if group:
                    return str(group)
        return None

    def map(self, session: dict, name_key: str = 'userName', mac_key: str = 'macAddress', ip_key: str = 'ipAddress') -> List[
        Tuple[str, str, str, str]]:
        """
        Do the mapping.

        :param session: Message from external context server
        :param name_key: Dictionary key for the username field in the message
        :param mac_key: Dictionary key for the MAC address field in the message
        :param group_key: Dictionary key for the group field in the message
        :return: List of tuples of (network_id, mac, name, mapped_group)
        """

        mappings = []

        name = str(session[name_key])
        mac = str(session[mac_key]).upper()
        ip = str(session[ip_key])

        if len(session['ipAddress']) == 0:
            logger.error(f"Client {name} ({mac}) has no IP addresses. Cannot map to network.")
            return []

        # map the network and group IDs
        network_id = self.map_to_networkid(ip)
        logger.debug(f"Client {name} ({mac}) mapped to network {network_id}.")
        logger.debug(f"session is ({session})")
        if self._profile_key in session:
            # Do the heavy lifting
            group_id = self.map_to_groupid(session)
            result = (network_id, mac, name, group_id)
            result_json_obj = json.dumps({'network_id': network_id, 'mac': mac, 'ip': ip, 'name': name, 'group': group_id})
        else:
            logger.error(f"Client {name} ({mac}) has no {self._profile_key} set. Cannot map to group.")

        cached_mapping = self.redis.get(f"client.{mac.replace(':', '')}")

        if cached_mapping:
            # We found a cached mapping. Nice.
            #need to check the string. if everything is the same, do nothing. But if any element is different do the other code
            #logger.debug(f"result_json_obj var is ({result_json_obj})")
            #logger.debug(f"cached_mapping var is ({cached_mapping})")
            if cached_mapping.decode() == result_json_obj:
                logger.debug(f"Found a cached identical mapping for client {name} ({mac})")
            else:
                logger.debug(f"Found a cached but different mapping for client {name} ({mac})")
                # so let's update it then
                json_obj = json.dumps({'network_id': network_id, 'mac': mac, 'ip': ip, 'name': name, 'group': group_id})
                self.redis.set(f"client.{mac.replace(':', '')}", json_obj, ex=self.cache_expire)
                mappings.append(result)
        else:
            json_obj = json.dumps({'network_id': network_id, 'mac': mac, 'ip': ip, 'name': name, 'group': group_id})
            self.redis.set(f"client.{mac.replace(':', '')}", json_obj, ex=self.cache_expire)
            mappings.append(result)

        # If the message did not contain session information this will return an empty list
        return mappings
