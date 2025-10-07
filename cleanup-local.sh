#!/bin/bash

HA_CONFIG="${HOME}/.homeassistant"

echo "Removing symlinks..."
rm -f "$HA_CONFIG/custom_components/mini_split_climate_groups"
rm -f "$HA_CONFIG/www/community/mini-split-climate-card.js"
echo "✓ Symlinks removed"
