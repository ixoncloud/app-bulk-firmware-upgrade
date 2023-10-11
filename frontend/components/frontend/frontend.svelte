<script lang="ts">
  import { onMount } from "svelte";

  export let context;

  let client;
  let response;

  let firmwareList = [];
  let selectedFirmware;
  let eligibleAgents;

  let selectFirmwareButtonText = "Select target firmware";
  let selectFirmwareButtonTextShort = "Select firmware";

  let disableFirmwareSelect = false;
  let disableStartUpgrade = true;
  let startUpgradeButtonText = "No eligible devices found";
  let startUpgradeButtonTextShort = "No devices found";
  let upgradesAllStarted;

  let rootEl: HTMLElement;
  let width: number | null = null;
  $: isNarrow = width !== null ? width <= 460 : false;

  onMount(async () => {
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

    return () => {
      resizeObserver.unobserve(rootEl);
    };
  });

  async function selectVersionAndGetRouters() {
    disableStartUpgrade = true;
    startUpgradeButtonText = "Searching for eligible devices";
    startUpgradeButtonTextShort = "Searching devices";
    const response = await client.call("functions.selectVersionAndGetRouters", {
      firmware: selectedFirmware,
    });
    eligibleAgents = response.data;
    console.log(eligibleAgents);
    upgradesAllStarted = false; // Reset value
    if (eligibleAgents.length === 0) {
      disableStartUpgrade = true;
      startUpgradeButtonText = "No eligible devices found";
      startUpgradeButtonTextShort = "No devices found";
    } else {
      disableStartUpgrade = false;
      startUpgradeButtonText = "Upgrade all eligible devices";
      startUpgradeButtonTextShort = "Upgrade all devices";
    }
  }
  async function startFirmwareUpgrade() {
    disableFirmwareSelect = true;
    disableStartUpgrade = true;
    startUpgradeButtonText = "Starting all device upgrades";
    startUpgradeButtonTextShort = "Starting all upgrades";
    console.log(selectedFirmware);
    console.log(eligibleAgents);
    const response = await client.call("functions.startFirmwareUpgrade", {
      firmware: selectedFirmware,
      agents: eligibleAgents,
    });
    console.log(response);
    upgradesAllStarted = response.data;
    if (upgradesAllStarted) {
      disableFirmwareSelect = false;
      disableStartUpgrade = true;
      startUpgradeButtonText = "All device upgrades started";
      startUpgradeButtonTextShort = "All upgrades started";
    }
  }
</script>

<main class="component" bind:this={rootEl}>
  <div class="componentHeader">
    <h3 class="componentTitle">Bulk Firmware Upgrade</h3>
  </div>
  <div class="componentLine">
    <div class="select" class:is-narrow={isNarrow}>
      <select disabled={disableFirmwareSelect} bind:value={selectedFirmware}>
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
              <option on:click={selectVersionAndGetRouters} value={firmware}
                >{firmware.version}</option
              >
            {/if}
          {/each}
        </optgroup><optgroup label="IXrouter2">
          {#each firmwareList as firmware}
            {#if firmware.version[0] == 2}
              <option on:click={selectVersionAndGetRouters} value={firmware}
                >{firmware.version}</option
              >
            {/if}
          {/each}
        </optgroup></select
      >
    </div>
    <button
      disabled={disableStartUpgrade}
      class="startUpgradeButton"
      class:narrowWidth={isNarrow}
      on:click={startFirmwareUpgrade}
      type="button"
    >
      {#if !isNarrow}
        {startUpgradeButtonText}
      {:else}
        {startUpgradeButtonTextShort}
      {/if}
    </button>
  </div>
</main>

<style>
  main {
    padding: 8px;
  }

  .componentHeader {
    display: flex;
    flex-direction: row;

    font-family: var(--font-family);
    height: 40px;
    box-sizing: border-box;
    white-space: nowrap;
    z-index: 1;
  }

  .componentTitle {
    flex: 1 0 auto;
    margin: 0;
    font-size: 14px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .componentLine {
    display: flex;
    justify-content: space-between;
  }

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

  .startUpgradeButton {
    cursor: pointer;
    float: right;
    width: 230px;
    height: 37px;
    background-color: var(--accent);
    color: var(--accent-color);
    font-size: 14px;
    text-align: center;
    border: none;
    border-radius: 4px;
    font-family: var(--font-family);
  }

  .startUpgradeButton:disabled {
    cursor: auto;
    background-color: rgba(0, 0, 0, 0.12);
    color: var(--body-color);
  }

  .narrowWidth {
    width: 200px;
  }
</style>
