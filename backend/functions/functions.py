from ixoncdkingress.cbc.context import CbcContext
from packaging.version import parse as parseVersion
from dateparser.search import search_dates
from datetime import date
import datetime


@CbcContext.expose
def getFirmwareVersions(context: CbcContext, **kwargs: dict[str, str]):
    del kwargs # Removes non-defined key word arguments
    firmware_list = []
    firmware_list_sorted = []
    firmware_version_list_sorted = []
    firmware_release_dates_checked_per_agent_type = []
    response = context.api_client.get('AgentTypeList', query={'fields': 'publicId,name'})
    agent_types = response['data']
    agent_type_names = ['IXrouter2', 'IXrouter3']
    latest_firmware_found_per_agent_type = []
    today = date.today()
    for agent in agent_type_names:  # Get all firmware versions for agents
        # Find publicId for specific agent type name
        ixrouter = next(
            (item for item in agent_types if item['name'] == agent), None)
        ixrouter_pubid = ixrouter['publicId']
        response = context.api_client.get('AgentTypeFileList', url_args={'publicId': ixrouter_pubid}, query={'fields': 'publicId,name,code,latest,notes'})  # Get all firmware versions for this agent
        ixrouter_firmware_versions = response['data']
        for ixrouter_firmware_version in ixrouter_firmware_versions:
            firmware_list.append({'agent_type_name': agent, 'agent_type_publicId': ixrouter_pubid,'publicId': ixrouter_firmware_version['publicId'],'version': ixrouter_firmware_version['code'],'latest':ixrouter_firmware_version['latest'],'note': ixrouter_firmware_version['notes']})
    for firmware in firmware_list:  # Make a list of version numbers only to enable natural sorting
        firmware_version_list_sorted.append(firmware['version'])
    # Sort version numbers naturally
    firmware_version_list_sorted.sort(key=parseVersion, reverse=True)
    # Create a sorted list of dictionaries of each version
    for firmware_version in firmware_version_list_sorted:
        # Find this firmware version's publicId and agent type publicId
        for firmware in firmware_list:
            if firmware['version'] == firmware_version:
                # Skip version if it isn't latest of this agent type
                if firmware['latest'] == False and not firmware['agent_type_publicId'] in latest_firmware_found_per_agent_type:
                    continue
                elif firmware['latest'] == True:
                    latest_firmware_found_per_agent_type.append(firmware['agent_type_publicId'])

                if firmware['agent_type_publicId'] in firmware_release_dates_checked_per_agent_type:
                    firmware_allowed = True
                    days_remaining = ''
                else:
                    firmware_release_date_text = search_dates(firmware['note'],languages=['en'])
                    firmware_release_date_string = str(firmware_release_date_text[0][1])
                    firmware_release_date = datetime.datetime.strptime(firmware_release_date_string, '%Y-%m-%d %H:%M:%S').date()
                    date_delta = today - firmware_release_date
                    days = int(date_delta.days)
                    if days < 14:
                        firmware_allowed = False
                        days_remaining = 14 - days
                    else:
                        firmware_allowed = True
                        days_remaining = ''
                        firmware_release_dates_checked_per_agent_type.append(firmware['agent_type_publicId'])
                firmware_list_sorted.append({'version': firmware['version'],'publicId':firmware['publicId'],'agent_type_publicId':firmware['agent_type_publicId'],'allowed':firmware_allowed,'days_remaining':days_remaining})
    return (firmware_list_sorted)


@CbcContext.expose
def selectVersionAndGetRouters(context: CbcContext, firmware, **kwargs: dict[str, str]):
    del kwargs # Removes non-defined key word arguments
    agent_list = []
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
        return ([])
    else:
        return (agent_list)


@CbcContext.expose
def startFirmwareUpgrade(context: CbcContext, firmware, agents, **kwargs: dict[str, str]):
    del kwargs # Removes non-defined key word arguments
    # Upgrade all to latest version
    for agent in agents:
        response = context.api_client.post('AgentFirmwareUpgrade', url_args={'agentId': agent['publicId']}, data={'file': {'publicId': firmware['publicId']}})
    return True
