<script>
  import { onMount } from "svelte";

  export let context;

  let client;
  let response;

  let firmwareVersions = [];
  let selectedFirmware;
  let eligibleAgents;

  let disableFirmwareSelect = false;
  let disableInstall = true;
  let installButtonText = "Select a firmware version";
  let upgradesAllStarted;

  onMount(async () => {
    client = context.createBackendComponentClient();
    response = await client.call("functions.getFirmwareVersions");
    firmwareVersions = response.data;
  });

  async function getFirmwareVersions() {
    const response = await client.call("functions.getFirmwareVersions");
    result = JSON.stringify(response, null, 2);
  }
  async function selectVersionAndGetRouters() {
    const response = await client.call("functions.selectVersionAndGetRouters", {
      version: selectedFirmware,
    });
    upgradesAllStarted = false;
    eligibleAgents = JSON.stringify(response.data, null, 2);
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
    const response = await client.call("functions.installFirmware");
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
        {#each firmwareVersions as firmwareVersion}
          <option on:click={selectVersionAndGetRouters} value={firmwareVersion}
            >{firmwareVersion}</option
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
    <h1>Selected firmware: {selectedFirmware}</h1>
    <br />
    <textarea bind:value={eligibleAgents} rows="20" cols="120" />
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
