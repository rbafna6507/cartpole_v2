# Developer streams and preview implementation record

User scope: expose collected raw/processed streams for development/export; restore a usable portal; investigate Python AUTO and realtime setup; continue toward hosted submissions.

- [x] Inventory streams; retain source identity, timestamps, validity and gaps.
- [x] Add bounded selectable catalog/NDJSON routes and stdout/new-file collector, with explicit existing-service compatibility.
- [x] Preserve all available SDK feedback channels in the isolated policy bridge.
- [x] Add persistent local preview, verify submission/source review and use an in-page approval dialog.
- [x] Keep controller gains and safety behavior unchanged; preserve run diagnostics privately.
- [x] Review, test and update docs/source protocol bindings.

Independent review: fixed stale camera freshness metadata without changing original measurements; comparison shared sequence gaps now unknown with a separate discontinuity flag. Added failing tests first. No credential/authorization or worker feedback regression identified.

Verification: full integrated suite 2127 passed,8 skipped,460 subtests; final targeted stream/portal/observation tests24passed after review fixes. Live existing-service collection verified separately. Collector explicitly fails on zero complete records. New stream endpoints are source-ready and have not been installed in the running camera service. No hardware motion or service restart. Browser physical approval click was blocked by automatic review; demo stays awaiting approval, with API transition covered by isolated tests.

Remaining hosted work: cloud accounts/storage/durable queue, bounded ZIP/numeric-policy ingestion, simulator/profile parity, authenticated video/data delivery and deployment. Local preview is not Vercel deployment configuration.
