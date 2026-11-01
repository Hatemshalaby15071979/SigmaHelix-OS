# Simulated Tenant Data — G-12

## Accepted Substitutes
Both datasets accepted as real-client substitute for testing and chaos-proof validation:

### 1. callcenterclient
- **Path**: `External tenant data/callcenterclient/`
- **Purpose**: Call center simulation data for chaos testing
- **Features**: customer interactions, call records, agent performance metrics
- **Status**: accepted substitute — no live client needed

### 2. sportacademyclient
- **Path**: `External tenant data/sportacademyclient/`
- **Purpose**: Sports academy simulation data for chaos testing
- **Features**: class bookings, membership data, attendance records, facility utilization
- **Status**: accepted substitute — no live client needed

## Integration Notes
- Both datasets are **simulated** — no external API calls
- Truth freeze executed 2026-10-23 — all data labeled simulated
- External access disabled per truth freeze
- Used for: chaos-proof testing, governance validation, demo purposes only
- Not connected to any live service or external system

## Chaos-Proof Testing
- Simulated data used to test Company OS features
- Voice input/output tested against simulated tenant scenarios
- Project monitoring tested with simulated call center and sports academy data
- No live drill performed (tabletop only per G-5)

## Status
- Simulated tenant data: **accepted as real-client substitute** — **complete**
- callcenterclient: **accepted**
- sportacademyclient: **accepted**
- External dependency: **zero** — fully local