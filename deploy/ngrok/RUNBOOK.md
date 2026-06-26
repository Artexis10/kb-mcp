# ngrok — kb-mcp ingress setup (no domain needed)

Per-machine playbook for putting kb-mcp behind **ngrok** — the **no-domain**,
burst-tolerant alternative to [Cloudflare Tunnel](../cloudflared/RUNBOOK.md). Use
this when you want claude.ai web/mobile access but **don't own (and won't buy) a
domain**. The server code is unchanged — the public URL is env-driven via
`KB_MCP_BASE_URL`; this is purely ingress + `.env` + GitHub OAuth App + the
claude.ai connector.

> **Why ngrok and not Tailscale Funnel?** claude.ai's connector re-authenticates
> in bursts (`/.well-known` → `register` → `authorize` → `token`). Tailscale
> Funnel's shared relay throttles that burst and silently drops it — the "connector
> keeps dropping" complaint. ngrok's free tier allows 4,000 req/min, so the ~5
> request OAuth burst sails through. The trade is ngrok's free-tier caveats (below),
> not burst drops.
>
> **Want the bulletproof path instead?** Cloudflare Tunnel (own a domain) has no
> request cap and no interstitial — see [../cloudflared/RUNBOOK.md](../cloudflared/RUNBOOK.md).
> A domain is ~$1–12/yr; put it on Cloudflare's free plan, switch nameservers, done.

## Caveats — read before you commit (free tier)

- **One-time login interstitial.** On the free tier, the *first* time a browser
  hits your ngrok host it shows a "Visit Site" warning page. This fires **once** on
  the GitHub-login redirect (`/authorize` opens in your browser), you click through,
  and a cookie suppresses it for ~7 days. It does **not** affect claude.ai's own
  API/OAuth calls — ngrok exempts programmatic traffic from the interstitial.
- **20,000 requests/month cap** (and 4,000/min). Fine for light personal use; a
  ceiling under heavy use or connector reconnect churn. If you outgrow it, move to
  Cloudflare or a paid ngrok plan.
- **Not yet battle-tested against claude.ai end-to-end by us** (Cloudflare is). The
  mechanism is sound; if something snags, it'll be the interstitial on the login
  redirect — fall back to the cloudflared runbook.

Substitute throughout:
- `<HOST>` = your reserved ngrok domain, e.g. `kb-yourname.ngrok-free.dev`
  (newer accounts; older accounts get `*.ngrok-free.app` — both work).

## Prereqs
- An ngrok account (free) — <https://dashboard.ngrok.com>.
- ngrok agent installed: `winget install --id Ngrok.Ngrok` (Windows) /
  `brew install ngrok` (macOS) / see <https://ngrok.com/download> (Linux).
- kb-mcp already installed and running as a service on `127.0.0.1:8765` (see the
  main [README](../../README.md) for the service install).

## Steps — order matters

1. **Authenticate the agent** (token from dashboard → *Your Authtoken*):
   ```
   ngrok config add-authtoken <YOUR_TOKEN>
   ```
2. **Reserve your free dev domain.** Dashboard → **Domains** → you get one free
   static domain like `kb-yourname.ngrok-free.dev`. This is **stable across
   restarts** (reserved to your account) — which is what makes OAuth work; the
   ephemeral `ngrok http 8765` URL would change every restart and break the
   callback. Copy it; that's your `<HOST>`.
3. **Smoke-test in the foreground** (Ctrl-C when you've confirmed it serves):
   ```
   ngrok http --url=https://<HOST> 8765
   ```
   > Older agents use `--domain=<HOST>` instead of `--url=https://<HOST>`.

   Then from another machine/phone: `https://<HOST>/mcp` should return **401**
   (healthy — the auth funnel).
4. **Run it as a persistent service** so it survives reboots/logout. Create an
   `ngrok.yml` next to your kb-mcp checkout:
   ```yaml
   version: "2"
   authtoken: <YOUR_TOKEN>
   tunnels:
     kb-mcp:
       proto: http
       addr: 8765
       domain: <HOST>
   ```
   Install + start the service (cross-platform: Windows service / systemd / launchd):
   ```
   ngrok service install --config <full-path-to>/ngrok.yml
   ngrok service start
   ```
   (See <https://ngrok.com/docs/agent/> for per-OS service details.)
5. **GitHub OAuth App** — edit *this host's* app (the one whose Client ID matches
   `GITHUB_CLIENT_ID` in this machine's `.env`) at
   <https://github.com/settings/developers>:
   - Homepage URL → `https://<HOST>`
   - Authorization callback URL → `https://<HOST>/auth/callback`
   - **Update application** (fields aren't saved until you click it).
6. **Point the server at `<HOST>`** and restart so it reloads:
   ```
   (Get-Content .env) -replace '^KB_MCP_BASE_URL=.*','KB_MCP_BASE_URL=https://<HOST>' | Set-Content .env   # Windows
   pwsh -File scripts/restart.ps1
   ```
   (macOS/Linux: set `KB_MCP_BASE_URL=https://<HOST>` in `.env`, then restart the
   service per the README.)
   > **CRITICAL:** steps 5 and 6 must *both* point at `<HOST>` before step 7. If the
   > GitHub app and the server's base URL disagree, GitHub rejects the login with
   > "The redirect_uri is not associated with this application."
7. **claude.ai** → Connectors → add at `https://<HOST>/mcp` → complete the GitHub
   login (click through the one-time ngrok "Visit Site" page if it appears). Remove
   any old `*.ts.net` connector once verified.

## Verify
- Local: `curl.exe -i http://127.0.0.1:8765/mcp` → **401**.
- Public base URL — must now show `<HOST>` (proves the `.env` cutover took). From
  off-host (another machine/phone, not the server itself):
  ```
  curl -s https://<HOST>/.well-known/oauth-protected-resource
  ```
  → `{"resource":"https://<HOST>/mcp","authorization_servers":["https://<HOST>/"], ...}`
- claude.ai: connector connected, tools listed, a `find` returns results.
- Reboot: the ngrok service and kb-mcp both auto-start and the connector still works.

## Gotchas
- **Ephemeral vs reserved URL.** Only the *reserved* dev domain (step 2) is stable.
  If you ever run a bare `ngrok http 8765`, it mints a random URL that won't match
  your OAuth callback — always pass your `<HOST>`.
- **Interstitial during login.** If GitHub login stalls on an ngrok warning page,
  click **Visit Site** once; the cookie suppresses it for ~7 days. If it ever blocks
  the *API* path (it shouldn't — programmatic traffic is exempt), you've outgrown the
  free tier; switch to Cloudflare or upgrade ngrok.
- **Hit the 20k/month cap?** That's the free-tier ceiling, not a kb-mcp bug. Move to
  the [Cloudflare path](../cloudflared/RUNBOOK.md) or a paid ngrok plan.

## Rollback
- `.env`: `KB_MCP_BASE_URL` back to the previous public URL; `pwsh -File scripts/restart.ps1`.
- GitHub OAuth App callback back to the previous `https://<old-host>/auth/callback`.
- claude.ai connector back to the previous `https://<old-host>/mcp`.
- `ngrok service stop` (or `ngrok service uninstall`) to retire the tunnel.
