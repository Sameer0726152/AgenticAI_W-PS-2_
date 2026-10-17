# Forwards GitHub webhook deliveries from your smee.io channel to the local backend.
#   .\scripts\start_tunnel.ps1 https://smee.io/YOUR_CHANNEL
# Keep this window open during the demo.
param([Parameter(Mandatory = $true)][string]$SmeeUrl)

# Trust the Windows certificate store (needed when antivirus inspects HTTPS).
$env:NODE_OPTIONS = "--use-system-ca"
npx --yes smee-client --url $SmeeUrl --target http://localhost:8000/api/webhooks/github
