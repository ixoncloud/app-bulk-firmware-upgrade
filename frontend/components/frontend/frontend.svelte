<script>
  import { onMount } from "svelte";

  export let context;
  export let client;
  export let response;
  export let firmwareVersions = [];
  export let selectedFirmware;
  export let eligibleAgents;
  export let disableInstall = true;
  export let installButtonText = "Select a firmware version";
  export let disableFirmwareSelect = false;
  export let upgradesAllStarted = false;

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
    // {#if $eligibleAgents === '[]'}
    //   installButtonText = "No eligible devices found";
    //   disableInstall = false;
    // {/if}
    disableInstall = false;
    installButtonText = "Upgrade all devices";
  }
  async function installFirmware() {
    const response = await client.call("functions.installFirmware");
    upgradesAllStarted = response.data;
    // result = JSON.stringify(response, null, 2);
    disableInstall = true;
    disableFirmwareSelect = true;
    installButtonText = "Starting all upgrades";
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
