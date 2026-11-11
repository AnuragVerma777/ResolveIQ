# PayPal AI Toolkit in Codex on Windows

## Verified installation

The official [PayPal AI Toolkit repository](https://github.com/paypal/AI-Toolkit) documents this Codex workflow:

```powershell
codex plugin marketplace add paypal/AI-Toolkit
codex plugin add paypal@paypal-ai-toolkit
```

Both commands completed successfully in this environment. The plugin was installed at the Codex cache path under `%USERPROFILE%\.codex\plugins\cache\paypal-ai-toolkit\paypal\1.2.0`. The installed `.mcp.json` declares `paypal-sandbox` using SSE at `https://mcp.sandbox.paypal.com/sse` and the bearer token variable `PAYPAL_SANDBOX_ACCESS_TOKEN`.

The current Codex process has not loaded the server: `codex mcp list` reported no servers in this running session. The upstream README requires fully restarting Codex after installation. Restart the Codex desktop app before checking tools. Do not consider the MCP connection verified until its tools appear and a harmless read-only tool call succeeds.

## Credentials

Create or select a sandbox REST app in the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/applications/sandbox). The app's **sandbox client ID and client secret** are used only to request a sandbox OAuth access token. Configure the resulting **single-line access token** in Codex as `PAYPAL_SANDBOX_ACCESS_TOKEN`; do not put the client secret in the project, commit either credential, or paste credentials into chat.

The MCP server limits visible tools to those allowed by the token. For ResolveIQ's dispute use case, the sandbox token needs the PayPal dispute scopes available to the app, especially `disputes/read-seller` for reading seller disputes and `disputes/update-seller` for responding. Other tools require their matching API scopes (for example invoicing). PayPal controls which scopes an app receives; inspect the returned `scope` field without sharing the token. There is no separate plugin permission grant documented for Codex. Use sandbox credentials only; production credentials and production writes are outside this setup.

## Configure on Windows

1. In PayPal Developer Dashboard, open **Apps & Credentials → Sandbox**, create/select an app, and copy its sandbox client ID and secret.
2. Request an access token from PayPal's sandbox OAuth endpoint using the official README flow. In PowerShell, use `curl.exe` (not the PowerShell `curl` alias):

   ```powershell
   $clientId = Read-Host 'Sandbox client ID'
   $clientSecret = Read-Host 'Sandbox client secret' -AsSecureString
   $secretText = [System.Net.NetworkCredential]::new('', $clientSecret).Password
   $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${clientId}:${secretText}"))
   $result = Invoke-RestMethod -Method Post `
     -Uri 'https://api-m.sandbox.paypal.com/v1/oauth2/token' `
     -Headers @{ Authorization = "Basic $basic" } `
     -ContentType 'application/x-www-form-urlencoded' `
     -Body 'grant_type=client_credentials'
   $result.expires_in
   $result.access_token | Set-Clipboard
   Remove-Variable clientSecret, secretText, basic, result
   ```

   This copies the token to the clipboard without printing it. Paste it into the local Codex user config, `%USERPROFILE%\.codex\config.toml`, under the existing section (merge with existing settings; do not duplicate the table):

   ```toml
   [shell_environment_policy.set]
   PAYPAL_SANDBOX_ACCESS_TOKEN = "<paste the single-line sandbox access token>"
   ```

   Protect this user config as a secret. Do not place the token in the repository's `.env`, source files, or a committed config. The toolkit README documents this Codex config location and setting.
3. Fully quit and reopen Codex so the plugin MCP server receives the token.
4. In a new Codex session, inspect the available PayPal MCP tools and make a read-only call (for example, list invoices with page size 1). Avoid creating orders, sending invoices, refunding, or responding to disputes as a connectivity test.

## Setup and diagnostics

The upstream plugin's `/paypal:setup` and `/paypal:doctor` commands are described as slash commands for Claude Code and Cursor. The repository says Codex uses the same skills and MCP through natural language; it does not document those slash commands as Codex commands. In Codex, ask it to list PayPal MCP tools or invoke its setup skill after restart. The setup skill checks for loaded `paypal-sandbox` tools and suggests a lightweight invoice-list probe.

The official `codex plugin marketplace add` and `codex plugin add` commands were run and returned success. `codex plugin list`, `codex plugin marketplace list`, and `codex mcp list` in the same currently running session reported no marketplace plugins, no marketplace scope, and no MCP server. This is consistent with the README's restart requirement but means MCP tool connectivity has **not** yet been verified here. Re-run the list checks in a fresh Codex terminal/session after restarting the desktop app.

## Troubleshooting

- **No `paypal-sandbox` tools after restart:** confirm the plugin appears in Codex plugin settings and the token is under `[shell_environment_policy.set]`; fully quit/reopen Codex.
- **401 Unauthorized:** token may have expired (the README says up to eight hours depending on scope); generate a fresh sandbox token and restart Codex.
- **Invalid Authorization header:** ensure the token is one uninterrupted line with no quotes copied into the value, whitespace, or newline.
- **429:** stop retrying and wait briefly before probing again.
- **Connection or timeout errors:** check network/proxy access to `mcp.sandbox.paypal.com`.
- **Never diagnose connectivity by performing a financial write.** Use a read-only list operation first.

## Sources

- [PayPal AI Toolkit README](https://github.com/paypal/AI-Toolkit#readme)
- [PayPal MCP server quickstart](https://developer.paypal.com/ai-tools/mcp-server)
- [PayPal REST authentication and token scopes](https://developer.paypal.com/api/rest/authentication)
- Installed plugin manifest and `.mcp.json` in the Codex plugin cache (version 1.2.0).
