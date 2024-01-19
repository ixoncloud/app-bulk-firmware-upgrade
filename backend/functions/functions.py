from ixoncdkingress.function.context import FunctionContext
from packaging.version import parse as parseVersion
from dateparser.search import search_dates
from datetime import date
import datetime


@FunctionContext.expose
def checkUserPermissions(context: FunctionContext, **kwargs: dict[str, str]):
    del kwargs

    # Get all roles
    role_list = []
    role_with_permission_list = {}
    more_after = None
    all_roles_checked = False
    while all_roles_checked == False:
        response = context.api_client.get(
            'RoleList',
            query={
                'page-size': '1000',
                'page-after': more_after,
                'fields': 'name,publicId,permissions'
            }
        )
        role_list = role_list + response['data']
        more_after = response['moreAfter']
        if more_after is None:
            all_roles_checked = True
            break
    sufficient_permissions = False
    for role in role_list:
        if role['permissions'] is not None:
            company_wide_role = False
            manage_agents_role = False
            company_wide_manage_agents = False
            for permission in role['permissions']:
                # Role is company admin
                if permission['publicId'] == 'COMPANY_ADMIN':
                    company_wide_role = True
                    manage_agents_role = True
                    sufficient_permissions = True
                    break
                # Role is company-wide
                if permission['publicId'] == 'COMPANY_WIDE_ROLE':
                    company_wide_role = True
                    continue
                # Role provides "manage agents" permission
                if permission['publicId'] == 'MANAGE_AGENT':
                    manage_agents_role = True
                    sufficient_permissions = True
                    role_with_permission_list[role['publicId']] = role
                    continue
            # Company wide role providing manage devices
            if company_wide_role and manage_agents_role:
                company_wide_manage_agents = True
                break
    
    # No role found with manage agents, insufficient permissions
    if sufficient_permissions == False:
        return([])

    # Get all agents
    agent_list = []
    more_after = None
    all_agents_checked = False
    while all_agents_checked == False:
        response = context.api_client.get(
            'AgentList',
            query={
                'page-size': '1000',
                'page-after': more_after,
                'fields': 'publicId,name,serialNumber,type.name,type.publicId,lastSeenAgentUserAgent.firmwareVersion,mdrServer,memberships.group.publicId',
                'filters': ['isnotnull(mdrServer)']
        })
        agent_list = agent_list + response['data']
        more_after = response['moreAfter']
        if more_after is None:
            all_agents_checked = True
            break
    
    # Company-wide role with manage permissions, no need to continue permission checks or filtering
    if company_wide_manage_agents == True:
        agent_list.sort(key=lambda i: i['name'])
        return(agent_list)

    # Get all device-specific groups
    group_list = []
    dev_spec_group_list = {}
    more_after = None
    all_groups_checked = False
    while all_groups_checked == False:
        response = context.api_client.get(
            'GroupList',
            query={
                'page-size': '1000',
                'page-after': more_after,
                'fields': 'name,publicId,agent.publicId'
            }
        )
        group_list = group_list + response['data']
        more_after = response['moreAfter']
        if more_after is None:
            all_groups_checked = True
            break
    for group in group_list:
        # Check if device-specific group
        if group['agent'] is not None:
            dev_spec_group_list[group['publicId']] = group['agent']['publicId']

    # Get user permissions
    response = context.api_client.get(
        'MyUser',
        query={'fields': 'name,publicId'}
    )
    selfPublicId = response['data']['publicId']
    response = context.api_client.get(
        'User',
        url_args={'publicId': selfPublicId},
        query={'fields': 'name,memberships.group.publicId,memberships.role.publicId'}
    )
    memberships = response['data']['memberships']

    # Check per membership
    agent_list_filtered = []
    for membership in memberships:
        if membership['role'] is not None:
            if membership['role']['publicId'] in role_with_permission_list:
                # Device specific membership
                if membership['group']['publicId'] in dev_spec_group_list:
                    # Find agent
                    for agent in agent_list:
                        if agent['publicId'] == dev_spec_group_list[membership['group']['publicId']]:
                            agent_list_filtered.append(agent)
                            agent_list.remove(agent)
                            break
                # Group specific membership
                else:
                    # Find agents in group
                    for agent in agent_list:
                        for agent_membership in agent['memberships']:
                            if agent_membership['group']['publicId'] == membership['group']['publicId']:
                                agent_list_filtered.append(agent)
                                agent_list.remove(agent)
                                break
    
    return(agent_list_filtered)


@FunctionContext.expose
def getFirmwareVersions(context: FunctionContext, **kwargs: dict[str, str]):
    del kwargs
    firmware_list = []
    firmware_list_sorted = []
    firmware_version_list_sorted = []
    firmware_release_dates_checked_per_agent_type = []
    agent_type_names = '"IXrouter2","IXrouter3"'
    agent_types = []
    more_after = None
    all_agent_types_checked = False
    while all_agent_types_checked == False:
        response = context.api_client.get(
            'AgentTypeList',
            query={
                'page-size': '1000',
                'page-after': more_after,
                'fields': 'publicId,name',
                'filters': 'in(name,' + agent_type_names + ')'
            }
        )
        agent_types = agent_types + response['data']
        more_after = response['moreAfter']
        if more_after is None:
            all_agent_types_checked = True
            break
    latest_firmware_found_per_agent_type = []
    today = date.today()
    # Get all firmware versions for agents
    for agent_type in agent_types:
        response = context.api_client.get(
            'AgentTypeFileList',
            url_args={'publicId': agent_type['publicId']},
            query={
                'page-size': '1000',
                'fields': 'publicId,name,code,latest,notes'
            }
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
    return(firmware_list_sorted)


@FunctionContext.expose
def startFirmwareInstallation(context: FunctionContext, firmware, agents, **kwargs: dict[str, str]):
    del kwargs
    for agent in agents:
        context.api_client.post(
            'AgentFirmwareUpgrade',
            url_args={'agentId': agent['publicId']},
            data={'file': {'publicId': firmware['publicId']}}
        )
    return(True)
