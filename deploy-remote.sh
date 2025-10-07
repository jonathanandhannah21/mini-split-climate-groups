#!/bin/bash

# Deploy to remote Home Assistant
# Usage: ./deploy-remote.sh [hostname] [ssh-port]

HA_HOST="${1:-homeassistant.local}"
HA_SSH_PORT="${2:-22222}"

echo "Deploying to $HA_HOST:$HA_SSH_PORT..."

# Commit and push
git add -A
git commit -m "Development update $(date +%Y%m%d-%H%M%S)" || true
git push origin main || echo "Push failed or no remote configured"

# Deploy via SSH
ssh -p "$HA_SSH_PORT" root@"$HA_HOST" << 'ENDSSH'
cd /config

# Backup existing
if [ -d "custom_components/mini_split_climate_groups" ]; then
    mv custom_components/mini_split_climate_groups custom_components/mini_split_climate_groups.backup
fi

# Clone latest
git clone https://github.com/GITHUB_USER/mini-split-climate-groups.git temp-deploy
cp -r temp-deploy/custom_components/mini_split_climate_groups custom_components/
mkdir -p www/community
cp temp-deploy/www/mini-split-climate-card.js www/community/
rm -rf temp-deploy

echo "✓ Deployed! Restart Home Assistant to apply changes."
ENDSSH

echo ""
echo "Deployed successfully!"
echo "Now restart Home Assistant to apply changes."
