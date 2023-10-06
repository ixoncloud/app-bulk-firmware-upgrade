<script>
  import { onMount } from "svelte";

  export let context;

  let client;
  let response;

  let firmwareList = [];
  let selectedFirmware;
  let eligibleAgents;

  let disableFirmwareSelect = false;
  let disableStartUpgrade = true;
  let startUpgradeButtonText = "Select a firmware version";
  let upgradesAllStarted;

  onMount(async () => {
    client = context.createBackendComponentClient();
    response = await client.call("functions.getFirmwareVersions");
    firmwareList = response.data;
    console.log(firmwareList);
  });

  async function selectVersionAndGetRouters() {
    const response = await client.call("functions.selectVersionAndGetRouters", {
      firmware: selectedFirmware,
    });
    eligibleAgents = response.data;
    console.log(eligibleAgents);
    upgradesAllStarted = false; // Reset value
    if (eligibleAgents === "[]") {
      disableStartUpgrade = true;
      startUpgradeButtonText = "No eligible devices found";
    } else {
      disableStartUpgrade = false;
      startUpgradeButtonText = "Upgrade all eligible devices";
    }
  }
  async function startFirmwareUpgrade() {
    disableFirmwareSelect = true;
    disableStartUpgrade = true;
    startUpgradeButtonText = "Starting all device upgrades";
    const response = await client.call("functions.startFirmwareUpgrade", {
      firmware: selectedFirmware,
      agents: eligibleAgents,
    });
    upgradesAllStarted = response.data;
    // result = JSON.stringify(response, null, 2);
    if (upgradesAllStarted) {
      disableFirmwareSelect = false;
      disableStartUpgrade = true;
      startUpgradeButtonText = "All device upgrades started";
    }
  }
</script>

<main>
  <form>
    <div>
      Select firmware:
      <select disabled={disableFirmwareSelect} bind:value={selectedFirmware}>
        {#each firmwareList as firmware}
          <option on:click={selectVersionAndGetRouters} value={firmware}
            >{firmware.version}</option
          >
        {/each}
      </select>
      <button
        disabled={disableStartUpgrade}
        class="startUpgradeButton"
        on:click={startFirmwareUpgrade}
        type="button"
      >
        {startUpgradeButtonText}
      </button>
    </div>
  </form>
</main>

<style>
  main {
    padding: 0.6rem;
  }

  .startUpgradeButton {
    float: right;
    width: 200px;
  }
</style>
