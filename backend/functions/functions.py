from ixoncdkingress.cbc.context import CbcContext
from packaging.version import parse as parseVersion
from dateparser.search import search_dates
from datetime import date
import datetime


@CbcContext.expose
def checkUserPermissions(context: CbcContext, **kwargs: dict[str, str]):
    del kwargs
    response = context.api_client.get(
        'RoleList',
        query={'fields': 'name,publicId,permissions'}
    )
    roles = response['data']
    for role in roles:
        if role['permissions'] is not None:
            for permission in role['permissions']:
                if permission['publicId'] in ('COMPANY_ADMIN', 'MANAGE_AGENT'):
                    return (True)
    return (False)


@CbcContext.expose
def getFirmwareVersions(context: CbcContext, **kwargs: dict[str, str]):
    del kwargs
    firmware_list = []
    firmware_list_sorted = []
    firmware_version_list_sorted = []
    firmware_release_dates_checked_per_agent_type = []
    agent_type_names = '"IXrouter2","IXrouter3"'
    response = context.api_client.get(
        'AgentTypeList',
        query={'fields': 'publicId,name',
               'filters': 'in(name,' + agent_type_names + ')'
        }
    )
    agent_types = response['data']
    latest_firmware_found_per_agent_type = []
    today = date.today()
    # Get all firmware versions for agents
    for agent_type in agent_types:
        response = context.api_client.get(
            'AgentTypeFileList',
            url_args={'publicId': agent_type['publicId']},
            query={'fields': 'publicId,name,code,latest,notes'}
        )  # Get all firmware versions for this agent
        ixrouter_firmware_versions = response['data']
        for ixrouter_firmware_version in ixrouter_firmware_versions:
            firmware_list.append({
                'agent_type_name': agent_type['name'],
                'agent_type_publicId': agent_type['publicId'],
                'publicId': ixrouter_firmware_version['publicId'],
                'version': ixrouter_firmware_version['code'],
                'latest':ixrouter_firmware_version['latest'],
                'note': ixrouter_firmware_version['notes']
            })
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
                if firmware['latest'] == False and firmware['agent_type_publicId'] not in latest_firmware_found_per_agent_type:
                    continue
                elif firmware['latest'] == True:
                    latest_firmware_found_per_agent_type.append(firmware['agent_type_publicId'])

                if firmware['agent_type_publicId'] in firmware_release_dates_checked_per_agent_type:
                    firmware_allowed = True
                    days_remaining = ''
                else:
                    firmware_release_date_text = search_dates(firmware['note'], languages=['en'])
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
                firmware_list_sorted.append({
                    'version': firmware['version'],
                    'publicId':firmware['publicId'],
                    'agent_type_publicId':firmware['agent_type_publicId'],
                    'allowed':firmware_allowed,
                    'days_remaining':days_remaining
                })
    return (firmware_list_sorted)


@CbcContext.expose
def selectVersionAndGetRouters(context: CbcContext, firmware, **kwargs: dict[str, str]):
    del kwargs
    agent_list = []
    more_after = None
    all_agents_checked = False
    while all_agents_checked == False:
        response = context.api_client.get(
            'AgentList',
            query={
                'page-size': '1000',
                'page-after': more_after,
                'fields': 'publicId,name,serialNumber,type.name,type.publicId,lastSeenAgentUserAgent.firmwareVersion,mdrServer',
                'filters': ['eq(type.publicId,"' + firmware['agent_type_publicId'] + '")', 'ne(lastSeenAgentUserAgent.firmwareVersion,"' + firmware['version'] + '")', 'isnotnull(mdrServer)']
        })
        agents_list = response['data']
        for agent in agents_list:
            agent_list.append({
                'name': agent['name'],
                'publicId': agent['publicId'],
                'serialNumber': agent['serialNumber'],
                'firmware': agent['lastSeenAgentUserAgent']['firmwareVersion']
            })
        more_after = response['moreAfter']
        if more_after is None:
            all_agents_checked = True
            break
    # List all devices
    agent_list.sort(key=lambda i: i['name'])
    if not agent_list:
        return ([])
    else:
        return (agent_list)


@CbcContext.expose
def startFirmwareUpgrade(context: CbcContext, firmware, agents, **kwargs: dict[str, str]):
    del kwargs
    for agent in agents:
        context.api_client.post(
            'AgentFirmwareUpgrade',
            url_args={'agentId': agent['publicId']},
            data={'file': {'publicId': firmware['publicId']}}
        )
    return True
