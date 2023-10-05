from ixoncdkingress.cbc.context import CbcContext
from packaging.version import parse as parseVersion


@CbcContext.expose
# **kwargs, key word arguments die niet defined is
def getFirmwareVersions(context: CbcContext, **kwargs: dict[str, str]):
    del kwargs
    # Get all firmware versions
    global firmware_list
    firmware_list = []
    firmware_version_list = []
    response = context.api_client.get('AgentTypeList', query={'fields': 'publicId,name'})
    agent_types = response['data']
    agents = ['IXrouter2', 'IXrouter3']
    for agent in agents:  # Get all firmware versions for agents
        # Find publicId for specific agent type name
        ixrouter = next(
            (item for item in agent_types if item['name'] == agent), None)
        ixrouter_pubid = ixrouter['publicId']
        response = context.api_client.get('AgentTypeFileList', url_args={'publicId': ixrouter_pubid}, query={'fields': 'publicId,name,code,latest,notes'})  # Get all firmware versions for this agent
        ixrouter_firmware_versions = response['data']
        for ixrouter_firmware_version in ixrouter_firmware_versions:
            firmware_list.append({'agent_type_name': agent, 'agent_type_publicId': ixrouter_pubid,'publicId': ixrouter_firmware_version['publicId'], 'version': ixrouter_firmware_version['code'], 'note': ixrouter_firmware_version['notes']})
    for firmware in firmware_list:  # Make a list of version numbers only
        firmware_version_list.append(firmware['version'])
    # Sort version numbers naturally
    firmware_version_list.sort(key=parseVersion, reverse=True)
    return (firmware_version_list)


@CbcContext.expose
# **kwargs, key word arguments die niet defined is
def selectVersionAndGetRouters(context: CbcContext, version, **kwargs: dict[str, str]):
    del kwargs
    # if firmware_list == []: # If firmware_list is empty for whatever reason, repeat the above function
    #   getFirmwareVersions(context)
    # Find publicId for selected firmware
    firmware = next(
        (item for item in firmware_list if item['version'] == version), None)
    # Get a list of agents that have an active MQTT connection and are not running the latest firmware version\
    global agent_list
    global target_firmware_version
    global target_firmware_publicid
    agent_list = []
    target_firmware_version = firmware['version']
    target_firmware_publicid = firmware['publicId']
    more_after = None
    all_agents_checked = False
    while all_agents_checked == False:
        response = context.api_client.get('AgentList', query={'page-size': '1000', 'page-after': more_after, 'fields': 'publicId,name,deviceId,type.name,type.publicId,lastSeenAgentUserAgent.firmwareVersion,mdrServer'})
        agents_list = response['data']
        for agent in agents_list:
            # Check if agent is correct agent type (e.g. IXrouter3), based on selected firmware version
            if agent['type']['publicId'] == firmware['agent_type_publicId']:
                # Check if agent is not already running selected firmware version
                if agent['lastSeenAgentUserAgent']['firmwareVersion'] != firmware['version']:
                    # Check if IXrouter has an active MQTT connection
                    if agent['mdrServer'] is not None:
                        agent_list.append({'name': agent['name'], 'publicId': agent['publicId'], 'firmware': agent['lastSeenAgentUserAgent']['firmwareVersion']})
        more_after = response['moreAfter']
        if more_after is None:  # All agents checked
            all_agents_checked = True
            break  # Redundant

    # List all devices
    agent_list.sort(key=lambda i: i['name'])
    if not agent_list:
        print('No IXrouters online for a firmware upgrade')
        return ([])
    else:
        print('IXrouters that are online for a firmware upgrade')
        for agent in agent_list:
            print('- {} ({}) ({})'.format(agent['name'], agent['publicId'], agent['firmware']))
    return (agent_list)


@CbcContext.expose
# **kwargs, key word arguments die niet defined is
def installFirmware(context: CbcContext, **kwargs: dict[str, str]):
    del kwargs
    # Upgrade all to latest version
    for agent in agent_list:
        print('{} {} ({})'.format('Upgrading',
              agent['name'], agent['publicId']))
        response = context.api_client.post('AgentFirmwareUpgrade', url_args={'agentId': agent['publicId']}, data={'file': {'publicId': target_firmware_publicid}})
        # if response['status'] == 'error':
        #     response_message = ''.join(response['data'][0]['message'])
        #     print('{} {}'.format('Failed to start upgrade:', response_message))
        # else:
        #     print('{} {} {} {}'.format('Successfully started upgrade from',agent['firmware'], 'to', target_firmware_version))
    print('Upgrades ALL started')
    return True
