<script lang="ts">
  import { api } from '$lib/api';

  let err = '';
  let submitting = false;

  async function accept() {
    err = '';
    submitting = true;
    try {
      await api.acceptTerms();
      window.location.href = '/';
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      submitting = false;
    }
  }
</script>

<section class="block">
  <h1 class="title is-3">Before you continue</h1>
  <p class="subtitle is-6">Please accept our Privacy Policy and Legal Terms.</p>

  <div class="box">
    <div class="content">
      <ul>
        <li><a href="/privacy">Privacy Policy</a> (stub)</li>
        <li><a href="/terms">Legal Terms</a> (stub)</li>
      </ul>
      <p class="has-text-grey is-size-7">
        We store your acceptance with your account identifier, the policy version date, your IP address, and a timestamp.
        If the policy version changes, you will be asked to accept again.
      </p>
    </div>

    {#if err}
      <article class="message is-danger" role="alert"><div class="message-body">{err}</div></article>
    {/if}

    <button class="button is-primary" type="button" on:click={accept} disabled={submitting}>
      {submitting ? 'Saving…' : 'I accept and continue'}
    </button>
  </div>
</section>
