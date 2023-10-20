<script lang="ts">
  import { onMount } from "svelte";

  export let context;

  let client;
  let response;

  let firmwareList = [];
  let selectedFirmware;
  let eligibleAgents = [];

  let selectFirmwareButtonText = "Select target firmware";
  let selectFirmwareButtonTextShort = "Select firmware";
  let disableFirmwareSelect = false;

  const upgradeBatchSize = 50;
  let eligibleAgentsBatch;
  let disableStartUpgrade = true;
  let loading = false;
  let spinnerColor = "spinnerLight";
  let startUpgradeButtonText = "No eligible devices found";
  let startUpgradeButtonTextShort = "No devices found";
  let startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
  let upgradesAllStarted;

  let rootEl: HTMLElement;
  let width: number | null = null;
  $: isNarrow = width !== null ? width <= 460 : false;

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
    selectFirmwareButtonText = "Searching firmware...";
    selectFirmwareButtonTextShort = "Searching firmware...";
    width = rootEl.getBoundingClientRect().width;
    const resizeObserver = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        width = entry.contentRect.width;
      });
    });
    resizeObserver.observe(rootEl);

    client = context.createBackendComponentClient();
    response = await client.call("functions.getFirmwareVersions");
    firmwareList = response.data;
    console.log(firmwareList);
    disableFirmwareSelect = false;
    selectFirmwareButtonText = "Select target firmware";
    selectFirmwareButtonTextShort = "Select firmware";

    return () => {
      resizeObserver.unobserve(rootEl);
    };
  });

  async function selectVersionAndGetRouters() {
    disableStartUpgrade = true;
    loading = true; // Show spinner
    spinnerColor = "spinnerDark";
    startUpgradeButtonText = "Searching for eligible devices";
    startUpgradeButtonTextShort = "Searching devices";
    startUpgradeButtonStyle = "startUpgradeButtonStyleDisabled";
    const response = await client.call("functions.selectVersionAndGetRouters", {
      firmware: selectedFirmware,
    });
    eligibleAgents = response.data;
    console.log(eligibleAgents);
    upgradesAllStarted = false; // Reset value
    loading = false; // Hide spinner
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
  }

  async function informFirmwareNotAvailable(
    selectedUnavailableFirmware,
    availableInDays
  ): Promise<void> {
    disableStartUpgrade = true;
    startUpgradeButtonText = "No eligible devices found";
    startUpgradeButtonTextShort = "No devices found";
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
    disableFirmwareSelect = true;
    disableStartUpgrade = true;
    loading = true; // Show spinner
    spinnerColor = "spinnerLight";
    startUpgradeButtonText = "Starting all upgrades";
    startUpgradeButtonTextShort = "Starting upgrades";
    startUpgradeButtonStyle = "startUpgradeButtonStyleStarting";
    console.log(selectedFirmware);
    console.log(eligibleAgents);
    informKeepPageOpen();
    for (let i = 0; i < eligibleAgents.length; i += upgradeBatchSize) {
      eligibleAgentsBatch = eligibleAgents.slice(i, i + upgradeBatchSize);
      const response = await client.call("functions.startFirmwareUpgrade", {
        firmware: selectedFirmware,
        agents: eligibleAgentsBatch,
      });
    }
    console.log(response);
    upgradesAllStarted = response.data;
    if (upgradesAllStarted) {
      disableFirmwareSelect = false;
      disableStartUpgrade = true;
      loading = false; // Hide spinner
      startUpgradeButtonText = "All device upgrades started";
      startUpgradeButtonTextShort = "All upgrades started";
      startUpgradeButtonStyle = "startUpgradeButtonStyleCompleted";
    }
  }

  async function informKeepPageOpen(): Promise<void> {
    const result = await context.openAlertDialog({
      title: "Starting upgrades",
      message:
        "Please remain on this page until all device upgrades have started.",
      buttonText: "I understand",
    });
  }
</script>

<main bind:this={rootEl}>
  <div class="componentPadding">
    <div class="componentHeader">
      <h3 class="componentTitle">Bulk Firmware Upgrade</h3>
    </div>
    <div class="componentLine">
      <div class="select" class:is-narrow={isNarrow}>
        <select
          disabled={disableFirmwareSelect}
          id="my_select"
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
      <button
        disabled={disableStartUpgrade}
        class={startUpgradeButtonStyle}
        class:narrowWidth={isNarrow}
        on:click={startFirmwareUpgrade}
        type="button"
      >
        {#if loading}
          <div class="spinnerRow">
            <div class="spinnerSpacing">
              <div class="spinner">
                <div class={spinnerColor}>
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
  </div>
</main>

<style lang="scss" scoped>
  @import "./styles/component.scss";
  @import "./styles/startfirmware.scss";
  @import "./styles/spinner.scss";

  select {
    appearance: none; /* Removes the default dropdown arrow */
    padding: 0 1em 0 0;
    cursor: pointer;
    height: 37px;
    text-align: center;
    border: 1px solid;
    border-radius: 4px;
    border-color: rgba(0, 0, 0, 0.12);
    background-color: white;
    color: var(--body-color);
    font-size: 14px;
    font-family: var(--font-family);
    font-weight: 500;
  }

  select:disabled {
    cursor: auto;
    border-color: transparent;
    background-color: rgba(0, 0, 0, 0.12);
    color: var(--body-color);
    font-weight: normal;
  }

  .select {
    padding-right: 8px;
    width: 230px;
    display: grid;
    grid-template-areas: "select";
    align-items: center;
  }

  .select::after {
    content: "";
    width: 0.6em;
    height: 0.3em;
    background-color: var(--body-color);
    clip-path: polygon(100% 0%, 0 0%, 50% 100%);

    justify-self: right;

    pointer-events: none;
    margin-right: 0.9em;
  }

  select,
  .select:after {
    grid-area: select;
  }

  optgroup {
    font-style: normal;
    background-color: white;
    color: var(--body-color);
    text-align: left;
    text-align-last: center;
  }
</style>
