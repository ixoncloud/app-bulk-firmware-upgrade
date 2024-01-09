<script lang="ts">
  import { onMount } from "svelte";

  export let context;

  let client;
  let response;
  let url;
  let authToken;
  $: activeWebsocketConn = undefined;
  let activeWebsocket;
  let timerWebsocketRenewal;

  let state: number;
  let passedPermissionsCheck = undefined;
  let searchingFirmware = true;
  let searchingAgents = false;
  let upgradingAgents = false;

  let selectFirmwareButtonText = "";
  let selectFirmwareButtonTextLong = "";
  let selectFirmwareButtonTextShort = "";
  let selectedFirmware;
  let firmwareList = [];
  let eligibleAgents = [];
  let disableFirmwareSelect = false;

  let startUpgradeButtonText = "";
  let startUpgradeButtonTextLong = "";
  let startUpgradeButtonTextShort = "";
  let startUpgradeButtonStyle = "";
  let upgradeStatusText = "";
  let upgradeStatusTextLong = "";
  let upgradeStatusTextShort = "";
  const upgradeBatchSize = 5;
  let eligibleAgentsBatch = [];
  let disableStartUpgrade = true;

  let tableAgentsStatus: number;
  let tableAgents = [];

  let showUpgradingAgentsStatus = false;
  let informUpgradeStatusTitleText = "";
  let informUpgradeStatusMessageText = "";
  let upgradeStatusTitleStyling = "";
  let spinnerRowStyling = "";
  let agentsStatusStarted = [];
  let agentsStatusCompleted = [];
  let agentsStatusFailed = [];
  let startedStatusStyling = "statusSelected";
  let completedStatusStyling = "statusNotSelected";
  let failedStatusStyling = "statusNotSelected";

  let rootEl: HTMLElement;
  let width: number | null = null;
  $: isNarrow = width !== null ? width <= 580 : false;

  enum TableAgentsStatus {
    Started = 1,
    Completed = 2,
    Failed = 3,
  }

  enum State {
    SearchingFirmware = 1,
    WaitingFirmwareSelect = 2,
    SearchingDevices = 3,
    NoDevicesFound = 4,
    DevicesFound = 5,
    StartInstall = 6,
    InstallingFirmware = 7,
    InstalledFirmware = 8,
    NoWebsocketStartingInstall = 9,
    NoWebsocketStartedInstall = 10,
    NotAllowed = 99,
  }

  onMount(async () => {
    state = State.SearchingFirmware; // Waiting for firmware selection
    disableFirmwareSelect = true;
    searchingFirmware = true; // Show spinner
    width = rootEl.getBoundingClientRect().width;
    const resizeObserver = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        width = entry.contentRect.width;
      });
    });
    resizeObserver.observe(rootEl);

    client = context.createBackendComponentClient();
    response = await client.call("functions.checkUserPermissions");
    passedPermissionsCheck = response.data;

    if (passedPermissionsCheck) {
      response = await client.call("functions.getFirmwareVersions");
      firmwareList = response.data;
      disableFirmwareSelect = false;
    }
    searchingFirmware = false; // Hide spinner
    state = State.WaitingFirmwareSelect; // Waiting for firmware selection

    return () => {
      resizeObserver.unobserve(rootEl);
      client.destroy();
    };
  });

  async function selectVersionAndGetRouters(): Promise<void> {
    state = State.SearchingDevices; // Firmware selected, searching devices
    upgradingAgents = false;
    eligibleAgents = [];
    agentsStatusStarted = [];
    agentsStatusCompleted = [];
    agentsStatusFailed = [];
    disableStartUpgrade = true;
    searchingAgents = true; // Show spinner
    if (activeWebsocketConn) {
      activeWebsocketConn.close();
    }
    activeWebsocket = undefined;
    response = await client.call("functions.selectVersionAndGetRouters", {
      firmware: selectedFirmware,
    });
    eligibleAgents = response.data;
    searchingAgents = false; // Hide spinner
    if (eligibleAgents.length === 0) {
      state = State.NoDevicesFound; // No devices found
      disableStartUpgrade = true;
    } else {
      state = State.DevicesFound; // Devices found, waiting for upgrade start
      disableStartUpgrade = false;
    }
    tableAgents = eligibleAgents;
  }

  function informFirmwareNotAvailable(
    selectedUnavailableFirmware,
    availableInDays,
  ): void {
    state = State.WaitingFirmwareSelect;
    disableStartUpgrade = true;
    selectedFirmware = "";
    context.openAlertDialog({
      title: "Available soon",
      message:
        "Firmware versions become available for Bulk Firmware Upgrade 2 weeks after they are released. Firmware " +
        selectedUnavailableFirmware +
        " becomes available in " +
        availableInDays +
        " day(s).",
      buttonText: "I understand",
    });
  }

  async function startFirmwareUpgrade(): Promise<void> {
    state = State.StartInstall;
    establishWebsocketConn();
    disableFirmwareSelect = true;
    disableStartUpgrade = true;
    upgradingAgents = true;
    changeTableAgents(TableAgentsStatus.Started);
    agentsStatusStarted = [];
    for (let i = 0; i < eligibleAgents.length; i += upgradeBatchSize) {
      eligibleAgentsBatch = eligibleAgents.slice(i, i + upgradeBatchSize);
      await client.call("functions.startFirmwareUpgrade", {
        firmware: selectedFirmware,
        agents: eligibleAgentsBatch,
      });
      agentsStatusStarted = agentsStatusStarted.concat(eligibleAgentsBatch);
    }
  }

  async function establishWebsocketConn(): Promise<void> {
    url = context.getApiUrl("AuthTokenChangeNotificationsList");
    response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + context.appData.accessToken.secretId,
        "Api-Application": context.appData.apiAppId,
        "Api-Company": context.appData.company.publicId,
        "Api-Version": "2",
      },
      body: JSON.stringify({ expiresIn: 3600 }),
      method: "POST",
    })
      .then((res) => res.json())
      .catch((error) => {
        console.error("Error:", error);
      });
    authToken = response.data.secretId;

    url = context.getApiUrl("ChangeNotificationWebSocket");
    if (activeWebsocketConn) {
      activeWebsocketConn.close();
    }
    activeWebsocketConn = new WebSocket(url, "change-notifications");

    activeWebsocketConn.onerror = (event) => {
      activeWebsocket = false;
      state = State.NoWebsocketStartingInstall;
    };

    activeWebsocketConn.onopen = (event) => {
      activeWebsocket = true;
      state = State.InstallingFirmware;
      activeWebsocketConn.send('{"aut":"' + authToken + '"}');
      activeWebsocketConn.send(
        '{"sub":["Company/' + context.appData.company.publicId + '"]}',
      );
      timerWebsocketRenewal = setTimeout(establishWebsocketConn, 3_300_000); // 5 min before WS expires
    };

    activeWebsocketConn.onmessage = (event) => {
      let eventData = JSON.parse(event.data);
      // If-statement returns true if eventData.dat exists and both mqttChangedOn and mdrServer are not null, so MQTT connected
      if (eventData?.dat?.mqttChangedOn && eventData.dat.mdrServer) {
        eventData.sel.forEach(async (agent) => {
          let agentPubId = agent.pat.slice(1);
          url = context.getApiUrl("Agent", {
            publicId: agentPubId,
            fields: "name,publicId,lastSeenAgentUserAgent.firmwareVersion",
          });
          response = await fetch(url, {
            headers: {
              "Content-Type": "application/json",
              Authorization: "Bearer " + context.appData.accessToken.secretId,
              "Api-Application": context.appData.apiAppId,
              "Api-Company": context.appData.company.publicId,
              "Api-Version": "2",
            },
            method: "GET",
          })
            .then((res) => res.json())
            .catch((error) => {
              console.error("Error:", error);
            });

          // New firmware is
          let agentFirmwareNew =
            response.data.lastSeenAgentUserAgent.firmwareVersion;

          // Find old firmware
          let indexInAgentsStatusStarted = agentsStatusStarted.findIndex(
            (agent) => agent.publicId == agentPubId,
          );
          let agentDetails = agentsStatusStarted[indexInAgentsStatusStarted];
          let agentFirmwareOld = agentDetails.firmware;

          if (agentFirmwareNew != agentFirmwareOld) {
            // firmware upgrade succeeded
            let found = agentsStatusCompleted.find(
              (agent) => agent.publicId == agentPubId,
            );
            if (!found) {
              agentsStatusCompleted =
                agentsStatusCompleted.concat(agentDetails);
            }

            let agentInAgentsStatusStarted = agentsStatusStarted.find(
              (agent) => agent.publicId == agentPubId,
            );
            if (agentInAgentsStatusStarted) {
              agentsStatusStarted = agentsStatusStarted.filter(
                (m) => m !== agentInAgentsStatusStarted,
              );
              if (agentsStatusStarted.length == 0) {
                upgradingAgents = false;
                disableFirmwareSelect = false;
                state = State.InstalledFirmware;

                if (agentsStatusCompleted.length != 0) {
                  changeTableAgents(TableAgentsStatus.Completed);
                } else {
                  changeTableAgents(TableAgentsStatus.Failed);
                }
                clearTimeout(timerWebsocketRenewal);
                activeWebsocketConn.close();
              }
            }
          } else {
            // firmware upgrade failed
            let found = agentsStatusFailed.find(
              (agent) => agent.publicId == agentPubId,
            );
            if (!found) {
              agentsStatusFailed = agentsStatusFailed.concat(agentDetails);
            }

            let agentInAgentsStatusStarted = agentsStatusStarted.find(
              (agent) => agent.publicId == agentPubId,
            );
            if (agentInAgentsStatusStarted) {
              agentsStatusStarted = agentsStatusStarted.filter(
                (m) => m !== agentInAgentsStatusStarted,
              );
              if (agentsStatusStarted.length == 0) {
                upgradingAgents = false;
                disableFirmwareSelect = false;
                state = State.InstalledFirmware;

                if (agentsStatusCompleted.length != 0) {
                  changeTableAgents(TableAgentsStatus.Completed);
                } else {
                  changeTableAgents(TableAgentsStatus.Failed);
                }
                clearTimeout(timerWebsocketRenewal);
                activeWebsocketConn.close();
              }
            }
          }
        });
      }
    };
  }

  const textTimeIndication =
    "After an upgrade has started, it usually takes 2 to 5 minutes for the upgrade to complete. Do not turn off or unplug the device during this period.\n\n";
  const textWebsocketError =
    "Upgrade progression cannot be displayed because the WebSocket connection failed. Please contact your local IT to allow your browser's WebSocket connection for future uses of this app and in the meantime see the Portal or Fleet Manager for each device's connection status and firmware version.\n\n";
  const textStartedAndFailedDevices =
    'Devices with upgrade status "Started" for longer than 30 minutes (these devices have not come back online) or upgrade status "Failed" (these devices have come back online with their old firmware version) have not been able to succeed their firmware upgrade.\n\n';
  const textFailedDevices =
    'Devices with upgrade status "Failed" (these devices have come back online with their old firmware version) have not been able to succeed their firmware upgrade.\n\n';
  const textCompletedDevices = "All devices were successfully upgraded.";
  const textReferenceSupportWebsite =
    'The "Firmware upgrade" article on our support website provides help with any unsuccessful firmware upgrades (support.ixon.cloud).';

  $: firmwareSelected(selectedFirmware);
  function firmwareSelected(_selectedFirmware): void {
    if (_selectedFirmware) {
      if (_selectedFirmware.allowed) {
        selectVersionAndGetRouters();
      } else {
        informFirmwareNotAvailable(
          _selectedFirmware["version"],
          _selectedFirmware["days_remaining"],
        );
      }
    }
  }
  $: showUpgradingAgentsStatusBanner(activeWebsocket, agentsStatusStarted);
  function showUpgradingAgentsStatusBanner(
    _activeWebsocket: Boolean,
    _agentsStatusStarted,
  ): void {
    if (_activeWebsocket != undefined) {
      showUpgradingAgentsStatus = true;
    } else {
      showUpgradingAgentsStatus = false;
    }
    if (_activeWebsocket != undefined && _activeWebsocket == false) {
      if (_agentsStatusStarted.length === eligibleAgents.length) {
        upgradingAgents = false;
        disableFirmwareSelect = false;
        state = State.NoWebsocketStartedInstall;
      }
    }
  }
  $: updateState(state);
  function updateState(_state: number): void {
    switch (_state) {
      case State.SearchingFirmware:
        // Searching firmware
        selectFirmwareButtonTextLong = "Searching firmware";
        selectFirmwareButtonTextShort = selectFirmwareButtonTextLong;
        startUpgradeButtonTextLong = "No firmware selected";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
        break;
      case State.WaitingFirmwareSelect:
        // Waiting for firmware selection
        selectFirmwareButtonTextLong = "Select target firmware";
        selectFirmwareButtonTextShort = "Select firmware";
        startUpgradeButtonTextLong = "No firmware selected";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        break;
      case State.SearchingDevices:
        // Firmware selected, searching devices
        startUpgradeButtonTextLong = "Searching for eligible devices";
        startUpgradeButtonTextShort = "Searching devices";
        startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
        break;
      case State.NoDevicesFound:
        // No devices found
        startUpgradeButtonTextLong = "No eligible devices found";
        startUpgradeButtonTextShort = "No devices found";
        break;
      case State.DevicesFound:
        // Devices found, waiting for upgrade start
        startUpgradeButtonTextLong =
          "Upgrade all devices (" + eligibleAgents.length + ")";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        startUpgradeButtonStyle = "startUpgradeButtonStyleEnabled";
        break;
      case State.StartInstall:
        selectFirmwareButtonTextLong = selectedFirmware["version"];
        selectFirmwareButtonTextShort = selectFirmwareButtonTextLong;
        startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
        upgradeStatusTitleStyling = "upgradeStatusTitleStyle";
        break;
      case State.InstallingFirmware:
        startUpgradeButtonTextLong =
          "Upgrading " + eligibleAgents.length + " devices";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        upgradeStatusTextLong = "Upgrading firmware";
        upgradeStatusTextShort = "Upgrading";
        informUpgradeStatusTitleText = "Upgrading firmware";
        informUpgradeStatusMessageText =
          textTimeIndication +
          textStartedAndFailedDevices +
          textReferenceSupportWebsite;
        break;
      case State.InstalledFirmware:
        startUpgradeButtonTextLong =
          "Upgraded " + eligibleAgents.length + " devices";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        upgradeStatusTextLong = "Upgrades finished";
        upgradeStatusTextShort = upgradeStatusTextLong;
        if (agentsStatusFailed.length === 0) {
          informUpgradeStatusTitleText = "Upgrades finished";
          informUpgradeStatusMessageText = textCompletedDevices;
        } else {
          informUpgradeStatusTitleText = "Upgrades finished";
          informUpgradeStatusMessageText =
            textFailedDevices + textReferenceSupportWebsite;
        }
        if (isNarrow) {
          upgradeStatusTitleStyling = "upgradeStatusTitleStyleIsNarrow";
        } else {
          upgradeStatusTitleStyling = "upgradeStatusTitleStyle";
        }
        break;
      case State.NoWebsocketStartingInstall:
        startUpgradeButtonTextLong =
          "Starting " + eligibleAgents.length + " upgrades";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        upgradeStatusTextLong = "Starting upgrades";
        upgradeStatusTextShort = "Upgrading";
        informUpgradeStatusTitleText = "Starting upgrades";
        informUpgradeStatusMessageText =
          textTimeIndication + textWebsocketError + textReferenceSupportWebsite;
        break;
      case State.NoWebsocketStartedInstall:
        startUpgradeButtonTextLong =
          "All " + agentsStatusStarted.length + " upgrades started";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        upgradeStatusTextLong = "All upgrades started";
        upgradeStatusTextShort = "All upgrades started";
        informUpgradeStatusTitleText = "All upgrades have started";
        informUpgradeStatusMessageText =
          textTimeIndication + textWebsocketError + textReferenceSupportWebsite;
        if (isNarrow) {
          upgradeStatusTitleStyling = "upgradeStatusTitleStyleIsNarrow";
        } else {
          upgradeStatusTitleStyling = "upgradeStatusTitleStyle";
        }
        break;
      case State.NotAllowed:
        // No permission
        selectFirmwareButtonTextLong = "- Not allowed -";
        selectFirmwareButtonTextShort = selectFirmwareButtonTextLong;
        startUpgradeButtonTextLong = "- Insufficient permissions -";
        startUpgradeButtonTextShort = startUpgradeButtonTextLong;
        break;
    }
  }
  $: changeTableAgents(
    tableAgentsStatus,
    agentsStatusStarted,
    agentsStatusCompleted,
    agentsStatusFailed,
  ); // added agentsStatusX so function is called when any of them change to update the content of the table
  function changeTableAgents(
    _tableAgentsStatus: number,
    _agentsStatusStarted?,
    _agentsStatusCompleted?,
    _agentsStatusFailed?,
  ): void {
    switch (_tableAgentsStatus) {
      case TableAgentsStatus.Started:
        tableAgentsStatus = TableAgentsStatus.Started; // Used to correctly update the table when agentsStatusStarted changes
        startedStatusStyling = "statusSelected";
        completedStatusStyling = "statusNotSelected";
        failedStatusStyling = "statusNotSelected";
        tableAgents = agentsStatusStarted;
        break;
      case TableAgentsStatus.Completed:
        tableAgentsStatus = TableAgentsStatus.Completed; // Used to correctly update the table when agentsStatusCompleted changes
        startedStatusStyling = "statusNotSelected";
        completedStatusStyling = "statusSelected";
        failedStatusStyling = "statusNotSelected";
        tableAgents = agentsStatusCompleted;
        break;
      case TableAgentsStatus.Failed:
        tableAgentsStatus = TableAgentsStatus.Failed; // Used to correctly update the table when agentsStatusFailed changes
        startedStatusStyling = "statusNotSelected";
        completedStatusStyling = "statusNotSelected";
        failedStatusStyling = "statusSelected";
        tableAgents = agentsStatusFailed;
        break;
    }
  }
  $: selectFirmwareButtonText = isNarrow
    ? selectFirmwareButtonTextShort
    : selectFirmwareButtonTextLong;
  $: startUpgradeButtonText = isNarrow
    ? startUpgradeButtonTextShort
    : startUpgradeButtonTextLong;
  $: tableWrapperStyling = isNarrow ? "tableWrapperIsNarrow" : "tableWrapper";
  $: hrBottomStyling = isNarrow ? "hrBottomIsNarrow" : "hrBottom";
  $: upgradeStatusText = isNarrow
    ? upgradeStatusTextShort
    : upgradeStatusTextLong;
  $: hrRightStyling = isNarrow ? "hrRightIsNarrow" : "hrRight";
  $: spinnerRowStyling = isNarrow ? "nonSpinnerRow" : "spinnerRow";

  function informUpgradeStatus() {
    context.openAlertDialog({
      title: informUpgradeStatusTitleText,
      message: informUpgradeStatusMessageText,
      buttonText: "I understand",
    });
  }
