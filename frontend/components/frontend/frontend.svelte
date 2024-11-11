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
  let searchingFirmware = true;
  let searchingAgents = false;
  let installingFirmware = false;

  let selectFirmwareButtonText = "";
  let selectFirmwareButtonTextLong = "";
  let selectFirmwareButtonTextShort = "";
  let selectedFirmware;
  let firmwareOverview = [];
  let agentTypeList = [];
  let firmwareList = [];
  let eligibleAgents = [];
  let disableFirmwareSelect = false;

  let startInstallationButtonText = "";
  let startInstallationButtonTextLong = "";
  let startInstallationButtonTextShort = "";
  let startInstallationButtonStyle = "";
  let installationStatusText = "";
  let installationStatusTextLong = "";
  let installationStatusTextShort = "";
  const eligibleAgentsBatchSize = 5;
  let eligibleAgentsBatch = [];
  let disableStartInstallation = true;

  let tableAgentsStatus: number;
  let tableAgents = [];

  let showInstallingFirmwareStatus = false;
  let informInstallationStatusTitleText = "";
  let informInstallationStatusMessageText = "";
  let installationStatusTitleStyling = "";
  let spinnerRowStyling = "";
  let agentsStatusStarted = [];
  let agentsStatusStartedBackup = [];
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
    SearchingFirmwareVersions = 1,
    WaitingFirmwareSelect = 2,
    SearchingDevices = 3,
    NoDevicesFound = 4,
    DevicesFound = 5,
    StartInstall = 6,
    InstallingFirmware = 7,
    InstalledFirmware = 8,
    NoWebsocketStartingInstall = 9,
    NoWebsocketStartedInstall = 10,
  }

  onMount(async () => {
    state = State.SearchingFirmwareVersions; // Waiting for firmware selection
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
    response = await client.call("functions.getFirmwareVersions");
    firmwareOverview = response.data;
    agentTypeList = firmwareOverview[0];
    firmwareList = firmwareOverview[1];
    disableFirmwareSelect = false;
    searchingFirmware = false; // Hide spinner
    state = State.WaitingFirmwareSelect; // Waiting for firmware selection

    return () => {
      resizeObserver.unobserve(rootEl);
      client.destroy();
    };
  });

  async function getRouters(): Promise<void> {
    state = State.SearchingDevices; // Firmware selected, searching devices
    installingFirmware = false;
    tableAgents = [];
    eligibleAgents = [];
    agentsStatusStarted = [];
    agentsStatusCompleted = [];
    agentsStatusFailed = [];
    disableStartInstallation = true;
    searchingAgents = true; // Show spinner
    if (activeWebsocketConn) {
      activeWebsocketConn.close();
    }
    activeWebsocket = undefined;
    response = await client.call("functions.getRouters", {
      firmware: selectedFirmware,
    });
    eligibleAgents = response.data;
    searchingAgents = false; // Hide spinner
    if (eligibleAgents.length === 0) {
      state = State.NoDevicesFound; // No devices found
      disableStartInstallation = true;
    } else {
      state = State.DevicesFound; // Devices found, waiting for firmware installation start
      disableStartInstallation = false;
    }
    tableAgents = eligibleAgents;
  }

  function informFirmwareNotAvailable(
    selectedUnavailableFirmware,
    availableInDays,
  ): void {
    state = State.WaitingFirmwareSelect;
    disableStartInstallation = true;
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

  async function startFirmwareInstallation(): Promise<void> {
    state = State.StartInstall;
    establishWebsocketConn();
    disableFirmwareSelect = true;
    disableStartInstallation = true;
    installingFirmware = true;
    changeTableAgents(TableAgentsStatus.Started);
    agentsStatusStarted = [];
    for (let i = 0; i < eligibleAgents.length; i += eligibleAgentsBatchSize) {
      eligibleAgentsBatch = eligibleAgents.slice(
        i,
        i + eligibleAgentsBatchSize,
      );
      await client.call("functions.startFirmwareInstallation", {
        firmware: selectedFirmware,
        agents: eligibleAgentsBatch,
      });
      agentsStatusStarted = agentsStatusStarted.concat(eligibleAgentsBatch);
    }
    agentsStatusStartedBackup = agentsStatusStarted;
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
      agentsStatusStarted = agentsStatusStartedBackup;
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
      if (eventData?.act == "MXT") {
        // Not exclusive, but does filter out some unrelated WS messages
        if (eventData.sel[0].typ == "Agent") {
          // Agent event type (is an array, but should only be 1 index as all .dat should be of the same typ)
          eventData.dat.forEach(async (agent) => {
            if (agent.mdrServer?.publicId) {
              // Agent is back online
              let agentPubId = agent.publicId;
              url = context.getApiUrl("Agent", {
                publicId: agentPubId,
                fields: "name,publicId,lastSeenAgentUserAgent.firmwareVersion",
              });
              response = await fetch(url, {
                headers: {
                  "Content-Type": "application/json",
                  Authorization:
                    "Bearer " + context.appData.accessToken.secretId,
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
                (agentsStarted) => agentsStarted.publicId == agentPubId,
              );

              if (indexInAgentsStatusStarted !== -1) {
                // Agent is from Started list
                let agentDetails =
                  agentsStatusStarted[indexInAgentsStatusStarted];
                let agentFirmwareOld =
                  agentDetails.lastSeenAgentUserAgent.firmwareVersion;

                if (agentFirmwareNew != agentFirmwareOld) {
                  // firmware installation succeeded
                  let found = agentsStatusCompleted.find(
                    (agent) => agent.pubId == agentPubId,
                  );
                  if (!found) {
                    agentDetails.lastSeenAgentUserAgent.firmwareVersion =
                      agentFirmwareNew;
                    agentsStatusCompleted =
                      agentsStatusCompleted.concat(agentDetails);
                  }

                  let agentInAgentsStatusStarted = agentsStatusStarted.find(
                    (agentsStarted) => agentsStarted.publicId == agentPubId,
                  );
                  if (agentInAgentsStatusStarted) {
                    agentsStatusStarted = agentsStatusStarted.filter(
                      (m) => m !== agentInAgentsStatusStarted,
                    );
                    if (agentsStatusStarted.length == 0) {
                      installingFirmware = false;
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
                  // firmware installation failed
                  let found = agentsStatusFailed.find(
                    (agent) => agent.pubId == agentPubId,
                  );
                  if (!found) {
                    agentsStatusFailed =
                      agentsStatusFailed.concat(agentDetails);
                  }

                  let agentInAgentsStatusStarted = agentsStatusStarted.find(
                    (agentsStarted) => agentsStarted.publicId == agentPubId,
                  );
                  if (agentInAgentsStatusStarted) {
                    agentsStatusStarted = agentsStatusStarted.filter(
                      (m) => m !== agentInAgentsStatusStarted,
                    );
                    if (agentsStatusStarted.length == 0) {
                      installingFirmware = false;
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
              }
            }
          });
        }
      }
    };
  }

  const textTimeIndication =
    "After an installation has started, it usually takes 2 to 5 minutes for the installation to complete. Do not turn off or unplug the device during this period.\n\n";
  const textWebsocketError =
    "Installation progression cannot be displayed because the WebSocket connection failed. Please contact your local IT to allow your browser's WebSocket connection for future uses of this app and in the meantime see the Portal or Fleet Manager for each device's connection status and firmware version.\n\n";
  const textStartedAndFailedDevices =
    'Devices with status "Started" for longer than 30 minutes (these devices have not come back online) or status "Failed" (these devices have come back online with their old firmware version) have not been able to succeed their firmware installation.\n\n';
  const textFailedDevices =
    'Devices with status "Failed" (these devices have come back online with their old firmware version) have not been able to succeed their firmware installation.\n\n';
  const textCompletedDevices =
    "The firmware was successfully installed on all devices.";
  const textReferenceSupportWebsite =
    'The "Firmware upgrade" article on our support website provides help with any unsuccessful firmware installations (support.ixon.cloud).';

  $: firmwareSelected(selectedFirmware);
  function firmwareSelected(_selectedFirmware): void {
    if (_selectedFirmware) {
      if (_selectedFirmware.allowed) {
        getRouters();
      } else {
        informFirmwareNotAvailable(
          _selectedFirmware["version"],
          _selectedFirmware["days_remaining"],
        );
      }
    }
  }
  $: showInstallingFirmwareStatusBanner(activeWebsocket, agentsStatusStarted);
  function showInstallingFirmwareStatusBanner(
    _activeWebsocket: Boolean,
    _agentsStatusStarted,
  ): void {
    if (_activeWebsocket != undefined) {
      showInstallingFirmwareStatus = true;
    } else {
      showInstallingFirmwareStatus = false;
    }
    if (_activeWebsocket != undefined && _activeWebsocket == false) {
      if (_agentsStatusStarted.length === eligibleAgents.length) {
        installingFirmware = false;
        disableFirmwareSelect = false;
        state = State.NoWebsocketStartedInstall;
      }
    }
  }
  $: updateState(state);
  function updateState(_state: number): void {
    switch (_state) {
      case State.SearchingFirmwareVersions:
        // Searching firmware
        selectFirmwareButtonTextLong = "Searching firmware";
        selectFirmwareButtonTextShort = selectFirmwareButtonTextLong;
        startInstallationButtonTextLong = "No firmware selected";
        startInstallationButtonTextShort = startInstallationButtonTextLong;
        startInstallationButtonStyle = "startInstallationButtonStyleDisabled";
        break;
      case State.WaitingFirmwareSelect:
        // Waiting for firmware selection
        selectFirmwareButtonTextLong = "Select target firmware";
        selectFirmwareButtonTextShort = "Select firmware";
        startInstallationButtonTextLong = "No firmware selected";
        startInstallationButtonTextShort = startInstallationButtonTextLong;
        break;
      case State.SearchingDevices:
        // Firmware selected, searching devices
        startInstallationButtonTextLong = "Searching for eligible devices";
        startInstallationButtonTextShort = "Searching devices";
        startInstallationButtonStyle = "startInstallationButtonStyleDisabled";
        break;
      case State.NoDevicesFound:
        // No devices found
        startInstallationButtonTextLong = "No eligible devices found";
        startInstallationButtonTextShort = "No devices found";
        startInstallationButtonStyle = "startInstallationButtonStyleDisabled";
        break;
      case State.DevicesFound:
        // Devices found, waiting for installation start
        startInstallationButtonTextLong =
          "Install on all devices (" + eligibleAgents.length + ")";
        startInstallationButtonTextShort = startInstallationButtonTextLong;
        startInstallationButtonStyle = "startInstallationButtonStyleEnabled";
        break;
      case State.StartInstall:
        selectFirmwareButtonTextLong = selectedFirmware["version"];
        selectFirmwareButtonTextShort = selectFirmwareButtonTextLong;
        startInstallationButtonTextLong =
          "Installing on all devices (" + eligibleAgents.length + ")";
        startInstallationButtonTextShort = "Installing firmware";
        installationStatusTextLong = "Installing firmware";
        installationStatusTextShort = "Installing";
        startInstallationButtonStyle = "startInstallationButtonStyleDisabled";
        installationStatusTitleStyling = "installationStatusTitleStyle";
        break;
      case State.InstallingFirmware:
        informInstallationStatusTitleText = "Installing firmware";
        informInstallationStatusMessageText =
          textTimeIndication +
          textStartedAndFailedDevices +
          textReferenceSupportWebsite;
        break;
      case State.InstalledFirmware:
        startInstallationButtonTextLong = "Installations finished";
        startInstallationButtonTextShort = startInstallationButtonTextLong;
        installationStatusTextLong = "Installations finished";
        installationStatusTextShort = installationStatusTextLong;
        if (agentsStatusFailed.length === 0) {
          informInstallationStatusTitleText = "Installations finished";
          informInstallationStatusMessageText = textCompletedDevices;
        } else {
          informInstallationStatusTitleText = "Installations finished";
          informInstallationStatusMessageText =
            textFailedDevices + textReferenceSupportWebsite;
        }
        if (isNarrow) {
          installationStatusTitleStyling =
            "installationStatusTitleStyleIsNarrow";
        } else {
          installationStatusTitleStyling = "installationStatusTitleStyle";
        }
        break;
      case State.NoWebsocketStartingInstall:
        startInstallationButtonTextLong = "Installing firmware";
        startInstallationButtonTextShort = startInstallationButtonTextLong;
        informInstallationStatusTitleText = "Installing firmware";
        informInstallationStatusMessageText =
          textTimeIndication + textWebsocketError + textReferenceSupportWebsite;
        break;
      case State.NoWebsocketStartedInstall:
        startInstallationButtonTextLong = "Installations started";
        startInstallationButtonTextShort = startInstallationButtonTextLong;
        installationStatusTextLong = "Installations started";
        installationStatusTextShort = installationStatusTextLong;
        informInstallationStatusTitleText = "All installations have started";
        informInstallationStatusMessageText =
          textTimeIndication + textWebsocketError + textReferenceSupportWebsite;
        if (isNarrow) {
          installationStatusTitleStyling =
            "installationStatusTitleStyleIsNarrow";
        } else {
          installationStatusTitleStyling = "installationStatusTitleStyle";
        }
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
  $: startInstallationButtonText = isNarrow
    ? startInstallationButtonTextShort
    : startInstallationButtonTextLong;
  $: tableWrapperStyling = isNarrow ? "tableWrapperIsNarrow" : "tableWrapper";
  $: hrBottomStyling = isNarrow ? "hrBottomIsNarrow" : "hrBottom";
  $: installationStatusText = isNarrow
    ? installationStatusTextShort
    : installationStatusTextLong;
  $: hrRightStyling = isNarrow ? "hrRightIsNarrow" : "hrRight";
  $: spinnerRowStyling = isNarrow ? "nonSpinnerRow" : "spinnerRow";

  function informInstallationStatus() {
    context.openAlertDialog({
      title: informInstallationStatusTitleText,
      message: informInstallationStatusMessageText,
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
      {#if disableFirmwareSelect}
        <button
          disabled
          class={startInstallationButtonStyle}
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
            {#each agentTypeList as agentType}
              <optgroup label={agentType.name}>
                {#each firmwareList as firmware}
                  {#if firmware.agent_type_publicId == agentType.publicId}
                    <option value={firmware}>{firmware.version}</option>
                  {/if}
                {/each}
              </optgroup>
            {/each}
          </select>
        </div>
      {/if}
      <div class="buttonPadding" />
      <button
        disabled={disableStartInstallation}
        class={startInstallationButtonStyle}
        class:narrowWidth={isNarrow}
        on:click={startFirmwareInstallation}
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
          {startInstallationButtonText}
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
              <td>{agent.lastSeenAgentUserAgent.firmwareVersion}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class={hrBottomStyling} />
    <div class="statusWrapper">
      {#if showInstallingFirmwareStatus}
        <span class={spinnerRowStyling}>
          <button
            class="iconButton"
            on:click={informInstallationStatus}
            type="button"
            ><svg viewBox="0 0 24 24" width="24" height="24"
              ><path
                d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
              /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
            >
          </button>
          <span class={installationStatusTitleStyling}>
            {installationStatusText}
          </span>
          {#if installingFirmware}
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
