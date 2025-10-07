#!/bin/bash

# Test script for local Home Assistant development
set -e

HA_CONFIG="${HOME}/.homeassistant"

if [ ! -d "$HA_CONFIG" ]; then
    echo "Error: Home Assistant config directory not found at $HA_CONFIG"
    exit 1
fi

echo "Creating symlinks for local testing..."

# Create directories if needed
mkdir -p "$HA_CONFIG/custom_components"
mkdir -p "$HA_CONFIG/www/community"

# Remove old symlinks
rm -f "$HA_CONFIG/custom_components/mini_split_climate_groups"
rm -f "$HA_CONFIG/www/community/mini-split-climate-card.js"

# Create new symlinks
ln -sf "$(pwd)/custom_components/mini_split_climate_groups" \
       "$HA_CONFIG/custom_components/mini_split_climate_groups"

ln -sf "$(pwd)/www/mini-split-climate-card.js" \
       "$HA_CONFIG/www/community/mini-split-climate-card.js"

echo "✓ Backend symlinked"
echo "✓ Frontend symlinked"
echo ""
echo "Next steps:"
echo "1. Restart Home Assistant"
echo "2. Check logs for any errors"
echo "3. Add integration via Settings → Integrations"
echo "4. Add card to dashboard"
