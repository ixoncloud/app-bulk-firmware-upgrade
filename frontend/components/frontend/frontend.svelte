<script lang="ts">
  import { onMount } from "svelte";

  export let context;

  let client;
  let response;

  let firmwareList = [];
  let selectedFirmware;
  let tableAgents = [];
  let eligibleAgents = [];

  let passedPermissionsCheck = false;

  let searchingFirmware = true;
  let selectFirmwareButtonText = "Select target firmware";
  let selectFirmwareButtonTextShort = "Select firmware";
  let disableFirmwareSelect = false;

  const upgradeBatchSize = 5;
  let eligibleAgentsBatch = [];
  let disableStartUpgrade = true;
  let searchingAgents = false;
  let startUpgradeButtonText = "No firmware selected";
  let startUpgradeButtonTextShort = "No firmware selected";
  let startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";

  let showUpgradingAgentsStatus = false; // <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< testing, default should be false
  let upgradingAgents = false; // <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< testing, default should be false

  let url;
  let urlAuthToken;
  let urlWebsocket;
  let authToken;
  $: activeWebsocketConn = undefined;
  let activeWebsocket;
  let timerWebsocketRenewal;
  let agentsStatusStarted = [];
  let agentsStatusCompleted = [];
  let agentsStatusFailed = [];
  let startedStatusStyling = "statusNotSelected";
  let completedStatusStyling = "statusNotSelected";
  let failedStatusStyling = "statusNotSelected";

  let rootEl: HTMLElement;
  let width: number | null = null;
  $: isNarrow = width !== null ? width <= 580 : false;

  $: if (selectedFirmware) {
    console.log(selectedFirmware);
    if (selectedFirmware.allowed) {
      selectVersionAndGetRouters();
    } else {
      informFirmwareNotAvailable(
        selectedFirmware["version"],
        selectedFirmware["days_remaining"]
      );
    }
  }

  onMount(async () => {
    disableFirmwareSelect = true;
    searchingFirmware = true; // Show spinner
    selectFirmwareButtonText = "Searching firmware";
    selectFirmwareButtonTextShort = "Searching firmware";
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
      console.log(firmwareList);
      disableFirmwareSelect = false;
      searchingFirmware = false; // Hide spinner
      selectFirmwareButtonText = "Select target firmware";
      selectFirmwareButtonTextShort = "Select firmware";
    } else {
      selectFirmwareButtonText = "- Not allowed -";
      selectFirmwareButtonTextShort = "- Not allowed -";
      searchingFirmware = false; // Hide spinner
      startUpgradeButtonText = "- Insufficient permissions -";
      startUpgradeButtonTextShort = "- Insufficient permissions -";
    }

    return () => {
      resizeObserver.unobserve(rootEl);
    };
  });

  async function selectVersionAndGetRouters() {
    upgradingAgents = false;
    eligibleAgents = [];
    agentsStatusStarted = [];
    agentsStatusCompleted = [];
    agentsStatusFailed = [];
    disableStartUpgrade = true;
    searchingAgents = true; // Show spinner
    startUpgradeButtonText = "Searching for eligible devices";
    startUpgradeButtonTextShort = "Searching devices";
    startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
    if (activeWebsocketConn) {
      activeWebsocketConn.close();
    }
    activeWebsocket = undefined;
    response = await client.call("functions.selectVersionAndGetRouters", {
      firmware: selectedFirmware,
    });
    eligibleAgents = response.data;
    console.log(eligibleAgents);
    searchingAgents = false; // Hide spinner
    if (eligibleAgents.length === 0) {
      disableStartUpgrade = true;
      startUpgradeButtonText = "No eligible devices found";
      startUpgradeButtonTextShort = "No devices found";
      startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
    } else {
      disableStartUpgrade = false;
      startUpgradeButtonText =
        "Upgrade all devices (" + eligibleAgents.length + ")";
      startUpgradeButtonTextShort =
        "Upgrade all devices (" + eligibleAgents.length + ")";
      startUpgradeButtonStyle = "startUpgradeButtonStyleEnabled";
    }
    tableAgents = eligibleAgents;
  }

  async function informFirmwareNotAvailable(
    selectedUnavailableFirmware,
    availableInDays
  ): Promise<void> {
    disableStartUpgrade = true;
    startUpgradeButtonText = "No firmware selected";
    startUpgradeButtonTextShort = "No firmware selected";
    startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
    selectedFirmware = "";
    const result = await context.openAlertDialog({
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

  async function startFirmwareUpgrade() {
    establishWebsocketConn();
    disableFirmwareSelect = true;
    disableStartUpgrade = true;
    // showUpgradingAgentsStatus = true;
    upgradingAgents = true;
    changeTableAgentsStarted();
    startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
    console.log(selectedFirmware);
    console.log(eligibleAgents);
    // informKeepPageOpen();
    agentsStatusStarted = [];
    for (let i = 0; i < eligibleAgents.length; i += upgradeBatchSize) {
      eligibleAgentsBatch = eligibleAgents.slice(i, i + upgradeBatchSize);
      response = await client.call("functions.startFirmwareUpgrade", {
        firmware: selectedFirmware,
        agents: eligibleAgentsBatch,
      });
      agentsStatusStarted = agentsStatusStarted.concat(eligibleAgentsBatch);
    }
  }

  async function establishWebsocketConn(): Promise<void> {
    urlAuthToken = context.getApiUrl("AuthTokenChangeNotificationsList");
    response = await fetch(urlAuthToken, {
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

    urlWebsocket = context.getApiUrl("ChangeNotificationWebSocket");
    if (activeWebsocketConn) {
      activeWebsocketConn.close();
    }
    activeWebsocketConn = new WebSocket(urlWebsocket, "change-notifications");

    activeWebsocketConn.onerror = (event) => {
      activeWebsocket = false;
      startUpgradeButtonText =
        "Starting " + eligibleAgents.length + " upgrades";
      startUpgradeButtonTextShort =
        "Starting " + eligibleAgents.length + " upgrades";
      console.log("WebSocket error: ", event);
    };

    activeWebsocketConn.onopen = (event) => {
      activeWebsocket = true;
      startUpgradeButtonText =
        "Upgrading " + eligibleAgents.length + " devices";
      startUpgradeButtonTextShort =
        "Upgrading " + eligibleAgents.length + " devices";
      activeWebsocketConn.send('{"aut":"' + authToken + '"}');
      activeWebsocketConn.send(
        '{"sub":["Company/' + context.appData.company.publicId + '"]}'
      );
      timerWebsocketRenewal = setTimeout(establishWebsocketConn, 5000); // 5 min before WS expires
    };

    activeWebsocketConn.onmessage = (event) => {
      let eventData = JSON.parse(event.data);
      if (eventData?.dat?.mqttChangedOn && eventData.dat.mdrServer) {
        // If-statement returns true if eventData.dat exists and both mqttChangedOn and mdrServer are not null, so MQTT connected
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
          let indx = agentsStatusStarted.findIndex(
            (agent) => agent.publicId == agentPubId
          );
          let agentDetails = agentsStatusStarted[indx];
          let agentFirmwareOld = agentDetails.firmware;

          if (agentFirmwareNew != agentFirmwareOld) {
            // firmware upgrade succeeded
            let found = agentsStatusCompleted.find(
              (agent) => agent.publicId == agentPubId
            );
            if (!found) {
              agentsStatusCompleted =
                agentsStatusCompleted.concat(agentDetails);
            }

            let indx = agentsStatusStarted.find(
              (agent) => agent.publicId == agentPubId
            );
            if (indx) {
              agentsStatusStarted = agentsStatusStarted.filter(
                (m) => m !== indx
              );
              if (agentsStatusStarted.length == 0) {
                upgradingAgents = false;
                disableFirmwareSelect = false;
                startUpgradeButtonText =
                  "Upgraded " + eligibleAgents.length + " devices";
                startUpgradeButtonTextShort =
                  "Upgraded " + eligibleAgents.length + " devices";
                if (agentsStatusCompleted.length != 0) {
                  changeTableAgentsCompleted();
                } else {
                  changeTableAgentsFailed();
                }
                clearTimeout(timerWebsocketRenewal);
                activeWebsocketConn.close();
              }
            }
          } else {
            // firmware upgrade failed
            let found = agentsStatusFailed.find(
              (agent) => agent.publicId == agentPubId
            );
            if (!found) {
              agentsStatusFailed = agentsStatusFailed.concat(agentDetails);
            }

            let indx = agentsStatusStarted.find(
              (agent) => agent.publicId == agentPubId
            );
            if (indx) {
              agentsStatusStarted = agentsStatusStarted.filter(
                (m) => m !== indx
              );
              if (agentsStatusStarted.length == 0) {
                upgradingAgents = false;
                disableFirmwareSelect = false;
                startUpgradeButtonText =
                  "Upgraded " + eligibleAgents.length + " devices";
                startUpgradeButtonTextShort =
                  "Upgraded " + eligibleAgents.length + " devices";
                if (agentsStatusCompleted.length != 0) {
                  changeTableAgentsCompleted();
                } else {
                  changeTableAgentsFailed();
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

  let textTimeIndication =
    "After an upgrade has started, it usually takes 2 to 5 minutes for the upgrade to complete. Do not turn off or unplug the device during this period.\n\n";
  let textWebsocketError =
    "Upgrade progression cannot be displayed because the WebSocket connection failed. Please contact your local IT to allow your browser's WebSocket connection for future uses of this app and in the meantime see the Portal or Fleet Manager for each device's connection status and firmware version.\n\n";
  let textStartedAndFailedDevices =
    'Devices with upgrade status "Started" for longer than 30 minutes (these devices have not come back online) or upgrade status "Failed" (these devices have come back online with their old firmware version) have not been able to succeed their firmware upgrade.\n\n';
  let textFailedDevices =
    'Devices with upgrade status "Failed" (these devices have come back online with their old firmware version) have not been able to succeed their firmware upgrade.\n\n';
  let textCompletedDevices = "All devices were successfully upgraded.";
  let textReferenceSupportWebsite =
    'The "Firmware upgrade" article on our support website provides help with any unsuccessful firmware upgrades (support.ixon.cloud).';
  async function informUpgradingFirmware(): Promise<void> {
    const result = await context.openAlertDialog({
      title: "Upgrading firmware",
      message:
        textTimeIndication +
        textStartedAndFailedDevices +
        textReferenceSupportWebsite,
      buttonText: "I understand",
    });
  }
  async function informUpgradingFirmwareNoWebsocket(): Promise<void> {
    const result = await context.openAlertDialog({
      title: "Starting upgrades",
      message:
        textTimeIndication + textWebsocketError + textReferenceSupportWebsite,
      buttonText: "I understand",
    });
  }
  async function informUpgradesFinished(): Promise<void> {
    const result = await context.openAlertDialog({
      title: "Upgrades finished",
      message: textFailedDevices + textReferenceSupportWebsite,
      buttonText: "I understand",
    });
  }
  async function informUpgradesFinishedNoneFailed(): Promise<void> {
    const result = await context.openAlertDialog({
      title: "Upgrades finished",
      message: textCompletedDevices,
      buttonText: "I understand",
    });
  }
  async function informUpgradesFinishedNoWebsocket(): Promise<void> {
    const result = await context.openAlertDialog({
      title: "All upgrades have started",
      message: textWebsocketError + textReferenceSupportWebsite,
      buttonText: "I understand",
    });
  }

  let tableAgentsStatus = "";
  async function changeTableAgentsStarted(): Promise<void> {
    startedStatusStyling = "statusSelected";
    completedStatusStyling = "statusNotSelected";
    failedStatusStyling = "statusNotSelected";
    tableAgentsStatus = "started";
  }
  async function changeTableAgentsCompleted(): Promise<void> {
    startedStatusStyling = "statusNotSelected";
    completedStatusStyling = "statusSelected";
    failedStatusStyling = "statusNotSelected";
    tableAgentsStatus = "completed";
  }
  async function changeTableAgentsFailed(): Promise<void> {
    startedStatusStyling = "statusNotSelected";
    completedStatusStyling = "statusNotSelected";
    failedStatusStyling = "statusSelected";
    tableAgentsStatus = "failed";
  }
  $: if (tableAgentsStatus === "started") {
    tableAgents = agentsStatusStarted;
  } else if (tableAgentsStatus === "completed") {
    tableAgents = agentsStatusCompleted;
  } else if (tableAgentsStatus === "failed") {
    tableAgents = agentsStatusFailed;
  }
  $: if (activeWebsocket != undefined) {
    showUpgradingAgentsStatus = true;
  } else {
    showUpgradingAgentsStatus = false;
  }
  $: if (activeWebsocket != undefined && activeWebsocket == false) {
    if (agentsStatusStarted.length === eligibleAgents.length) {
      upgradingAgents = false;
      disableFirmwareSelect = false;
      startUpgradeButtonText =
        "All " + agentsStatusStarted.length + " upgrades started";
      startUpgradeButtonTextShort =
        "All " + agentsStatusStarted.length + " upgrades started";
    }
  }
</script>

<main bind:this={rootEl}>
  <div class="componentPadding">
    <div class="componentHeader">
      <h3 class="componentTitle">Bulk Firmware Upgrade</h3>
    </div>
    <div class="componentLine">
      {#if searchingFirmware || !passedPermissionsCheck}
        <button
          disabled
          class={startUpgradeButtonStyle}
          class:narrowWidth={isNarrow}
          type="button"
        >
          {#if searchingFirmware}
            <div class="spinnerRow">
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
              {#if !isNarrow}
                {selectFirmwareButtonText}
              {:else}
                {selectFirmwareButtonTextShort}
              {/if}
            </div>
          {:else if !isNarrow}
            {selectFirmwareButtonText}
          {:else}
            {selectFirmwareButtonTextShort}
          {/if}
        </button>
      {:else if disableFirmwareSelect}
        <button
          disabled
          class={startUpgradeButtonStyle}
          class:narrowWidth={isNarrow}
          type="button"
        >
          {#if !isNarrow}
            {selectedFirmware["version"]}
          {:else}
            {selectedFirmware["version"]}
          {/if}
        </button>
      {:else}
        <div class="select" class:is-narrow={isNarrow}>
          <select
            disabled={disableFirmwareSelect}
            bind:value={selectedFirmware}
          >
            <option value="" hidden>
              {#if !isNarrow}
                {selectFirmwareButtonText}
              {:else}
                {selectFirmwareButtonTextShort}
              {/if}</option
            >
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
            </optgroup></select
          >
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
        {#if searchingAgents}
          <div class="spinnerRow">
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
            {#if !isNarrow}
              {startUpgradeButtonText}
            {:else}
              {startUpgradeButtonTextShort}
            {/if}
          </div>
        {:else if !isNarrow}
          {startUpgradeButtonText}
        {:else}
          {startUpgradeButtonTextShort}
        {/if}
      </button>
    </div>
    <div class="hrTop" />
    <div class="buttonPadding" />
    {#if !isNarrow}
      <div class="tableWrapper">
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
      <div class="hrBottom" />
    {:else}
      <div class="tableWrapperIsNarrow">
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
      <div class="hrBottomIsNarrow" />
    {/if}
    {#if showUpgradingAgentsStatus}
      <div class="statusWrapper">
        {#if !isNarrow}
          {#if activeWebsocket}
            {#if upgradingAgents}
              <span class="spinnerRow">
                <button
                  class="iconButton"
                  on:click={informUpgradingFirmware}
                  type="button"
                  ><svg viewBox="0 0 24 24" width="24" height="24"
                    ><path
                      d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                    /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                  >
                </button>
                <span class="upgradeStatusTitleStyleUpgrading">
                  Upgrading firmware
                </span>
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
              </span>
            {:else if !upgradingAgents}
              {#if agentsStatusFailed.length === 0}
                <span class="upgradeStatusTitleStyleNotUpgrading">
                  <button
                    class="iconButton"
                    on:click={informUpgradesFinishedNoneFailed}
                    type="button"
                    ><svg viewBox="0 0 24 24" width="24" height="24"
                      ><path
                        d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                      /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                    >
                  </button>Upgrades finished
                </span>
              {:else}
                <span class="upgradeStatusTitleStyleNotUpgrading">
                  <button
                    class="iconButton"
                    on:click={informUpgradesFinished}
                    type="button"
                    ><svg viewBox="0 0 24 24" width="24" height="24"
                      ><path
                        d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                      /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                    >
                  </button>Upgrades finished
                </span>
              {/if}
            {/if}
            <span class="hrRight" />
            <span>
              <button
                class={startedStatusStyling}
                on:click={changeTableAgentsStarted}
                >Started ( {agentsStatusStarted.length} / {eligibleAgents.length}
                )
              </button></span
            >
            <span>
              <button
                class={completedStatusStyling}
                on:click={changeTableAgentsCompleted}
                >Completed ( {agentsStatusCompleted.length} / {eligibleAgents.length}
                )
              </button>
            </span>
            <span>
              <button
                class={failedStatusStyling}
                on:click={changeTableAgentsFailed}
                >Failed ( {agentsStatusFailed.length} / {eligibleAgents.length}
                )
              </button></span
            >
          {:else if !activeWebsocket}
            {#if upgradingAgents}
              <span class="spinnerRow">
                <button
                  class="iconButton"
                  on:click={informUpgradingFirmwareNoWebsocket}
                  type="button"
                  ><svg viewBox="0 0 24 24" width="24" height="24"
                    ><path
                      d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                    /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                  >
                </button>
                <span class="upgradeStatusTitleStyleUpgrading">
                  Starting upgrades
                </span>
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
              </span>
            {:else if !upgradingAgents}
              <span class="upgradeStatusTitleStyleNotUpgrading">
                <button
                  class="iconButton"
                  on:click={informUpgradesFinishedNoWebsocket}
                  type="button"
                  ><svg viewBox="0 0 24 24" width="24" height="24"
                    ><path
                      d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                    /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                  >
                </button>All upgrades started
              </span>
            {/if}
            <span class="hrRight" />
            <span>
              <button
                class="statusSelectedNoWebsocket"
                on:click={changeTableAgentsStarted}
                >Started ( {agentsStatusStarted.length} / {eligibleAgents.length}
                )
              </button></span
            >
          {/if}
        {:else if isNarrow}
          {#if activeWebsocket}
            {#if upgradingAgents}
              <span class="nonSpinnerRow">
                <button
                  class="iconButton"
                  on:click={informUpgradingFirmware}
                  type="button"
                  ><svg viewBox="0 0 24 24" width="24" height="24"
                    ><path
                      d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                    /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                  >
                </button>
                <span class="upgradeStatusTitleStyleUpgrading">
                  Upgrading
                </span>
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
              </span>
            {:else if !upgradingAgents}
              <span class="nonSpinnerRow">
                <button
                  class="iconButton"
                  on:click={informUpgradesFinished}
                  type="button"
                  ><svg viewBox="0 0 24 24" width="24" height="24"
                    ><path
                      d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                    /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                  >
                </button>
                <span class="upgradeStatusTitleStyleNotUpgradingIsNarrow"
                  >Upgrades finished
                </span>
              </span>
            {/if}
            <span class="hrRightIsNarrow" />
            <span>
              <button
                class={startedStatusStyling}
                on:click={changeTableAgentsStarted}
                >Started<br />( {agentsStatusStarted.length} )
              </button></span
            >
            <span>
              <button
                class={completedStatusStyling}
                on:click={changeTableAgentsCompleted}
                >Completed<br />( {agentsStatusCompleted.length} )
              </button>
            </span>
            <span>
              <button
                class={failedStatusStyling}
                on:click={changeTableAgentsFailed}
                >Failed<br />( {agentsStatusFailed.length} )
              </button></span
            >
          {:else if !activeWebsocket}
            {#if upgradingAgents}
              <span class="nonSpinnerRow">
                <button
                  class="iconButton"
                  on:click={informUpgradingFirmwareNoWebsocket}
                  type="button"
                  ><svg viewBox="0 0 24 24" width="24" height="24"
                    ><path
                      d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                    /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                  >
                </button>
                <span class="upgradeStatusTitleStyleUpgrading">
                  Starting upgrades
                </span>
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
              </span>
            {:else if !upgradingAgents}
              <span class="nonSpinnerRow">
                <button
                  class="iconButton"
                  on:click={informUpgradesFinishedNoWebsocket}
                  type="button"
                  ><svg viewBox="0 0 24 24" width="24" height="24"
                    ><path
                      d="M12 20c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-18C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                    /><path d="M11 9h2V7h-2v2zm0 8h2v-6h-2v6z" /></svg
                  >
                </button>
                <span class="upgradeStatusTitleStyleNotUpgradingIsNarrow"
                  >All upgrades started
                </span>
              </span>
            {/if}
            <span class="hrRightIsNarrow" />
            <span>
              <button
                class={startedStatusStyling}
                on:click={changeTableAgentsStarted}
                >Started<br />( {agentsStatusStarted.length} )
              </button></span
            >
          {/if}
        {/if}
      </div>
    {:else}
      <div class="statusWrapper">
        <p />
      </div>
    {/if}
  </div>
</main>

<style lang="scss" scoped>
  @import "./styles/component.scss";
  @import "./styles/select.scss";
  @import "./styles/spinner.scss";
  @import "./styles/startfirmware.scss";
  @import "./styles/statusbar.scss";
  @import "./styles/table.scss";
</style>
