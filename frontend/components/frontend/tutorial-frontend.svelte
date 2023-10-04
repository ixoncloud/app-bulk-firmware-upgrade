<script>
  import { onMount } from "svelte";

  export let context;
  export let client;
  export let response;
  export let firmware_versions = [];
  export let selected_firmware;
  export let eligible_agents;

  onMount(async () => {
    client = context.createBackendComponentClient();
    response = await client.call("functions.getFirmwareVersions");
    firmware_versions = response.data;
  });

  async function getFirmwareVersions() {
    const response = await client.call("functions.getFirmwareVersions");
    result = JSON.stringify(response, null, 2);
  }
  async function selectVersionAndGetRouters() {
    const response = await client.call("functions.selectVersionAndGetRouters", {
      version: selected_firmware,
    });
    eligible_agents = JSON.stringify(response.data, null, 2);
  }
  async function installFirmware() {
    const response = await client.call("functions.installFirmware");
    result = JSON.stringify(response, null, 2);
  }
  function handleClick() {
    alert("no more alerts");
  }
</script>

<main>
  <form>
    <div>
      Select firmware:
      <select bind:value={selected_firmware}>
        {#each firmware_versions as firmware_version}
          <option on:click={selectVersionAndGetRouters} value={firmware_version}
            >{firmware_version}</option
          >
        {/each}
      </select>
      <button on:click={installFirmware} type="button"> Install </button>
    </div>
    <h1>Selected firmware: {selected_firmware}</h1>
    <br />
    <textarea bind:value={eligible_agents} rows="20" cols="120" />
    <h1>{JSON.stringify(response)}</h1>
    <button on:click|once={handleClick}> Click me </button>
  </form>
</main>
