<script>
  import { onMount } from "svelte";

  export let context;

  let client;
  let response;

  let firmwareList = [];
  let selectedFirmware;
  let selectedFirmware_string;
  let eligibleAgents;
  let eligibleAgents_string;

  let disableFirmwareSelect = false;
  let disableInstall = true;
  let installButtonText = "Select a firmware version";
  let upgradesAllStarted;

  onMount(async () => {
    client = context.createBackendComponentClient();
    response = await client.call("functions.getFirmwareVersions");
    firmwareList = response.data;
  });

  async function selectVersionAndGetRouters() {
    const response = await client.call("functions.selectVersionAndGetRouters", {
      firmware: selectedFirmware,
    });
    eligibleAgents = response.data;
    eligibleAgents_string = JSON.stringify(response.data, null, 2);
    selectedFirmware_string = JSON.stringify(selectedFirmware, null, 2);
    upgradesAllStarted = false; // Reset value
    if (eligibleAgents === "[]") {
      disableInstall = true;
      installButtonText = "No eligible devices found";
    } else {
      disableInstall = false;
      installButtonText = "Upgrade all eligible devices";
    }
  }
  async function installFirmware() {
    disableFirmwareSelect = true;
    disableInstall = true;
    installButtonText = "Starting all device upgrades";
    const response = await client.call("functions.installFirmware", {
      firmware: selectedFirmware,
      agents: eligibleAgents,
    });
    upgradesAllStarted = response.data;
    // result = JSON.stringify(response, null, 2);
    if (upgradesAllStarted) {
      disableFirmwareSelect = false;
      disableInstall = true;
      installButtonText = "All device upgrades started";
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
        disabled={disableInstall}
        class="installButton"
        on:click={installFirmware}
        type="button"
      >
        {installButtonText}
      </button>
    </div>
    <p>Disabled: {disableInstall}</p>
    <p>Response: {upgradesAllStarted}</p>
    <h1>Selected firmware: {selectedFirmware_string}</h1>
    <br />
    <textarea bind:value={eligibleAgents_string} rows="10" cols="100" />
    <h1>{JSON.stringify(response)}</h1>
  </form>
</main>

<style>
  main {
    padding: 0.6rem;
  }

  /* div {
    display: inline;
  } */

  .installButton {
    float: right;
    width: 200px;
  }
</style>
