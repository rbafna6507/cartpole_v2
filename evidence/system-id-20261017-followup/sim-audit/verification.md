# Verification record

The new adapter and codec were developed with failing tests first. The initial
seven adapter tests failed because the adapter was absent; the shared-codec
tests failed before that module existed. Review reproduced two timing defects
(transport-age input unavailable on the real SDK, and an artificial fixed-phase
lease gap), and new failing tests preceded their fixes.

Final focused run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_rig_gym_env.py tests/test_host_policy.py \
  tests/test_control_observation.py tests/test_reference_parity.py \
  tests/test_tunable_motion.py
```

Result: **78 passed, 19 subtests passed, 6.57 s**. The adapter/codec file alone
has 15 passing tests. Native observer comparison is among these tests.

A separate reviewer ran the 15 tests plus three physical-diagnosis tests:
18 passed. Its source-pinned review is under the sibling `diagnosis` directory.
It replayed an actual preserved `Rig.control_observation()` snapshot through
both raw and filtered channel selections with exact codec agreement and zero
SDK age proxies. Timing combinations 0+0, 1+1, 3+3 and 9+0 ms telemetry+command
delay survived 30 decisions; 9+3 ms exhausted its anchored 20 ms lease as expected.

The complete project suite was also attempted in the restricted sandbox:
**14 failed, 1070 passed, 10 skipped, 390 subtests passed, 52.61 s**.
This is not a whole-suite success claim. One concurrently added training test
still expected all-dropout episodes to take zero steps; the now-explicit healthy
preflight snapshot allows one step before subsequent telemetry dropout. The
training agent was notified to update the expectation:

- `tests/test_model_training.py::test_observer_dropouts_fail_closed_without_using_truth_and_tamper_fails`

The other 13 failures were `PermissionError: [Errno 1] Operation not permitted`
on local `socket.bind` in the sandbox:

- `tests/test_portal_http.py::HTTPTests::test_auth_and_role_guards`
- `tests/test_portal_http.py::HTTPTests::test_cross_origin_browser_mutation_rejected`
- `tests/test_portal_http.py::HTTPTests::test_slow_body_progress_cannot_extend_absolute_request_budget`
- `tests/test_portal_http.py::HTTPTests::test_source_size_unknown_fields_and_path_rejected`
- `tests/test_portal_http.py::HTTPTests::test_submit_list_ownership_and_result`
- `tests/test_portal_http.py::HTTPTests::test_ui_is_public_but_does_not_embed_credentials`
- `tests/test_portal_http.py::HTTPTests::test_worker_claim_fetch_and_reset_before_start_contract`
- `tests/test_portal_worker.py::WorkerTests::test_outbound_http_worker_claim_fetch_and_finish_end_to_end`
- `tests/test_portal_worker.py::WorkerTests::test_remote_redirect_cannot_forward_bearer_to_another_origin`
- `tests/test_portal_worker.py::WorkerTests::test_remote_slow_response_cannot_extend_absolute_call_timeout`
- `tests/vision_runtime/test_comparison_process.py::ProcessTests::test_separate_process_tracks_without_camera_and_shuts_down`
- `tests/vision_runtime/test_encoder_feed.py::FeedTests::test_health_is_required_and_expires_even_if_telemetry_continues`
- `tests/vision_runtime/test_encoder_feed.py::FeedTests::test_real_udp_publisher_and_no_receiver`

No socket-bound test was rerun with wider permissions by this audit. No serial,
SSH, hardware command, or external network request was made.

`numerical_audit.py` reproduces the quantitative comparisons in `audit.md` and
prints JSON. Its saved output `numerical-audit.json` includes source hashes and
the final hardware parameter-report hash. It is offline analysis only.
