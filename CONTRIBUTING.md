# Contributing

Run `python3 -m unittest discover -s tests -v` for config/checker tests. On macOS,
also build and render the popup before submitting a UI change. Keep the native
size, first-click handling, persistent/nonactivating behavior, and synchronized
sounds intact. Video changes should be checked at small feed size as well as at
full resolution.

Please separate code changes from media additions and record provenance and
licensing for new media. Do not commit credentials, personal runtime JSON, profile
caches, background screenshots, or private task links. The existing named roster
is a demo; do not represent simulated checks as real users accepting.

Meeting/calendar adapters and genuine shared ready checks are possible future
work, not current functionality. Keep any new network/identity integration
explicit and opt-in.
