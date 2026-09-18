# Existing JobNavigator bridge maintenance

These integration files maintain the existing installations; they are not a replacement bridge or a second queue.

- `identity-compat.patch` updates `/opt/jobnavigator-bridge/jobnavigator_bridge/engine.py`. It accepts an exact legacy canonical-URL identity with the same source/external ID, and retains the stage key when the execution URL has not changed. Existing receipts, attempts and source records remain intact.
- `test_identity_compat.py` belongs in the existing bridge's `tests/` directory and uses only its synthetic fixtures.
- `route-enrichment-api.patch` / `route_endpoint.txt` add an authenticated JobNavigator route update operation. Apply the patch to the existing source checkout; installations with mixed CRLF can append the endpoint text once after checking it is absent and backing up the original. The backend source on ZacTower is a persistent bind mount, so restart only the backend after it is idle.
- `resolve_routes.py` runs beside the existing bridge using its selected config and protected environment. It reads pending source records and normal role preferences, opens a new background target in JobBot's existing signed-in browser, and observes Apply controls. It never clicks Apply, opens forms, fills fields, exports cookies or submits applications. Exact posting-ID evidence is required by the existing route contract. An observed external destination or explicit Easy Apply updates the same JobNavigator row through its authenticated API. Unresolved records remain available for later passes.
- The user service/timer runs ten-record enrichment slices every fifteen minutes. A slice yields to an active application and closes only its own target. Its post-step invokes the existing bridge, including its durable intake/enqueue receipts. The existing system bridge timer remains unchanged. The personal LinkedIn collector stays inactive.
- Unseen matching roles are inspected first. An unavailable posting rotates behind unseen work instead of ending the entire slice. Role and location preferences are unchanged.

Use the existing authoritative Python `/home/rejo/apps/auto-job-applier-runtime/.venv/bin/python`. Resolver progress is private beside the bridge's configured state database, never in Git. The service imports the existing protected bridge environment without printing its values.

Source backups and test evidence for the September 18 repair are under the existing ignored deployment artifacts area. Preserve Ubuntu-only runtime overlays; do not replace its working tree with a Windows checkout.