</script>

<div bind:this={rootEl}>
  <div class="componentPadding">
    <div class="componentHeader">
      <h3 class="componentTitle">Bulk Firmware Upgrade</h3>
    </div>
    <div class="componentLine">
      <!-- Exceptions that disallow firmware selection -->
      {#if searchingFirmware || !passedPermissionsCheck || disableFirmwareSelect}
        <button
          disabled
          class={startUpgradeButtonStyle}
          class:narrowWidth={isNarrow}
          type="button"
        >
          <div class="spinnerRow">
            {#if searchingFirmware}
              <div class="spinnerSpacingRight">
                <div class="spinner">
                  <div class="spinnerDark">
                    <svg
                      preserveAspectRatio="xMidYMid meet"
                      focusable="false"
                      viewBox="0 0 100 100"
                    >
                      <circle cx="50%" cy="50%" r="45" />
                    </svg>
                  </div>
                </div>
              </div>
            {/if}
            {selectFirmwareButtonText}
          </div>
        </button>
      {:else}
        <div class="select" class:narrowWidth={isNarrow}>
          <select bind:value={selectedFirmware}>
            <option value="" hidden>{selectFirmwareButtonText}</option>
            <optgroup label="IXrouter3">
              {#each firmwareList as firmware}
                {#if firmware.version[0] == 3}
                  <option value={firmware}>{firmware.version}</option>
                {/if}
              {/each}
            </optgroup><optgroup label="IXrouter2">
              {#each firmwareList as firmware}
                {#if firmware.version[0] == 2}
                  <option value={firmware}>{firmware.version}</option>
                {/if}
              {/each}
            </optgroup>
          </select>
        </div>
      {/if}
      <div class="buttonPadding" />
      <button
        disabled={disableStartUpgrade}
        class={startUpgradeButtonStyle}
        class:narrowWidth={isNarrow}
        on:click={startFirmwareUpgrade}
        type="button"
      >
        <div class="spinnerRow">
          {#if searchingAgents}
            <div class="spinnerSpacingRight">
              <div class="spinner">
                <div class="spinnerDark">
                  <svg
                    preserveAspectRatio="xMidYMid meet"
                    focusable="false"
                    viewBox="0 0 100 100"
                  >
                    <circle cx="50%" cy="50%" r="45" />
                  </svg>
                </div>
              </div>
            </div>
          {/if}
          {startUpgradeButtonText}
        </div>
      </button>
    </div>
    <div class="hrTop" />
    <div class="buttonPadding" />
    <div class={tableWrapperStyling}>
      <table class="table">
        <thead>
          <tr>
            <th class="columnName">Name</th>
            <th class="columnSerialNumber">Serial number</th>
            <th class="columnFirmware">Firmware</th>
          </tr></thead
        >
        <tbody>
          {#each tableAgents as agent}
            <tr>
              <td>{agent.name}</td>
              <td>{agent.serialNumber}</td>
              <td>{agent.firmware}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class={hrBottomStyling} />
    <div class="statusWrapper">
      {#if showUpgradingAgentsStatus}
        <span class={spinnerRowStyling}>
          <button
            class="iconButton"
            on:click={informUpgradeStatus}
            type="button"
            ><svg viewBox="0 0 24 24" width="24" height="24"
              ><path
                d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
              /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
            >
          </button>
          <span class={upgradeStatusTitleStyling}>
            {upgradeStatusText}
          </span>
          {#if upgradingAgents}
            <span class="spinnerSpacingLeftBottom">
              <div class="spinner">
                <div class="spinnerDark">
                  <svg
                    preserveAspectRatio="xMidYMid meet"
                    focusable="false"
                    viewBox="0 0 100 100"
                  >
                    <circle cx="50%" cy="50%" r="45" />
                  </svg>
                </div>
              </div>
            </span>
          {/if}
        </span>
        <span class={hrRightStyling} />
        <span>
          <button
            class={startedStatusStyling}
            on:click={() => changeTableAgents(TableAgentsStatus.Started)}
          >
            {#if !isNarrow}
              Started ( {agentsStatusStarted.length} / {eligibleAgents.length} )
            {:else}
              Started<br /> ( {agentsStatusStarted.length} )
            {/if}
          </button></span
        >
        {#if activeWebsocket}
          <span>
            <button
              class={completedStatusStyling}
              on:click={() => changeTableAgents(TableAgentsStatus.Completed)}
            >
              {#if !isNarrow}
                Completed ( {agentsStatusCompleted.length} / {eligibleAgents.length}
                )
              {:else}
                Completed<br /> ( {agentsStatusCompleted.length} )
              {/if}
            </button>
          </span>
          <span>
            <button
              class={failedStatusStyling}
              on:click={() => changeTableAgents(TableAgentsStatus.Failed)}
            >
              {#if !isNarrow}
                Failed ( {agentsStatusFailed.length} / {eligibleAgents.length}
                )
              {:else}
                Failed<br /> ( {agentsStatusFailed.length} )
              {/if}
            </button></span
          >
        {/if}
      {:else}
        <p />
      {/if}
    </div>
  </div>
</div>

<style lang="scss" scoped>
  @import "./styles/component.scss";
  @import "./styles/select.scss";
  @import "./styles/spinner.scss";
  @import "./styles/startfirmware.scss";
  @import "./styles/statusbar.scss";
  @import "./styles/table.scss";
</style>
