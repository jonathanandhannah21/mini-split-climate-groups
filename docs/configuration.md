# Configuration Guide

## Adding a Climate Group

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Mini Split Climate Groups"
4. Follow the configuration wizard

## Edge Cases Handled

### Initializing on Existing System
The integration detects the current state of your mini splits and initializes appropriately.

### Unavailable Climate Entities
If a climate entity becomes unavailable, the integration will:
- Log a warning
- Skip controlling that member
- Continue operating other members
- Auto-recover when entity becomes available

### Missing HVAC Modes
If a climate entity is missing cool/heat modes (Kumo bug), the integration will:
- Log the issue
- Only use available modes
- Suggest manual device registry fix in logs

## Troubleshooting

Check logs at Settings → System → Logs, filter by "mini_split_climate_groups"
