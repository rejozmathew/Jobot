# Stop-condition source catalog

Companion to [STOP_CONDITION_AUDIT.md](STOP_CONDITION_AUDIT.md). This is an index of explicit exception messages and named return reasons, **not a count of application shutdowns**.

Source snapshot: `0d2a75118b9ea6771f1fd811433cecf161eca6a24e46a571fef234e19c642196`. Scanned 62 Python/JavaScript files directly under `job_applier/` and `job_applier/browser_helpers/`. Found 743 named sites, 551 distinct labels and 49 nonliteral/argument-free raise expressions. Includes embedded JavaScript. Administrative and retired paths are intentionally identified separately.

The review disposition for every row is in its linked family. Classification is based on the code and caller review; similarly named errors can appear at more than one boundary. A result reason may describe ordinary progress. This catalog does not invent an error label for silent Boolean rejection, unlabelled status transitions, operating-system failures or employer validation; those are covered in the main audit. Dynamic expressions and status outputs are indexed below.

Regeneration uses the ignored audit script in `artifacts/jobbot-v1-private/stop-audit/`; private history evidence stays there. Source links include the line from this snapshot and may move after implementation.

## G01

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g01).

| Message or reason | Source sites and kind |
|---|---|
| `driver_owned_elsewhere` | [application_runtime.py:227](../../job_applier/application_runtime.py#L227) (raise); [managed_sessions.py:118](../../job_applier/managed_sessions.py#L118) (raise); [workspace_host.py:272](../../job_applier/workspace_host.py#L272) (raise) |
| `driver_required` | [managed_sessions.py:241](../../job_applier/managed_sessions.py#L241) (raise) |
| `driver_session_required` | [application_runtime.py:89](../../job_applier/application_runtime.py#L89) (raise) |
| `fast_runner_already_owned_or_crash_lock` | [workday_fast.py:373](../../job_applier/workday_fast.py#L373) (raise) |
| `host_lock_missing` | [workspace_host.py:51](../../job_applier/workspace_host.py#L51) (raise) |
| `local_request_context_required` | [managed_sessions.py:49](../../job_applier/managed_sessions.py#L49) (raise) |
| `local_session_requires_start` | [managed.py:325](../../job_applier/managed.py#L325) (raise) |
| `local_session_transport_required` | [managed_sessions.py:156](../../job_applier/managed_sessions.py#L156) (raise) |
| `local_workspace_requires_session` | [managed_sessions.py:162](../../job_applier/managed_sessions.py#L162) (raise) |
| `owned_attempt_required` | [workday_fast.py:350](../../job_applier/workday_fast.py#L350) (raise) |
| `owned_elsewhere` | [managed.py:232](../../job_applier/managed.py#L232) (raise); [managed.py:236](../../job_applier/managed.py#L236) (raise); [managed.py:310](../../job_applier/managed.py#L310) (raise); [managed.py:328](../../job_applier/managed.py#L328) (raise); [managed.py:335](../../job_applier/managed.py#L335) (raise); [managed.py:343](../../job_applier/managed.py#L343) (raise); [managed_continuity.py:34](../../job_applier/managed_continuity.py#L34) (raise); [managed_events.py:156](../../job_applier/managed_events.py#L156) (raise); [managed_sessions.py:63](../../job_applier/managed_sessions.py#L63) (raise) |
| `session_resolves_ownership` | [workspace_host.py:310](../../job_applier/workspace_host.py#L310) (raise) |
| `stale_host` | [managed_sessions.py:172](../../job_applier/managed_sessions.py#L172) (raise); [managed_sessions.py:182](../../job_applier/managed_sessions.py#L182) (raise) |
| `stale_owner` | [managed.py:366](../../job_applier/managed.py#L366) (raise); [managed.py:375](../../job_applier/managed.py#L375) (raise); [managed_events.py:24](../../job_applier/managed_events.py#L24) (raise); [managed_events.py:101](../../job_applier/managed_events.py#L101) (raise); [workday_fast.py:356](../../job_applier/workday_fast.py#L356) (raise) |
| `stale_session` | [managed_continuity.py:15](../../job_applier/managed_continuity.py#L15) (raise) |
| `target_not_owned` | [managed_runtime.py:70](../../job_applier/managed_runtime.py#L70) (raise); [managed_runtime.py:98](../../job_applier/managed_runtime.py#L98) (raise); [managed_runtime.py:114](../../job_applier/managed_runtime.py#L114) (raise); [managed_runtime.py:130](../../job_applier/managed_runtime.py#L130) (raise) |
| `target_owned_elsewhere` | [managed_runtime.py:82](../../job_applier/managed_runtime.py#L82) (raise) |
| `worker_identity_mismatch` | [managed_api.py:137](../../job_applier/managed_api.py#L137) (result) |
| `worker_identity_required` | [managed.py:311](../../job_applier/managed.py#L311) (raise); [managed_api.py:139](../../job_applier/managed_api.py#L139) (result) |
| `worker_session_required` | [hermes_plugin.py:117](../../job_applier/hermes_plugin.py#L117) (raise) |
| `workspace_endpoint_mismatch` | [managed_runtime.py:112](../../job_applier/managed_runtime.py#L112) (raise) |
| `workspace_mismatch` | [workspace_host.py:271](../../job_applier/workspace_host.py#L271) (raise) |
| `workspace_owned_by_another_host` | [workspace_host.py:56](../../job_applier/workspace_host.py#L56) (raise) |

## G02

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g02).

| Message or reason | Source sites and kind |
|---|---|
| `browser_profile_mismatch` | [workspace_host.py:170](../../job_applier/workspace_host.py#L170) (raise) |
| `conflicting_target_options` | [cdp_client.py:477](../../job_applier/cdp_client.py#L477) (raise) |
| `explicit_loopback_cdp_required` | [application_runtime.py:48](../../job_applier/application_runtime.py#L48) (raise); [application_runtime.py:500](../../job_applier/application_runtime.py#L500) (raise); [workday_fast.py:363](../../job_applier/workday_fast.py#L363) (raise) |
| `invalid_browser_profile` | [managed.py:276](../../job_applier/managed.py#L276) (raise) |
| `loopback_host_required` | [managed_api.py:39](../../job_applier/managed_api.py#L39) (result) |
| `loopback_url_required` | [managed_client.py:11](../../job_applier/managed_client.py#L11) (raise) |
| `orphan_browser_still_running` | [workspace_host.py:353](../../job_applier/workspace_host.py#L353) (raise) |
| `owned_browser_still_alive` | [workspace_host.py:55](../../job_applier/workspace_host.py#L55) (raise) |
| `owned_target_not_found` | [cdp_client.py:491](../../job_applier/cdp_client.py#L491) (raise) |
| `owned_target_requires_loopback_cdp` | [cdp_client.py:482](../../job_applier/cdp_client.py#L482) (raise); [managed_runtime.py:121](../../job_applier/managed_runtime.py#L121) (raise) |
| `unsafe_owned_debugger_url` | [cdp_client.py:516](../../job_applier/cdp_client.py#L516) (raise) |
| `workspace_alias_conflict` | [managed_sessions.py:42](../../job_applier/managed_sessions.py#L42) (raise) |
| `workspace_configuration_in_use` | [managed_sessions.py:36](../../job_applier/managed_sessions.py#L36) (raise) |
| `workspace_endpoint_already_in_use` | [workspace_host.py:148](../../job_applier/workspace_host.py#L148) (raise) |
| `workspace_isolation_required` | [application_runtime.py:51](../../job_applier/application_runtime.py#L51) (raise); [application_runtime.py:53](../../job_applier/application_runtime.py#L53) (raise) |
| `workspace_process_inventory_unavailable` | [workspace_host.py:107](../../job_applier/workspace_host.py#L107) (raise) |
| `workspace_profile_already_in_use` | [workspace_host.py:149](../../job_applier/workspace_host.py#L149) (raise) |
| `workspace_profile_not_prepared` | [workspace_host.py:145](../../job_applier/workspace_host.py#L145) (raise) |
| `workspace_still_occupied` | [workspace_host.py:274](../../job_applier/workspace_host.py#L274) (raise) |

## G03

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g03).

| Message or reason | Source sites and kind |
|---|---|
| `application_frame_redirect_unverified` | [browser_frames.py:198](../../job_applier/browser_frames.py#L198) (result) |
| `application_target_not_ready` | [workspace_host.py:194](../../job_applier/workspace_host.py#L194) (raise) |
| `credential_target_scope_mismatch` | [managed_credentials.py:129](../../job_applier/managed_credentials.py#L129) (result) |
| `frame_parent_job_changed` | [browser_frames.py:76](../../job_applier/browser_frames.py#L76) (raise) |
| `invalid_job_url` | [managed_identity.py:11](../../job_applier/managed_identity.py#L11) (raise) |
| `sensitive_url` | [managed_identity.py:13](../../job_applier/managed_identity.py#L13) (raise); [managed_identity.py:16](../../job_applier/managed_identity.py#L16) (raise) |
| `target_job_mismatch` | [application_runtime.py:277](../../job_applier/application_runtime.py#L277) (raise); [application_runtime.py:338](../../job_applier/application_runtime.py#L338) (raise); [managed_runtime.py:79](../../job_applier/managed_runtime.py#L79) (raise); [managed_runtime.py:134](../../job_applier/managed_runtime.py#L134) (raise); [managed_runtime.py:146](../../job_applier/managed_runtime.py#L146) (raise); [submission.py:79](../../job_applier/submission.py#L79) (raise) |
| `target_scope_changed` | [workday_fast.py:66](../../job_applier/workday_fast.py#L66) (raise) |

## G04

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g04).

| Message or reason | Source sites and kind |
|---|---|
| `answer_history_scope_mismatch` | [application_answers.py:26](../../job_applier/application_answers.py#L26) (raise) |
| `asset_identity_mismatch` | [managed_documents.py:58](../../job_applier/managed_documents.py#L58) (raise); [managed_documents.py:61](../../job_applier/managed_documents.py#L61) (raise); [managed_documents.py:72](../../job_applier/managed_documents.py#L72) (raise); [managed_documents.py:91](../../job_applier/managed_documents.py#L91) (raise); [managed_sessions.py:71](../../job_applier/managed_sessions.py#L71) (raise) |
| `attempt_forbidden` | [managed_api.py:141](../../job_applier/managed_api.py#L141) (result); [managed_context.py:19](../../job_applier/managed_context.py#L19) (raise); [managed_questions.py:101](../../job_applier/managed_questions.py#L101) (raise); [managed_reports.py:34](../../job_applier/managed_reports.py#L34) (raise) |
| `candidate_credential_identity_mismatch` | [managed_credentials.py:117](../../job_applier/managed_credentials.py#L117) (raise) |
| `candidate_email_mismatch` | [workday_auth.py:89](../../job_applier/workday_auth.py#L89) (handoff); [workday_fast.py:206](../../job_applier/workday_fast.py#L206) (handoff) |
| `context_forbidden` | [managed_api.py:150](../../job_applier/managed_api.py#L150) (result); [workspace_host.py:316](../../job_applier/workspace_host.py#L316) (raise); [workspace_host.py:319](../../job_applier/workspace_host.py#L319) (raise) |
| `identity_immutable` | [managed.py:170](../../job_applier/managed.py#L170) (raise) |
| `invalid_question_context` | [managed_questions.py:42](../../job_applier/managed_questions.py#L42) (raise); [managed_questions.py:43](../../job_applier/managed_questions.py#L43) (raise) |
| `question_context_mismatch` | [application_runtime.py:203](../../job_applier/application_runtime.py#L203) (raise); [hermes_plugin.py:267](../../job_applier/hermes_plugin.py#L267) (raise); [managed_questions.py:163](../../job_applier/managed_questions.py#L163) (raise) |
| `wrong_attempt` | [managed_events.py:103](../../job_applier/managed_events.py#L103) (raise) |

## G05

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g05).

| Message or reason | Source sites and kind |
|---|---|
| `account_namespace_reconciliation_required` | [managed_accounts.py:56](../../job_applier/managed_accounts.py#L56) (raise) |
| `already_applied` | [managed.py:227](../../job_applier/managed.py#L227) (raise); [managed.py:451](../../job_applier/managed.py#L451) (raise) |
| `employer_row_already_submitted` | [workday_fast.py:195](../../job_applier/workday_fast.py#L195) (handoff) |
| `history_unavailable` | [application_runtime.py:448](../../job_applier/application_runtime.py#L448) (raise); [application_runtime.py:479](../../job_applier/application_runtime.py#L479) (raise) |
| `identity_conflict` | [managed.py:142](../../job_applier/managed.py#L142) (raise) |
| `legacy_account_reconciliation_required` | [managed_accounts.py:113](../../job_applier/managed_accounts.py#L113) (raise) |
| `legacy_history_suppression` | [application_runtime.py:120](../../job_applier/application_runtime.py#L120) (raise); [application_runtime.py:126](../../job_applier/application_runtime.py#L126) (raise); [workday_fast.py:358](../../job_applier/workday_fast.py#L358) (result) |
| `newer_attempt_exists` | [managed.py:449](../../job_applier/managed.py#L449) (raise) |
| `not_retryable` | [managed.py:476](../../job_applier/managed.py#L476) (raise); [managed_questions.py:202](../../job_applier/managed_questions.py#L202) (raise) |
| `protected_job` | [managed.py:221](../../job_applier/managed.py#L221) (raise) |
| `reconciliation_required` | [managed.py:235](../../job_applier/managed.py#L235) (raise); [managed.py:237](../../job_applier/managed.py#L237) (raise); [managed.py:250](../../job_applier/managed.py#L250) (raise); [managed.py:334](../../job_applier/managed.py#L334) (raise); [managed.py:376](../../job_applier/managed.py#L376) (raise); [managed.py:399](../../job_applier/managed.py#L399) (raise); [managed.py:475](../../job_applier/managed.py#L475) (raise); [managed.py:477](../../job_applier/managed.py#L477) (raise); [managed_accounts.py:107](../../job_applier/managed_accounts.py#L107) (raise); [managed_continuity.py:22](../../job_applier/managed_continuity.py#L22) (raise); [managed_continuity.py:39](../../job_applier/managed_continuity.py#L39) (raise); [managed_continuity.py:40](../../job_applier/managed_continuity.py#L40) (raise); [managed_questions.py:200](../../job_applier/managed_questions.py#L200) (raise) |

## G06

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g06).

| Message or reason | Source sites and kind |
|---|---|
| `browser_endpoint_not_ready` | [workspace_host.py:163](../../job_applier/workspace_host.py#L163) (raise) |
| `company_excluded` | [managed.py:243](../../job_applier/managed.py#L243) (raise) |
| `development_submission_disabled` | [managed.py:70](../../job_applier/managed.py#L70) (raise); [managed_settings.py:30](../../job_applier/managed_settings.py#L30) (raise) |
| `identity_inactive` | [managed.py:265](../../job_applier/managed.py#L265) (raise); [managed.py:345](../../job_applier/managed.py#L345) (raise); [managed_accounts.py:129](../../job_applier/managed_accounts.py#L129) (result); [managed_sessions.py:67](../../job_applier/managed_sessions.py#L67) (raise) |
| `job_archived` | [managed.py:248](../../job_applier/managed.py#L248) (raise); [managed_questions.py:203](../../job_applier/managed_questions.py#L203) (raise) |
| `market_incompatible` | [managed.py:246](../../job_applier/managed.py#L246) (raise) |
| `not_ready` | [managed.py:251](../../job_applier/managed.py#L251) (raise) |
| `submission_not_authorized` | [managed.py:398](../../job_applier/managed.py#L398) (raise); [workday_fast.py:290](../../job_applier/workday_fast.py#L290) (handoff) |

## G07

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g07).

| Message or reason | Source sites and kind |
|---|---|
| `absolute_config_path_required` | [managed_cli.py:12](../../job_applier/managed_cli.py#L12) (raise) |
| `absolute_database_required` | [application_runtime.py:485](../../job_applier/application_runtime.py#L485) (raise) |
| `absolute_db_path_required` | [managed.py:45](../../job_applier/managed.py#L45) (raise); [managed.py:60](../../job_applier/managed.py#L60) (raise); [managed_cli.py:17](../../job_applier/managed_cli.py#L17) (raise) |
| `absolute_existing_config_required` | [application_runtime.py:440](../../job_applier/application_runtime.py#L440) (raise) |
| `absolute_outbox_path_required` | [hermes_plugin.py:42](../../job_applier/hermes_plugin.py#L42) (raise) |
| `absolute_spool_required` | [application_answers.py:17](../../job_applier/application_answers.py#L17) (raise); [application_runtime.py:317](../../job_applier/application_runtime.py#L317) (raise); [workday_fast.py:366](../../job_applier/workday_fast.py#L366) (raise) |
| `absolute_workspace_paths_required` | [application_runtime.py:45](../../job_applier/application_runtime.py#L45) (raise) |
| `application_runtime_model_mismatch` | [application_runtime.py:141](../../job_applier/application_runtime.py#L141) (raise) |
| `autofill_capability_unavailable` | [managed_settings.py:47](../../job_applier/managed_settings.py#L47) (raise) |
| `browser_executable_missing` | [workspace_host.py:144](../../job_applier/workspace_host.py#L144) (raise) |
| `browser_mode_mismatch` | [managed_settings.py:53](../../job_applier/managed_settings.py#L53) (raise); [workspace_host.py:172](../../job_applier/workspace_host.py#L172) (raise) |
| `browser_mode_mismatch: headed browser cannot satisfy headless request` | [cdp_client.py:471](../../job_applier/cdp_client.py#L471) (raise) |
| `config_not_found` | [managed_cli.py:13](../../job_applier/managed_cli.py#L13) (raise) |
| `configuration_or_data_error` | [managed_cli.py:109](../../job_applier/managed_cli.py#L109) (result) |
| `configured_candidate_and_resume_required` | [application_runtime.py:128](../../job_applier/application_runtime.py#L128) (raise) |
| `configured_credentials_unavailable` | [managed_credentials.py:112](../../job_applier/managed_credentials.py#L112) (raise); [workday_auth.py:203](../../job_applier/workday_auth.py#L203) (handoff) |
| `configured_resume_required` | [managed_sessions.py:68](../../job_applier/managed_sessions.py#L68) (raise) |
| `configured_workspace_pool_required` | [application_runtime.py:38](../../job_applier/application_runtime.py#L38) (raise) |
| `credential_unavailable` | [managed_cli.py:27](../../job_applier/managed_cli.py#L27) (raise); [managed_cli.py:40](../../job_applier/managed_cli.py#L40) (raise) |
| `explicit_managed_instance_required` | [application_runtime.py:33](../../job_applier/application_runtime.py#L33) (raise) |
| `headless browser cannot satisfy headed request` | [cdp_client.py:469](../../job_applier/cdp_client.py#L469) (raise) |
| `incomplete_reasoning_selection` | [managed_settings.py:37](../../job_applier/managed_settings.py#L37) (raise) |
| `instance_mismatch` | [application_runtime.py:67](../../job_applier/application_runtime.py#L67) (raise); [application_runtime.py:488](../../job_applier/application_runtime.py#L488) (raise); [hermes_plugin.py:131](../../job_applier/hermes_plugin.py#L131) (raise); [managed.py:52](../../job_applier/managed.py#L52) (raise); [managed_api.py:58](../../job_applier/managed_api.py#L58) (result); [workspace_host.py:269](../../job_applier/workspace_host.py#L269) (raise) |
| `instance_not_initialized` | [managed.py:46](../../job_applier/managed.py#L46) (raise); [managed.py:51](../../job_applier/managed.py#L51) (raise) |
| `integration_not_configured` | [hermes_plugin.py:33](../../job_applier/hermes_plugin.py#L33) (raise); [hermes_plugin.py:35](../../job_applier/hermes_plugin.py#L35) (raise); [hermes_plugin.py:36](../../job_applier/hermes_plugin.py#L36) (raise); [hermes_plugin.py:41](../../job_applier/hermes_plugin.py#L41) (raise) |
| `invalid_browser_mode` | [application_runtime.py:49](../../job_applier/application_runtime.py#L49) (raise) |
| `invalid_concurrency_limit` | [application_runtime.py:144](../../job_applier/application_runtime.py#L144) (raise) |
| `invalid_config` | [application_runtime.py:442](../../job_applier/application_runtime.py#L442) (raise); [managed_cli.py:16](../../job_applier/managed_cli.py#L16) (raise) |
| `invalid_history_paths` | [application_runtime.py:494](../../job_applier/application_runtime.py#L494) (raise) |
| `invalid_maximum_runtime` | [application_runtime.py:118](../../job_applier/application_runtime.py#L118) (raise) |
| `invalid_reasoning_selection` | [managed_settings.py:36](../../job_applier/managed_settings.py#L36) (raise) |
| `invalid_workspace_id` | [application_runtime.py:42](../../job_applier/application_runtime.py#L42) (raise) |
| `migration_backup_invalid` | [application_runtime.py:79](../../job_applier/application_runtime.py#L79) (raise) |
| `official_simplify_required` | [application_runtime.py:115](../../job_applier/application_runtime.py#L115) (raise) |
| `primary_is_not_legacy` | [application_runtime.py:495](../../job_applier/application_runtime.py#L495) (raise) |
| `reasoning_selection_mismatch` | [managed_settings.py:49](../../job_applier/managed_settings.py#L49) (raise); [managed_settings.py:51](../../job_applier/managed_settings.py#L51) (raise) |
| `requested_runtime_not_verified` | [hermes_plugin.py:120](../../job_applier/hermes_plugin.py#L120) (raise); [hermes_plugin.py:124](../../job_applier/hermes_plugin.py#L124) (raise) |
| `runtime_config_not_selected` | [application_runtime.py:28](../../job_applier/application_runtime.py#L28) (raise) |
| `runtime_database_mismatch` | [workday_fast.py:353](../../job_applier/workday_fast.py#L353) (raise) |
| `simplify_disabled_by_configuration` | [workday_auth.py:101](../../job_applier/workday_auth.py#L101) (handoff) |
| `simplify_workspace_setup_required` | [workspace_host.py:207](../../job_applier/workspace_host.py#L207) (raise) |
| `subscription_route_not_verified` | [hermes_plugin.py:122](../../job_applier/hermes_plugin.py#L122) (raise) |

## G08

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g08).

| Message or reason | Source sites and kind |
|---|---|
| `attempt_completed` | [managed.py:368](../../job_applier/managed.py#L368) (raise); [managed_documents.py:62](../../job_applier/managed_documents.py#L62) (raise) |
| `attempt_not_started` | [application_runtime.py:194](../../job_applier/application_runtime.py#L194) (raise); [application_runtime.py:207](../../job_applier/application_runtime.py#L207) (raise) |
| `closed_target_cannot_rebind` | [managed_runtime.py:85](../../job_applier/managed_runtime.py#L85) (raise) |
| `closed_target_immutable` | [managed_runtime.py:99](../../job_applier/managed_runtime.py#L99) (raise) |
| `conflicting_finish` | [managed.py:432](../../job_applier/managed.py#L432) (raise) |
| `control_pending` | [managed.py:394](../../job_applier/managed.py#L394) (raise) |
| `local_host_must_stop_browser` | [managed_events.py:144](../../job_applier/managed_events.py#L144) (raise) |
| `local_session_not_connected` | [managed_sessions.py:158](../../job_applier/managed_sessions.py#L158) (raise); [workspace_host.py:276](../../job_applier/workspace_host.py#L276) (raise) |
| `local_session_resolves_lifecycle` | [hermes_plugin.py:292](../../job_applier/hermes_plugin.py#L292) (raise) |
| `local_session_stop_required` | [application_runtime.py:210](../../job_applier/application_runtime.py#L210) (raise); [managed.py:447](../../job_applier/managed.py#L447) (raise) |
| `no_control_request` | [managed_events.py:147](../../job_applier/managed_events.py#L147) (raise); [managed_events.py:161](../../job_applier/managed_events.py#L161) (raise) |
| `not_paused` | [managed_events.py:129](../../job_applier/managed_events.py#L129) (raise) |
| `owned_browser_stop_evidence_required` | [managed_sessions.py:216](../../job_applier/managed_sessions.py#L216) (raise) |
| `owned_browser_stop_unconfirmed` | [workspace_host.py:229](../../job_applier/workspace_host.py#L229) (raise) |
| `owned_process_stop_failed` | [workspace_process.py:488](../../job_applier/workspace_process.py#L488) (raise) |
| `owned_process_stop_unconfirmed` | [workspace_process.py:492](../../job_applier/workspace_process.py#L492) (raise) |
| `run_not_active` | [managed.py:331](../../job_applier/managed.py#L331) (raise) |
| `run_not_resumable` | [managed_continuity.py:35](../../job_applier/managed_continuity.py#L35) (raise) |
| `run_stopping` | [managed_runtime.py:57](../../job_applier/managed_runtime.py#L57) (raise) |
| `run_terminal` | [managed_events.py:127](../../job_applier/managed_events.py#L127) (raise) |
| `session_not_preparing` | [managed_sessions.py:180](../../job_applier/managed_sessions.py#L180) (raise) |
| `start_a_local_session_first` | [hermes_plugin.py:286](../../job_applier/hermes_plugin.py#L286) (raise) |
| `startup_cancelled` | [workspace_host.py:218](../../job_applier/workspace_host.py#L218) (raise) |
| `stop_pending` | [managed_events.py:132](../../job_applier/managed_events.py#L132) (raise) |
| `stop_previous_driver_before_attach` | [managed_sessions.py:245](../../job_applier/managed_sessions.py#L245) (raise) |
| `stop_session_before_retry` | [application_runtime.py:216](../../job_applier/application_runtime.py#L216) (raise) |
| `use_local_session_attach` | [managed_continuity.py:32](../../job_applier/managed_continuity.py#L32) (raise) |
| `use_local_session_handle` | [managed_continuity.py:14](../../job_applier/managed_continuity.py#L14) (raise) |

## G09

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g09).

| Message or reason | Source sites and kind |
|---|---|
| `account_in_use` | [managed_sessions.py:260](../../job_applier/managed_sessions.py#L260) (raise) |
| `local_lock_busy` | [workspace_process.py:264](../../job_applier/workspace_process.py#L264) (raise); [workspace_process.py:268](../../job_applier/workspace_process.py#L268) (raise); [workspace_process.py:279](../../job_applier/workspace_process.py#L279) (raise); [workspace_process.py:292](../../job_applier/workspace_process.py#L292) (raise) |
| `session_limit` | [managed_ui.py:36](../../job_applier/managed_ui.py#L36) (result); [managed_ui.py:61](../../job_applier/managed_ui.py#L61) (result) |
| `session_operation_busy` | [workspace_host.py:339](../../job_applier/workspace_host.py#L339) (raise) |
| `workspace_host_stopping` | [workspace_host.py:49](../../job_applier/workspace_host.py#L49) (raise) |

## G10

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g10).

| Message or reason | Source sites and kind |
|---|---|
| `autofill_active` | [simplify_boundary.py:48](../../job_applier/simplify_boundary.py#L48) (result) |
| `browser_writer_busy` | [managed_events.py:85](../../job_applier/managed_events.py#L85) (raise) |
| `observation_unavailable` | [simplify_boundary.py:146](../../job_applier/simplify_boundary.py#L146) (handoff) |
| `official_extension_observation_required` | [managed_runtime.py:175](../../job_applier/managed_runtime.py#L175) (raise) |
| `quiescence_unverified` | [simplify_boundary.py:105](../../job_applier/simplify_boundary.py#L105) (handoff) |
| `simplify_input_or_settlement_required` | [application_runtime.py:311](../../job_applier/application_runtime.py#L311) (raise); [workspace_host.py:300](../../job_applier/workspace_host.py#L300) (raise) |
| `simplify_input_required` | [workday_auth.py:76](../../job_applier/workday_auth.py#L76) (handoff); [workday_fast.py:304](../../job_applier/workday_fast.py#L304) (handoff) |
| `writer_activity_unconfirmed` | [submission.py:82](../../job_applier/submission.py#L82) (result); [workday_fast.py:278](../../job_applier/workday_fast.py#L278) (handoff) |
| `writer_activity_unconfirmed_observe_only` | [workday_auth.py:74](../../job_applier/workday_auth.py#L74) (handoff); [workday_fast.py:240](../../job_applier/workday_fast.py#L240) (handoff) |
| `writers_not_quiescent` | [managed.py:433](../../job_applier/managed.py#L433) (raise); [managed_events.py:145](../../job_applier/managed_events.py#L145) (raise); [managed_events.py:157](../../job_applier/managed_events.py#L157) (raise); [managed_events.py:158](../../job_applier/managed_events.py#L158) (raise); [managed_events.py:159](../../job_applier/managed_events.py#L159) (raise) |

## G11

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g11).

| Message or reason | Source sites and kind |
|---|---|
| `'Maximum runtime reached'` | [workspace_host.py:390](../../job_applier/workspace_host.py#L390) (expression/transition) |
| `attempt_budget_exceeded` | [managed_runtime.py:50](../../job_applier/managed_runtime.py#L50) (raise) |
| `budget_extension_limit` | [managed_runtime.py:58](../../job_applier/managed_runtime.py#L58) (raise) |
| `fallback_not_allowed` | [managed_runtime.py:32](../../job_applier/managed_runtime.py#L32) (raise) |
| `invalid_budget_extension` | [managed_runtime.py:54](../../job_applier/managed_runtime.py#L54) (raise) |
| `no_progress_budget_exceeded` | [managed_runtime.py:51](../../job_applier/managed_runtime.py#L51) (raise) |
| `semantic_field_budget_exceeded` | [managed_runtime.py:39](../../job_applier/managed_runtime.py#L39) (raise) |
| `semantic_field_timing_unknown` | [managed_runtime.py:37](../../job_applier/managed_runtime.py#L37) (raise) |

## G12

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g12).

| Message or reason | Source sites and kind |
|---|---|
| `'bounded_call_elapsed'` | [workday_fast.py:334](../../job_applier/workday_fast.py#L334) (expression/transition) |
| `Invalid Simplify budget` | [simplify_boundary.py:14](../../job_applier/simplify_boundary.py#L14) (raise) |
| `Unrecognized Simplify observation` | [simplify_boundary.py:24](../../job_applier/simplify_boundary.py#L24) (raise) |
| `Unsupported Simplify operation` | [simplify_boundary.py:81](../../job_applier/simplify_boundary.py#L81) (raise) |
| `already_attempted` | [simplify_boundary.py:107](../../job_applier/simplify_boundary.py#L107) (handoff) |
| `autofill_budget_timeout` | [simplify_boundary.py:143](../../job_applier/simplify_boundary.py#L143) (handoff) |
| `autofill_ready` | [simplify_boundary.py:57](../../job_applier/simplify_boundary.py#L57) (result) |
| `bounded_call_elapsed` | [workday_fast.py:334](../../job_applier/workday_fast.py#L334) (inline/embedded reason) |
| `bounded_seconds_required` | [workday_fast.py:168](../../job_applier/workday_fast.py#L168) (raise); [workday_fast.py:349](../../job_applier/workday_fast.py#L349) (raise) |
| `click_result_unavailable` | [workday_fast.py:152](../../job_applier/workday_fast.py#L152) (result) |
| `click_unconfirmed` | [workday_fast.py:324](../../job_applier/workday_fast.py#L324) (handoff) |
| `controls_unavailable` | [simplify_boundary.py:50](../../job_applier/simplify_boundary.py#L50) (result) |
| `invalid_fast_checkpoint` | [workday_fast.py:376](../../job_applier/workday_fast.py#L376) (raise) |
| `observed_employer_sign_in` | [simplify_boundary.py:103](../../job_applier/simplify_boundary.py#L103) (result) |
| `page_changed_rediscover_controls` | [simplify_boundary.py:138](../../job_applier/simplify_boundary.py#L138) (handoff) |
| `prefer_extension_continue` | [simplify_boundary.py:54](../../job_applier/simplify_boundary.py#L54) (result); [simplify_boundary.py:61](../../job_applier/simplify_boundary.py#L61) (result) |
| `review_residual_fields` | [simplify_boundary.py:55](../../job_applier/simplify_boundary.py#L55) (result) |
| `simplify_waiting_for_skills_input` | [simplify_boundary.py:52](../../job_applier/simplify_boundary.py#L52) (result) |
| `start_ready` | [simplify_boundary.py:59](../../job_applier/simplify_boundary.py#L59) (result) |
| `workday_only` | [workday_fast.py:360](../../job_applier/workday_fast.py#L360) (raise) |

## G13

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g13).

| Message or reason | Source sites and kind |
|---|---|
| `'account_creation_confirmed_use_sign_in'` | [workday_auth.py:112](../../job_applier/workday_auth.py#L112) (expression/transition) |
| `account_click_recovery_limit` | [workday_auth.py:14](../../job_applier/workday_auth.py#L14) (raise); [workday_auth.py:114](../../job_applier/workday_auth.py#L114) (handoff); [workday_auth.py:230](../../job_applier/workday_auth.py#L230) (handoff) |
| `account_creation_outcome_unconfirmed` | [workday_auth.py:229](../../job_applier/workday_auth.py#L229) (handoff) |
| `account_evidence_required` | [managed_accounts.py:73](../../job_applier/managed_accounts.py#L73) (raise) |
| `account_namespace_not_verified_for_job` | [managed_accounts.py:77](../../job_applier/managed_accounts.py#L77) (raise) |
| `account_namespace_unverified` | [workday_auth.py:211](../../job_applier/workday_auth.py#L211) (handoff) |
| `account_observation_requires_reconciliation` | [managed_accounts.py:100](../../job_applier/managed_accounts.py#L100) (raise) |
| `account_requires_operator` | [workday_auth.py:110](../../job_applier/workday_auth.py#L110) (handoff); [workday_auth.py:214](../../job_applier/workday_auth.py#L214) (handoff) |
| `ambiguous_mail` | [managed_accounts.py:187](../../job_applier/managed_accounts.py#L187) (raise) |
| `ambiguous_or_stale_{dynamic suffix}` | [managed_credentials.py:65](../../job_applier/managed_credentials.py#L65) (inline/embedded reason) |
| `auth_response_lost` | [workday_auth.py:272](../../job_applier/workday_auth.py#L272) (result) |
| `credential_controls_must_share_document` | [managed_credentials.py:137](../../job_applier/managed_credentials.py#L137) (result) |
| `credential_reference_required` | [managed_accounts.py:91](../../job_applier/managed_accounts.py#L91) (raise) |
| `credential_transport_failed` | [managed_credentials.py:145](../../job_applier/managed_credentials.py#L145) (result); [managed_credentials.py:164](../../job_applier/managed_credentials.py#L164) (result) |
| `duplicate_control_ref` | [managed_credentials.py:71](../../job_applier/managed_credentials.py#L71) (inline/embedded reason) |
| `evidence_required` | [managed_accounts.py:93](../../job_applier/managed_accounts.py#L93) (raise) |
| `expected_sender_required` | [managed_accounts.py:146](../../job_applier/managed_accounts.py#L146) (raise) |
| `idempotency_conflict` | [managed_accounts.py:98](../../job_applier/managed_accounts.py#L98) (raise) |
| `incorrect_{dynamic suffix}` | [managed_credentials.py:70](../../job_applier/managed_credentials.py#L70) (inline/embedded reason) |
| `invalid_account_state` | [managed_accounts.py:90](../../job_applier/managed_accounts.py#L90) (raise) |
| `invalid_mail_purpose` | [managed_accounts.py:145](../../job_applier/managed_accounts.py#L145) (raise) |
| `invalid_namespace` | [managed_accounts.py:15](../../job_applier/managed_accounts.py#L15) (raise) |
| `invalid_timestamp` | [managed_accounts.py:26](../../job_applier/managed_accounts.py#L26) (raise) |
| `invalid_{dynamic suffix}` | [managed_credentials.py:64](../../job_applier/managed_credentials.py#L64) (inline/embedded reason) |
| `mail_namespace_not_verified` | [managed_accounts.py:159](../../job_applier/managed_accounts.py#L159) (raise) |
| `mail_request_not_owned` | [managed_accounts.py:168](../../job_applier/managed_accounts.py#L168) (raise) |
| `mapped_account_mode_required` | [workday_auth.py:97](../../job_applier/workday_auth.py#L97) (handoff) |
| `mapped_private_credentials_required` | [workday_auth.py:98](../../job_applier/workday_auth.py#L98) (handoff) |
| `matching_creation_attempt_required` | [managed_accounts.py:105](../../job_applier/managed_accounts.py#L105) (raise) |
| `missing_{dynamic suffix}` | [managed_credentials.py:58](../../job_applier/managed_credentials.py#L58) (inline/embedded reason) |
| `namespace_alias_conflict` | [managed_accounts.py:37](../../job_applier/managed_accounts.py#L37) (raise); [managed_accounts.py:49](../../job_applier/managed_accounts.py#L49) (raise) |
| `namespace_alias_cycle` | [managed_accounts.py:34](../../job_applier/managed_accounts.py#L34) (raise); [managed_accounts.py:46](../../job_applier/managed_accounts.py#L46) (raise) |
| `namespace_verification_required` | [managed_accounts.py:44](../../job_applier/managed_accounts.py#L44) (raise) |
| `retained_credential_use_unverified` | [simplify_boundary.py:100](../../job_applier/simplify_boundary.py#L100) (handoff); [workday_auth.py:104](../../job_applier/workday_auth.py#L104) (handoff) |
| `saved_credential_reference_unavailable` | [managed_credentials.py:109](../../job_applier/managed_credentials.py#L109) (raise) |
| `sign_in_already_attempted` | [simplify_boundary.py:102](../../job_applier/simplify_boundary.py#L102) (handoff) |
| `sign_in_response_needs_inspection` | [simplify_boundary.py:140](../../job_applier/simplify_boundary.py#L140) (handoff) |
| `simplify_login_is_not_employer_sign_in` | [simplify_boundary.py:98](../../job_applier/simplify_boundary.py#L98) (handoff) |
| `unavailable_{dynamic suffix}` | [managed_credentials.py:68](../../job_applier/managed_credentials.py#L68) (inline/embedded reason) |
| `use_private_credentials_helper` | [form_controls.js:106](../../job_applier/browser_helpers/form_controls.js#L106) (inline/embedded reason) |
| `use_scoped_simplify_sign_in_with_credential_evidence` | [application_runtime.py:405](../../job_applier/application_runtime.py#L405) (result) |
| `values_not_committed` | [managed_credentials.py:92](../../job_applier/managed_credentials.py#L92) (inline/embedded reason) |
| `workday_account_coordination_unavailable` | [workday_auth.py:106](../../job_applier/workday_auth.py#L106) (handoff); [workday_auth.py:202](../../job_applier/workday_auth.py#L202) (handoff) |
| `workday_auth_action_already_attempted` | [workday_auth.py:243](../../job_applier/workday_auth.py#L243) (handoff) |
| `workday_auth_controls_unrecognized` | [workday_auth.py:223](../../job_applier/workday_auth.py#L223) (handoff) |
| `workday_auth_page_changed_during_fill` | [workday_auth.py:254](../../job_applier/workday_auth.py#L254) (handoff) |
| `workday_auth_submit_disabled_after_fill` | [workday_auth.py:256](../../job_applier/workday_auth.py#L256) (handoff) |
| `workday_credentials_rejected` | [workday_auth.py:99](../../job_applier/workday_auth.py#L99) (handoff) |
| `workday_sign_in_unconfirmed` | [workday_auth.py:218](../../job_applier/workday_auth.py#L218) (handoff) |
| `workday_verification_required` | [workday_auth.py:91](../../job_applier/workday_auth.py#L91) (handoff) |

## G14

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g14).

| Message or reason | Source sites and kind |
|---|---|
| `'mapped_step_'+type(exc).__name__` | [workday_auth.py:164](../../job_applier/workday_auth.py#L164) (expression/transition) |
| `ambiguous_option` | [browser_controls.py:148](../../job_applier/browser_controls.py#L148) (result) |
| `ambiguous_or_stale_control` | [browser_controls.py:187](../../job_applier/browser_controls.py#L187) (raise); [workday_click.js:9](../../job_applier/browser_helpers/workday_click.js#L9) (inline/embedded reason) |
| `ambiguous_simplify_document_use_observed_ref` | [browser_controls.py:259](../../job_applier/browser_controls.py#L259) (raise) |
| `checkbox_value_required` | [form_controls.js:137](../../job_applier/browser_helpers/form_controls.js#L137) (inline/embedded reason) |
| `configured_answer_control_unconfirmed` | [workday_fast.py:286](../../job_applier/workday_fast.py#L286) (handoff) |
| `control_changed` | [simplify_click.js:8](../../job_applier/browser_helpers/simplify_click.js#L8) (inline/embedded reason); [simplify_click.js:15](../../job_applier/browser_helpers/simplify_click.js#L15) (inline/embedded reason) |
| `control_changed_before_press` | [cdp_client.py:357](../../job_applier/cdp_client.py#L357) (result) |
| `control_disabled` | [simplify_click.js:19](../../job_applier/browser_helpers/simplify_click.js#L19) (inline/embedded reason) |
| `control_disabled_or_not available` | [simplify_boundary.py:111](../../job_applier/simplify_boundary.py#L111) (handoff) |
| `control_focus_unconfirmed` | [browser_controls.py:110](../../job_applier/browser_controls.py#L110) (result) |
| `control_obscured` | [workday_click.js:60](../../job_applier/browser_helpers/workday_click.js#L60) (inline/embedded reason) |
| `control_unavailable` | [form_controls.js:103](../../job_applier/browser_helpers/form_controls.js#L103) (inline/embedded reason); [workday_fast.py:142](../../job_applier/workday_fast.py#L142) (result) |
| `exact_option_required` | [browser_controls.py:129](../../job_applier/browser_controls.py#L129) (raise) |
| `file_control_unavailable` | [browser_controls.py:192](../../job_applier/browser_controls.py#L192) (raise); [browser_controls.py:194](../../job_applier/browser_controls.py#L194) (raise) |
| `hidden_control` | [workday_click.js:47](../../job_applier/browser_helpers/workday_click.js#L47) (inline/embedded reason) |
| `mapped_action_unavailable` | [workday_auth.py:85](../../job_applier/workday_auth.py#L85) (handoff) |
| `mapped_field_requires_private_helper` | [workday_click.js:23](../../job_applier/browser_helpers/workday_click.js#L23) (inline/embedded reason) |
| `mapped_field_unavailable` | [workday_click.js:20](../../job_applier/browser_helpers/workday_click.js#L20) (inline/embedded reason) |
| `mapped_option_unavailable` | [workday_click.js:25](../../job_applier/browser_helpers/workday_click.js#L25) (inline/embedded reason) |
| `mapped_response_lost` | [workday_auth.py:166](../../job_applier/workday_auth.py#L166) (result) |
| `menu_association_unconfirmed` | [form_controls.js:167](../../job_applier/browser_helpers/form_controls.js#L167) (inline/embedded reason) |
| `native_select_required` | [form_controls.js:149](../../job_applier/browser_helpers/form_controls.js#L149) (inline/embedded reason) |
| `new_screen_evidence_requires_mapping` | [workday_auth.py:77](../../job_applier/workday_auth.py#L77) (handoff) |
| `observed_control_required` | [application_runtime.py:419](../../job_applier/application_runtime.py#L419) (raise); [browser_controls.py:95](../../job_applier/browser_controls.py#L95) (raise) |
| `observed_selector_required` | [application_runtime.py:425](../../job_applier/application_runtime.py#L425) (raise) |
| `outside_viewport` | [workday_click.js:50](../../job_applier/browser_helpers/workday_click.js#L50) (inline/embedded reason) |
| `page_changed` | [simplify_click.js:5](../../job_applier/browser_helpers/simplify_click.js#L5) (inline/embedded reason) |
| `pointer_dispatch_unconfirmed` | [cdp_client.py:363](../../job_applier/cdp_client.py#L363) (result) |
| `screen_action_already_attempted` | [workday_auth.py:79](../../job_applier/workday_auth.py#L79) (handoff) |
| `select_control_unrecognized` | [browser_controls.py:140](../../job_applier/browser_controls.py#L140) (result) |
| `settled_screen_unrecognized` | [workday_fast.py:239](../../job_applier/workday_fast.py#L239) (handoff) |
| `simplify_control_stale` | [browser_controls.py:246](../../job_applier/browser_controls.py#L246) (raise) |
| `simplify_operation_mismatch` | [browser_controls.py:247](../../job_applier/browser_controls.py#L247) (raise) |
| `stale_control` | [application_runtime.py:404](../../job_applier/application_runtime.py#L404) (result); [workday_click.js:44](../../job_applier/browser_helpers/workday_click.js#L44) (inline/embedded reason) |
| `stale_or_unconfirmed_control` | [simplify_boundary.py:121](../../job_applier/simplify_boundary.py#L121) (handoff) |
| `stale_page` | [workday_click.js:7](../../job_applier/browser_helpers/workday_click.js#L7) (inline/embedded reason); [workday_click.js:12](../../job_applier/browser_helpers/workday_click.js#L12) (inline/embedded reason) |
| `stale_screen` | [application_runtime.py:399](../../job_applier/application_runtime.py#L399) (result); [workday_click.js:13](../../job_applier/browser_helpers/workday_click.js#L13) (inline/embedded reason) |
| `text_input_required` | [form_controls.js:142](../../job_applier/browser_helpers/form_controls.js#L142) (inline/embedded reason) |
| `unsupported_form_key` | [cdp_client.py:270](../../job_applier/cdp_client.py#L270) (raise) |
| `unsupported_form_operation` | [browser_controls.py:127](../../job_applier/browser_controls.py#L127) (raise); [form_controls.js:180](../../job_applier/browser_helpers/form_controls.js#L180) (inline/embedded reason) |
| `unsupported_key_modifier` | [cdp_client.py:264](../../job_applier/cdp_client.py#L264) (raise) |
| `use_observed_browser_control` | [workday_auth.py:102](../../job_applier/workday_auth.py#L102) (handoff) |

## G15

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g15).

| Message or reason | Source sites and kind |
|---|---|
| `application_frame_context_required` | [browser_frames.py:224](../../job_applier/browser_frames.py#L224) (raise) |
| `application_frame_limit` | [browser_frames.py:171](../../job_applier/browser_frames.py#L171) (result); [browser_frames.py:177](../../job_applier/browser_frames.py#L177) (result) |
| `application_frame_unavailable` | [browser_controls.py:254](../../job_applier/browser_controls.py#L254) (raise); [browser_frames.py:205](../../job_applier/browser_frames.py#L205) (result) |
| `frame_control_obscured` | [browser_frames.py:117](../../job_applier/browser_frames.py#L117) (inline/embedded reason) |
| `frame_document_changed` | [browser_frames.py:82](../../job_applier/browser_frames.py#L82) (raise); [browser_frames.py:83](../../job_applier/browser_frames.py#L83) (raise) |
| `frame_document_unavailable` | [browser_frames.py:49](../../job_applier/browser_frames.py#L49) (raise) |
| `frame_owner_changed` | [browser_frames.py:80](../../job_applier/browser_frames.py#L80) (raise); [browser_frames.py:101](../../job_applier/browser_frames.py#L101) (inline/embedded reason) |
| `frame_owner_unavailable` | [browser_frames.py:57](../../job_applier/browser_frames.py#L57) (raise); [browser_frames.py:58](../../job_applier/browser_frames.py#L58) (raise); [browser_frames.py:119](../../job_applier/browser_frames.py#L119) (result) |
| `frame_reference_invalid` | [browser_frames.py:210](../../job_applier/browser_frames.py#L210) (raise) |
| `frame_reference_stale` | [browser_frames.py:141](../../job_applier/browser_frames.py#L141) (result); [browser_frames.py:214](../../job_applier/browser_frames.py#L214) (raise) |
| `frame_transform_unsupported` | [browser_frames.py:105](../../job_applier/browser_frames.py#L105) (inline/embedded reason) |
| `pointer_dispatch_unconfirmed` | [browser_frames.py:147](../../job_applier/browser_frames.py#L147) (result) |

## G16

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g16).

| Message or reason | Source sites and kind |
|---|---|
| `ambiguous_question_options` | [managed_questions.py:39](../../job_applier/managed_questions.py#L39) (raise) |
| `answer_option_unavailable` | [managed_questions.py:122](../../job_applier/managed_questions.py#L122) (raise); [managed_questions.py:129](../../job_applier/managed_questions.py#L129) (raise) |
| `answer_required` | [managed_questions.py:124](../../job_applier/managed_questions.py#L124) (raise) |
| `answer_revision_conflict` | [managed_questions.py:146](../../job_applier/managed_questions.py#L146) (raise) |
| `answers_required` | [hermes_plugin.py:263](../../job_applier/hermes_plugin.py#L263) (raise); [managed_questions.py:137](../../job_applier/managed_questions.py#L137) (raise) |
| `approved_answer_policy_required` | [application_runtime.py:100](../../job_applier/application_runtime.py#L100) (raise) |
| `boolean_answer_required` | [managed_questions.py:118](../../job_applier/managed_questions.py#L118) (raise) |
| `duplicate_answer` | [managed_questions.py:138](../../job_applier/managed_questions.py#L138) (raise) |
| `human_answer_source_required` | [managed_questions.py:134](../../job_applier/managed_questions.py#L134) (raise) |
| `invalid_answer` | [managed_questions.py:142](../../job_applier/managed_questions.py#L142) (raise) |
| `invalid_market_policy` | [managed_settings.py:39](../../job_applier/managed_settings.py#L39) (raise) |
| `invalid_question` | [managed_questions.py:29](../../job_applier/managed_questions.py#L29) (raise) |
| `invalid_question_options` | [managed_questions.py:31](../../job_applier/managed_questions.py#L31) (raise); [managed_questions.py:35](../../job_applier/managed_questions.py#L35) (raise); [managed_questions.py:36](../../job_applier/managed_questions.py#L36) (raise) |
| `invalid_screenshot_policy` | [managed_settings.py:29](../../job_applier/managed_settings.py#L29) (raise) |
| `no_exact_saved_answer` | [application_runtime.py:367](../../job_applier/application_runtime.py#L367) (result) |
| `no_pending_questions` | [managed_questions.py:109](../../job_applier/managed_questions.py#L109) (raise) |
| `observed_options_required` | [managed_questions.py:38](../../job_applier/managed_questions.py#L38) (raise) |
| `observed_question_refs_required` | [browser_controls.py:203](../../job_applier/browser_controls.py#L203) (raise) |
| `observed_user_reply_required` | [hermes_plugin.py:260](../../job_applier/hermes_plugin.py#L260) (raise) |
| `private_question_prohibited` | [managed_questions.py:30](../../job_applier/managed_questions.py#L30) (raise) |
| `question_changed` | [managed_questions.py:144](../../job_applier/managed_questions.py#L144) (raise) |
| `question_control_unrecognized` | [form_controls.js:114](../../job_applier/browser_helpers/form_controls.js#L114) (inline/embedded reason) |
| `required_blocker_only` | [workday_fast.py:287](../../job_applier/workday_fast.py#L287) (handoff) |
| `required_question_only` | [managed_questions.py:26](../../job_applier/managed_questions.py#L26) (raise) |
| `retry_jobs_required` | [managed_questions.py:189](../../job_applier/managed_questions.py#L189) (raise) |
| `saved_radio_option_unavailable` | [application_runtime.py:372](../../job_applier/application_runtime.py#L372) (result) |
| `unanswered_questions` | [managed_questions.py:195](../../job_applier/managed_questions.py#L195) (raise) |
| `unsupported_question_kind` | [managed_questions.py:27](../../job_applier/managed_questions.py#L27) (raise) |
| `user_reply_evidence_required` | [managed_questions.py:136](../../job_applier/managed_questions.py#L136) (raise) |
| `user_reply_predates_answer` | [hermes_plugin.py:270](../../job_applier/hermes_plugin.py#L270) (raise) |
| `user_reply_predates_question` | [hermes_plugin.py:268](../../job_applier/hermes_plugin.py#L268) (raise) |
| `workday_consent_needs_inspection` | [workday_auth.py:200](../../job_applier/workday_auth.py#L200) (expression/transition) |

## G17

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g17).

| Message or reason | Source sites and kind |
|---|---|
| `observed_submit_control_required` | [application_runtime.py:292](../../job_applier/application_runtime.py#L292) (raise); [application_runtime.py:303](../../job_applier/application_runtime.py#L303) (raise) |
| `submission_intent_required` | [managed.py:435](../../job_applier/managed.py#L435) (raise) |
| `submission_observation_only` | [workday_auth.py:81](../../job_applier/workday_auth.py#L81) (handoff) |
| `submission_pending_read_only` | [application_runtime.py:306](../../job_applier/application_runtime.py#L306) (raise); [managed_questions.py:80](../../job_applier/managed_questions.py#L80) (raise); [managed_questions.py:107](../../job_applier/managed_questions.py#L107) (raise); [managed_questions.py:160](../../job_applier/managed_questions.py#L160) (raise) |
| `submission_target_mismatch` | [submission.py:43](../../job_applier/submission.py#L43) (raise) |
| `submission_unknown` | [managed_sessions.py:194](../../job_applier/managed_sessions.py#L194) (raise); [managed_sessions.py:247](../../job_applier/managed_sessions.py#L247) (raise) |
| `submit_control_changed` | [workday_fast.py:294](../../job_applier/workday_fast.py#L294) (result) |
| `submit_control_unavailable` | [application_runtime.py:300](../../job_applier/application_runtime.py#L300) (result) |
| `use_existing_final_submission_boundary` | [workday_auth.py:88](../../job_applier/workday_auth.py#L88) (handoff) |
| `verify_exact_submission_before_retry` | [application_runtime.py:218](../../job_applier/application_runtime.py#L218) (raise) |

## G18

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g18).

| Message or reason | Source sites and kind |
|---|---|
| `'Submission confirmation not captured; bounded inspection ended'` | [workspace_host.py:387](../../job_applier/workspace_host.py#L387) (expression/transition) |
| `confirmation_not_captured` | [workspace_host.py:236](../../job_applier/workspace_host.py#L236) (inline/embedded reason) |
| `invalid_evidence_source` | [managed.py:440](../../job_applier/managed.py#L440) (raise) |
| `outcome_readback_unconfirmed` | [workday_fast.py:203](../../job_applier/workday_fast.py#L203) (handoff) |
| `reconciliation_evidence_required` | [managed.py:443](../../job_applier/managed.py#L443) (raise) |

## G19

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g19).

| Message or reason | Source sites and kind |
|---|---|
| `Selected resume is missing or changed` | [managed_documents.py:27](../../job_applier/managed_documents.py#L27) (raise) |
| `Selected resume must be a verified local file` | [managed_documents.py:24](../../job_applier/managed_documents.py#L24) (raise) |
| `asset_not_selected` | [application_runtime.py:417](../../job_applier/application_runtime.py#L417) (raise); [managed_documents.py:92](../../job_applier/managed_documents.py#L92) (raise) |
| `asset_version_immutable` | [managed_documents.py:48](../../job_applier/managed_documents.py#L48) (raise) |
| `confirmed_upload_immutable` | [managed_documents.py:96](../../job_applier/managed_documents.py#L96) (raise) |
| `empty_file` | [managed_api.py:92](../../job_applier/managed_api.py#L92) (result) |
| `invalid_assessment` | [managed_documents.py:106](../../job_applier/managed_documents.py#L106) (raise) |
| `invalid_assessment_provenance` | [managed_documents.py:103](../../job_applier/managed_documents.py#L103) (raise) |
| `invalid_assessment_scale` | [managed_documents.py:104](../../job_applier/managed_documents.py#L104) (raise) |
| `invalid_assessment_score` | [managed_documents.py:105](../../job_applier/managed_documents.py#L105) (raise) |
| `invalid_assessment_time` | [managed_documents.py:110](../../job_applier/managed_documents.py#L110) (raise) |
| `invalid_asset_kind` | [managed_api.py:78](../../job_applier/managed_api.py#L78) (result) |
| `invalid_asset_metadata` | [managed_documents.py:39](../../job_applier/managed_documents.py#L39) (raise) |
| `invalid_hash` | [managed_documents.py:32](../../job_applier/managed_documents.py#L32) (raise) |
| `invalid_required_documents` | [managed_documents.py:74](../../job_applier/managed_documents.py#L74) (raise) |
| `invalid_storage_path` | [managed_api.py:99](../../job_applier/managed_api.py#L99) (result) |
| `invalid_storage_reference` | [managed_documents.py:40](../../job_applier/managed_documents.py#L40) (raise) |
| `invalid_upload_event` | [managed_documents.py:87](../../job_applier/managed_documents.py#L87) (raise) |
| `path_traversal_prohibited` | [managed_api.py:81](../../job_applier/managed_api.py#L81) (result) |
| `private_storage_reference_required` | [managed_documents.py:42](../../job_applier/managed_documents.py#L42) (raise) |
| `required_document_missing` | [managed.py:393](../../job_applier/managed.py#L393) (raise) |
| `target_exists` | [managed_cli.py:108](../../job_applier/managed_cli.py#L108) (result) |
| `unsupported_file_type` | [managed_api.py:85](../../job_applier/managed_api.py#L85) (result) |
| `upload_not_attempted` | [managed_documents.py:94](../../job_applier/managed_documents.py#L94) (raise) |

## G20

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g20).

| Message or reason | Source sites and kind |
|---|---|
| `action_already_finished` | [managed_events.py:82](../../job_applier/managed_events.py#L82) (raise) |
| `idempotency_conflict` | [managed_events.py:38](../../job_applier/managed_events.py#L38) (raise); [managed_events.py:81](../../job_applier/managed_events.py#L81) (raise); [managed_events.py:105](../../job_applier/managed_events.py#L105) (raise) |
| `invalid_action_status` | [managed_events.py:92](../../job_applier/managed_events.py#L92) (raise) |
| `invalid_control` | [managed_events.py:124](../../job_applier/managed_events.py#L124) (raise) |
| `invalid_duration` | [managed_events.py:30](../../job_applier/managed_events.py#L30) (raise); [managed_events.py:94](../../job_applier/managed_events.py#L94) (raise) |
| `invalid_event` | [managed_events.py:23](../../job_applier/managed_events.py#L23) (raise) |
| `invalid_semantic_context` | [managed_events.py:34](../../job_applier/managed_events.py#L34) (raise) |
| `invalid_timestamp` | [managed_events.py:28](../../job_applier/managed_events.py#L28) (raise) |
| `invalid_writer_flag` | [managed_events.py:70](../../job_applier/managed_events.py#L70) (raise) |
| `invalid_writer_state` | [managed_events.py:117](../../job_applier/managed_events.py#L117) (raise) |
| `secret_in_snapshot` | [managed_redaction.py:52](../../job_applier/managed_redaction.py#L52) (raise); [managed_redaction.py:57](../../job_applier/managed_redaction.py#L57) (raise) |
| `telemetry_delivery_pending` | [hermes_plugin.py:192](../../job_applier/hermes_plugin.py#L192) (raise) |
| `timestamp_requires_timezone` | [managed_events.py:98](../../job_applier/managed_events.py#L98) (raise) |

## G21

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g21).

| Message or reason | Source sites and kind |
|---|---|
| `'workday_'+action+'_unavailable'` | [workday_auth.py:246](../../job_applier/workday_auth.py#L246) (expression/transition) |
| `'workday_'+mode+'_unconfirmed'` | [workday_auth.py:222](../../job_applier/workday_auth.py#L222) (expression/transition) |
| `Cancelled while waiting for capacity` | [application_runtime.py:230](../../job_applier/application_runtime.py#L230) (inline/embedded reason) |
| `Explicit attach after owned browser stopped` | [managed_sessions.py:248](../../job_applier/managed_sessions.py#L248) (inline/embedded reason) |
| `Previous host died; owned process identity is stopped. Lost command was not replayed.` | [workspace_host.py:357](../../job_applier/workspace_host.py#L357) (inline/embedded reason) |
| `System restart/crash during execution` | [db_queue.py:331](../../job_applier/db_queue.py#L331) (inline/embedded reason) |
| `User-requested URL under configured standing application authorization` | [application_runtime.py:124](../../job_applier/application_runtime.py#L124) (inline/embedded reason) |
| `dispatch_pending` | [workday_auth.py:18](../../job_applier/workday_auth.py#L18) (result) |
| `evidence_required` | [managed.py:400](../../job_applier/managed.py#L400) (raise); [managed.py:434](../../job_applier/managed.py#L434) (raise) |
| `fake_worker_requires_development_review` | [managed_fake_worker.py:9](../../job_applier/managed_fake_worker.py#L9) (raise) |
| `fixture_context_mismatch` | [managed_fake_worker.py:23](../../job_applier/managed_fake_worker.py#L23) (raise) |
| `heartbeat_unavailable` | [hermes_plugin.py:154](../../job_applier/hermes_plugin.py#L154) (inline/embedded reason) |
| `idempotency_conflict` | [managed.py:262](../../job_applier/managed.py#L262) (raise); [managed_continuity.py:18](../../job_applier/managed_continuity.py#L18) (raise); [managed_sessions.py:55](../../job_applier/managed_sessions.py#L55) (raise) |
| `identity_evidence_required` | [managed.py:114](../../job_applier/managed.py#L114) (raise) |
| `identity_id_required` | [managed_api.py:73](../../job_applier/managed_api.py#L73) (result) |
| `invalid_archive_filter` | [managed_views.py:144](../../job_applier/managed_views.py#L144) (raise) |
| `invalid_budget` | [managed_settings.py:34](../../job_applier/managed_settings.py#L34) (raise) |
| `invalid_checkpoint` | [managed_continuity.py:8](../../job_applier/managed_continuity.py#L8) (raise) |
| `invalid_credential_parameters` | [managed_credentials.py:124](../../job_applier/managed_credentials.py#L124) (result) |
| `invalid_eligibility` | [managed.py:218](../../job_applier/managed.py#L218) (raise) |
| `invalid_fast_parameters` | [workday_fast.py:347](../../job_applier/workday_fast.py#L347) (raise) |
| `invalid_identity` | [managed.py:164](../../job_applier/managed.py#L164) (raise); [managed.py:189](../../job_applier/managed.py#L189) (raise) |
| `invalid_identity_id` | [managed_api.py:75](../../job_applier/managed_api.py#L75) (result) |
| `invalid_login_request` | [managed_ui.py:49](../../job_applier/managed_ui.py#L49) (result); [managed_ui.py:54](../../job_applier/managed_ui.py#L54) (result) |
| `invalid_mapped_credentials` | [workday_auth.py:96](../../job_applier/workday_auth.py#L96) (handoff) |
| `invalid_mapped_fields` | [workday_auth.py:94](../../job_applier/workday_auth.py#L94) (handoff) |
| `invalid_mapped_value` | [workday_click.js:28](../../job_applier/browser_helpers/workday_click.js#L28) (inline/embedded reason) |
| `invalid_operation` | [hermes_plugin.py:163](../../job_applier/hermes_plugin.py#L163) (raise); [managed_client.py:17](../../job_applier/managed_client.py#L17) (raise) |
| `invalid_outcome` | [managed.py:425](../../job_applier/managed.py#L425) (raise) |
| `invalid_payload` | [hermes_plugin.py:179](../../job_applier/hermes_plugin.py#L179) (raise); [hermes_plugin.py:217](../../job_applier/hermes_plugin.py#L217) (raise); [hermes_plugin.py:220](../../job_applier/hermes_plugin.py#L220) (raise); [hermes_plugin.py:224](../../job_applier/hermes_plugin.py#L224) (raise); [hermes_plugin.py:240](../../job_applier/hermes_plugin.py#L240) (raise); [hermes_plugin.py:241](../../job_applier/hermes_plugin.py#L241) (raise); [managed_api.py:158](../../job_applier/managed_api.py#L158) (result); [managed_cli.py:100](../../job_applier/managed_cli.py#L100) (raise); [workspace_host.py:278](../../job_applier/workspace_host.py#L278) (raise) |
| `invalid_profile_data` | [managed_shared.py:50](../../job_applier/managed_shared.py#L50) (raise) |
| `invalid_run` | [managed.py:256](../../job_applier/managed.py#L256) (raise) |
| `invalid_screen_mapping` | [workday_auth.py:71](../../job_applier/workday_auth.py#L71) (handoff) |
| `invalid_settings_request` | [managed_settings.py:70](../../job_applier/managed_settings.py#L70) (raise) |
| `invalid_target_id` | [cdp_client.py:475](../../job_applier/cdp_client.py#L475) (raise); [managed_runtime.py:63](../../job_applier/managed_runtime.py#L63) (raise) |
| `invalid_target_state` | [managed_runtime.py:94](../../job_applier/managed_runtime.py#L94) (raise) |
| `job_not_found` | [managed.py:97](../../job_applier/managed.py#L97) (raise) |
| `key_required` | [cdp_client.py:260](../../job_applier/cdp_client.py#L260) (raise) |
| `not_found` | [managed.py:159](../../job_applier/managed.py#L159) (raise); [managed_reports.py:28](../../job_applier/managed_reports.py#L28) (raise); [managed_ui.py:43](../../job_applier/managed_ui.py#L43) (result) |
| `one_url_or_job_id_required` | [application_runtime.py:112](../../job_applier/application_runtime.py#L112) (raise) |
| `outside_batch` | [managed_continuity.py:20](../../job_applier/managed_continuity.py#L20) (raise) |
| `payload_too_large` | [managed_api.py:90](../../job_applier/managed_api.py#L90) (result); [managed_api.py:123](../../job_applier/managed_api.py#L123) (result); [workspace_host.py:84](../../job_applier/workspace_host.py#L84) (raise) |
| `role_forbidden` | [managed_api.py:70](../../job_applier/managed_api.py#L70) (result); [managed_api.py:118](../../job_applier/managed_api.py#L118) (result); [managed_ui.py:68](../../job_applier/managed_ui.py#L68) (result); [managed_ui.py:73](../../job_applier/managed_ui.py#L73) (result) |
| `run_not_found` | [managed_views.py:167](../../job_applier/managed_views.py#L167) (raise) |
| `session_required` | [managed_continuity.py:37](../../job_applier/managed_continuity.py#L37) (raise) |
| `settings_version_conflict` | [managed_settings.py:73](../../job_applier/managed_settings.py#L73) (raise) |
| `unauthorized` | [managed_api.py:56](../../job_applier/managed_api.py#L56) (result); [managed_ui.py:58](../../job_applier/managed_ui.py#L58) (result) |
| `unknown_operation` | [managed_api.py:116](../../job_applier/managed_api.py#L116) (result); [managed_client.py:45](../../job_applier/managed_client.py#L45) (raise) |
| `unsupported_browser_method` | [application_runtime.py:259](../../job_applier/application_runtime.py#L259) (raise) |
| `unsupported_capability` | [managed.py:307](../../job_applier/managed.py#L307) (raise); [managed_continuity.py:36](../../job_applier/managed_continuity.py#L36) (raise) |
| `unsupported_session_operation` | [workspace_host.py:309](../../job_applier/workspace_host.py#L309) (raise) |
| `unsupported_setting` | [managed_settings.py:25](../../job_applier/managed_settings.py#L25) (raise) |
| `unsupported_timezone` | [managed_settings.py:31](../../job_applier/managed_settings.py#L31) (raise) |
| `unsupported_transport` | [managed_client.py:56](../../job_applier/managed_client.py#L56) (raise) |
| `untrusted_origin` | [managed_api.py:42](../../job_applier/managed_api.py#L42) (result) |

## G22

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g22).

| Message or reason | Source sites and kind |
|---|---|
| `absolute_db_path_required` | [managed_data.py:14](../../job_applier/managed_data.py#L14) (raise) |
| `activation_requires_quiescence` | [managed_learning.py:100](../../job_applier/managed_learning.py#L100) (raise) |
| `already_archived` | [managed_archive.py:20](../../job_applier/managed_archive.py#L20) (raise) |
| `already_managed_source` | [managed_data.py:74](../../job_applier/managed_data.py#L74) (raise) |
| `archive_job_reserved` | [managed_archive.py:22](../../job_applier/managed_archive.py#L22) (raise) |
| `archive_preview_changed` | [managed_archive.py:41](../../job_applier/managed_archive.py#L41) (raise) |
| `archive_requires_completed_job` | [managed_archive.py:19](../../job_applier/managed_archive.py#L19) (raise) |
| `backup_count_mismatch` | [managed_data.py:64](../../job_applier/managed_data.py#L64) (raise) |
| `backup_integrity_failed` | [managed_data.py:53](../../job_applier/managed_data.py#L53) (raise) |
| `helper_hash_mismatch` | [managed_learning.py:79](../../job_applier/managed_learning.py#L79) (raise) |
| `helper_missing` | [managed_learning.py:77](../../job_applier/managed_learning.py#L77) (raise) |
| `helper_not_found` | [managed_learning.py:102](../../job_applier/managed_learning.py#L102) (raise) |
| `helper_path_not_allowed` | [managed_learning.py:76](../../job_applier/managed_learning.py#L76) (raise) |
| `helper_too_large` | [managed_learning.py:78](../../job_applier/managed_learning.py#L78) (raise) |
| `helper_verification_required` | [managed_learning.py:98](../../job_applier/managed_learning.py#L98) (raise) |
| `helper_version_immutable` | [managed_learning.py:92](../../job_applier/managed_learning.py#L92) (raise) |
| `instance_mismatch` | [managed_data.py:39](../../job_applier/managed_data.py#L39) (raise) |
| `instance_not_initialized` | [managed_data.py:37](../../job_applier/managed_data.py#L37) (raise) |
| `invalid_archive_selection` | [managed_archive.py:11](../../job_applier/managed_archive.py#L11) (raise) |
| `invalid_helper_capability` | [managed_learning.py:84](../../job_applier/managed_learning.py#L84) (raise) |
| `invalid_helper_metadata` | [managed_learning.py:85](../../job_applier/managed_learning.py#L85) (raise) |
| `invalid_helper_reference` | [managed_learning.py:74](../../job_applier/managed_learning.py#L74) (raise) |
| `invalid_learning_scope` | [managed_learning.py:13](../../job_applier/managed_learning.py#L13) (raise) |
| `invalid_lesson` | [managed_learning.py:42](../../job_applier/managed_learning.py#L42) (raise) |
| `invalid_lesson_outcome` | [managed_learning.py:59](../../job_applier/managed_learning.py#L59) (raise) |
| `invalid_lesson_transition` | [managed_learning.py:50](../../job_applier/managed_learning.py#L50) (raise) |
| `invalid_limit` | [managed_learning.py:67](../../job_applier/managed_learning.py#L67) (raise) |
| `invalid_supporting_attempts` | [managed_learning.py:43](../../job_applier/managed_learning.py#L43) (raise) |
| `migration_count_mismatch` | [managed_data.py:94](../../job_applier/managed_data.py#L94) (raise) |
| `migration_integrity_failed` | [managed_data.py:95](../../job_applier/managed_data.py#L95) (raise) |
| `not_procedural_learning` | [managed_learning.py:62](../../job_applier/managed_learning.py#L62) (raise) |
| `operator_fact_review_required` | [managed_learning.py:29](../../job_applier/managed_learning.py#L29) (raise) |
| `procedural_verification_required` | [managed_learning.py:53](../../job_applier/managed_learning.py#L53) (raise) |
| `runtime_not_quiescent` | [managed_archive.py:14](../../job_applier/managed_archive.py#L14) (raise); [managed_archive.py:21](../../job_applier/managed_archive.py#L21) (raise); [managed_data.py:40](../../job_applier/managed_data.py#L40) (raise); [managed_data.py:42](../../job_applier/managed_data.py#L42) (raise) |
| `source_hash_mismatch` | [managed_data.py:70](../../job_applier/managed_data.py#L70) (raise) |
| `source_integrity_failed` | [managed_data.py:34](../../job_applier/managed_data.py#L34) (raise) |
| `source_not_found` | [managed_data.py:27](../../job_applier/managed_data.py#L27) (raise) |
| `symlink_target_refused` | [managed_data.py:15](../../job_applier/managed_data.py#L15) (raise) |
| `unsupported_source_schema` | [managed_data.py:41](../../job_applier/managed_data.py#L41) (raise) |

## G23

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g23).

| Message or reason | Source sites and kind |
|---|---|
| `CDP target has no webSocketDebuggerUrl` | [cdp_client.py:508](../../job_applier/cdp_client.py#L508) (raise) |
| `No CDP page targets found.` | [cdp_client.py:505](../../job_applier/cdp_client.py#L505) (raise) |
| `OwnedProcess is only supported on Windows` | [workspace_process.py:537](../../job_applier/workspace_process.py#L537) (raise) |
| `api_unavailable` | [managed_client.py:21](../../job_applier/managed_client.py#L21) (raise) |
| `breakaway_denied` | [workspace_process.py:760](../../job_applier/workspace_process.py#L760) (raise); [workspace_process.py:809](../../job_applier/workspace_process.py#L809) (raise) |
| `browser_exited_during_start` | [workspace_host.py:160](../../job_applier/workspace_host.py#L160) (raise) |
| `evaluate error: execution_context_unavailable` | [cdp_client.py:319](../../job_applier/cdp_client.py#L319) (raise) |
| `host_connection_lost` | [workspace_host.py:91](../../job_applier/workspace_host.py#L91) (raise) |
| `host_exited_during_launch` | [workspace_process.py:829](../../job_applier/workspace_process.py#L829) (raise) |
| `host_operation_timeout` | [workspace_host.py:88](../../job_applier/workspace_host.py#L88) (raise) |
| `host_start_unconfirmed` | [workspace_host.py:70](../../job_applier/workspace_host.py#L70) (raise) |
| `job_assignment_failed` | [workspace_process.py:669](../../job_applier/workspace_process.py#L669) (raise) |
| `job_setup_failed` | [workspace_process.py:543](../../job_applier/workspace_process.py#L543) (raise); [workspace_process.py:560](../../job_applier/workspace_process.py#L560) (raise) |
| `session_recovering` | [workspace_host.py:79](../../job_applier/workspace_host.py#L79) (raise) |
| `workspace_host_windows_only` | [workspace_host.py:102](../../job_applier/workspace_host.py#L102) (raise) |

## G24

[Purpose, challenge and disposition](STOP_CONDITION_AUDIT.md#g24).

| Message or reason | Source sites and kind |
|---|---|
| `Actual Hermes configuration mismatch` | [native_hermes_session.py:102](../../job_applier/native_hermes_session.py#L102) (raise) |
| `Actual native worker configuration mismatch` | [managed_hermes_worker.py:865](../../job_applier/managed_hermes_worker.py#L865) (raise) |
| `Agent could not complete task` | [agent.py:3275](../../job_applier/agent.py#L3275) (result) |
| `Already processing a job` | [runner.py:98](../../job_applier/runner.py#L98) (result); [runner.py:170](../../job_applier/runner.py#L170) (result) |
| `CAPTCHA/bot-check detected. This site requires human verification.` | [agent.py:289](../../job_applier/agent.py#L289) (inline/embedded reason) |
| `Call start first` | [managed_hermes_worker.py:467](../../job_applier/managed_hermes_worker.py#L467) (raise) |
| `Click an observed option; Enter is reserved to prevent implicit submission` | [managed_hermes_worker.py:690](../../job_applier/managed_hermes_worker.py#L690) (raise) |
| `Deterministic handler reached submit state but confirmation was not verified.` | [agent.py:3019](../../job_applier/agent.py#L3019) (inline/embedded reason) |
| `Empty label text` | [element_handlers.py:797](../../job_applier/element_handlers.py#L797) (inline/embedded reason) |
| `Hermes profile job-apply must reference the canonical repository skill` | [native_hermes_session.py:30](../../job_applier/native_hermes_session.py#L30) (raise) |
| `Manually stopped by user` | [api.py:147](../../job_applier/api.py#L147) (inline/embedded reason) |
| `Matched checkbox has no visible click targets` | [element_handlers.py:1058](../../job_applier/element_handlers.py#L1058) (inline/embedded reason) |
| `No checkbox found matching ` | [element_handlers.py:938](../../job_applier/element_handlers.py#L938) (inline/embedded reason) |
| `No file upload element found (base + fallback failed)` | [element_handlers.py:546](../../job_applier/element_handlers.py#L546) (inline/embedded reason) |
| `No matching dashboard request within wait budget` | [managed_hermes_worker.py:925](../../job_applier/managed_hermes_worker.py#L925) (raise) |
| `Owned page navigated outside claimed application` | [managed_hermes_worker.py:480](../../job_applier/managed_hermes_worker.py#L480) (raise) |
| `Resume file input unavailable` | [managed_hermes_worker.py:658](../../job_applier/managed_hermes_worker.py#L658) (raise) |
| `Stopped by user` | [runner.py:151](../../job_applier/runner.py#L151) (inline/embedded reason); [runner.py:221](../../job_applier/runner.py#L221) (inline/embedded reason) |
| `Subscription route unavailable` | [managed_hermes_worker.py:838](../../job_applier/managed_hermes_worker.py#L838) (raise); [native_hermes_session.py:25](../../job_applier/native_hermes_session.py#L25) (raise) |
| `This application executor requires the headed Simplify browser` | [native_hermes_session.py:22](../../job_applier/native_hermes_session.py#L22) (raise) |
| `Unexpected browser control endpoint` | [managed_hermes_worker.py:384](../../job_applier/managed_hermes_worker.py#L384) (raise) |
| `Unique submit control not found` | [managed_hermes_worker.py:642](../../job_applier/managed_hermes_worker.py#L642) (raise) |
| `Unsupported key` | [managed_hermes_worker.py:295](../../job_applier/managed_hermes_worker.py#L295) (raise) |
| `Unsupported operation` | [managed_hermes_worker.py:759](../../job_applier/managed_hermes_worker.py#L759) (raise) |
| `Unsupported worker model/provider/effort; no automatic fallback` | [managed_hermes_worker.py:35](../../job_applier/managed_hermes_worker.py#L35) (raise) |
| `Upload the approved resume with upload_resume first` | [managed_hermes_worker.py:641](../../job_applier/managed_hermes_worker.py#L641) (raise) |
| `Uploaded resume filename not confirmed on employer page` | [managed_hermes_worker.py:665](../../job_applier/managed_hermes_worker.py#L665) (raise) |
| `absolute_outbox_path_required` | [hermes_adapter.py:40](../../job_applier/hermes_adapter.py#L40) (raise) |
| `active_attempt_requires_reconciliation` | [hermes_adapter.py:100](../../job_applier/hermes_adapter.py#L100) (raise) |
| `awaiting_worker` | [managed.py:327](../../job_applier/managed.py#L327) (raise) |
| `captcha_or_bot_check` | [agent.py:1027](../../job_applier/agent.py#L1027) (inline/embedded reason) |
| `check_page_state: no active page` | [element_handlers.py:1785](../../job_applier/element_handlers.py#L1785) (inline/embedded reason) |
| `credential_fill_verification_failed` | [managed_hermes_worker.py:539](../../job_applier/managed_hermes_worker.py#L539) (raise) |
| `credentials_unavailable` | [managed_hermes_worker.py:523](../../job_applier/managed_hermes_worker.py#L523) (raise); [managed_hermes_worker.py:526](../../job_applier/managed_hermes_worker.py#L526) (raise); [managed_hermes_worker.py:532](../../job_applier/managed_hermes_worker.py#L532) (raise); [managed_hermes_worker.py:534](../../job_applier/managed_hermes_worker.py#L534) (raise) |
| `dismiss_popup: no active page` | [element_handlers.py:682](../../job_applier/element_handlers.py#L682) (inline/embedded reason) |
| `distinct_worker_credentials_required` | [managed_api.py:29](../../job_applier/managed_api.py#L29) (raise) |
| `explicit_credentials_required` | [managed_client.py:12](../../job_applier/managed_client.py#L12) (raise) |
| `handler-managed-cdp-navigation` | [agent.py:2943](../../job_applier/agent.py#L2943) (result) |
| `invalid-eval-response` | [agent.py:203](../../job_applier/agent.py#L203) (result) |
| `invalid_adapter_identity` | [hermes_adapter.py:27](../../job_applier/hermes_adapter.py#L27) (raise); [hermes_adapter.py:29](../../job_applier/hermes_adapter.py#L29) (raise) |
| `invalid_outbox_operation` | [hermes_adapter.py:242](../../job_applier/hermes_adapter.py#L242) (inline/embedded reason) |
| `loopback CDP required` | [managed_hermes_worker.py:275](../../job_applier/managed_hermes_worker.py#L275) (raise) |
| `managed_worker_required` | [database.py:329](../../job_applier/database.py#L329) (raise) |
| `missing-evidence` | [agent.py:3003](../../job_applier/agent.py#L3003) (result) |
| `missing_password_value` | [agent.py:1422](../../job_applier/agent.py#L1422) (inline/embedded reason) |
| `missing_profile_email` | [agent.py:1320](../../job_applier/agent.py#L1320) (inline/embedded reason) |
| `native_auth_required` | [managed_hermes_worker.py:568](../../job_applier/managed_hermes_worker.py#L568) (result) |
| `no-active-page` | [agent.py:133](../../job_applier/agent.py#L133) (result) |
| `no_alternate_login_path` | [agent.py:1072](../../job_applier/agent.py#L1072) (inline/embedded reason) |
| `no_claimed_attempt` | [hermes_plugin.py:191](../../job_applier/hermes_plugin.py#L191) (raise) |
| `no_password_fields` | [agent.py:1428](../../job_applier/agent.py#L1428) (inline/embedded reason) |
| `normal_exit` | [managed_hermes_worker.py:309](../../job_applier/managed_hermes_worker.py#L309) (inline/embedded reason) |
| `not-evaluated` | [agent.py:3197](../../job_applier/agent.py#L3197) (result) |
| `not_found` | [api.py:285](../../job_applier/api.py#L285) (result) |
| `outbox_owner_mismatch` | [hermes_adapter.py:65](../../job_applier/hermes_adapter.py#L65) (raise) |
| `outbox_target_collision` | [hermes_adapter.py:49](../../job_applier/hermes_adapter.py#L49) (raise); [hermes_adapter.py:53](../../job_applier/hermes_adapter.py#L53) (raise) |
| `outbox_unavailable` | [hermes_adapter.py:254](../../job_applier/hermes_adapter.py#L254) (inline/embedded reason) |
| `run_not_accepted` | [hermes_adapter.py:116](../../job_applier/hermes_adapter.py#L116) (raise) |
| `scan_form_fields: no active page` | [element_handlers.py:554](../../job_applier/element_handlers.py#L554) (inline/embedded reason) |
| `smart_fill: no active page` | [element_handlers.py:1836](../../job_applier/element_handlers.py#L1836) (inline/embedded reason) |
| `stale_ref: inventory again` | [managed_hermes_worker.py:594](../../job_applier/managed_hermes_worker.py#L594) (raise) |
| `strong_local_credentials_required` | [managed_api.py:27](../../job_applier/managed_api.py#L27) (raise) |
| `submission_confirmed` | [managed_hermes_worker.py:442](../../job_applier/managed_hermes_worker.py#L442) (inline/embedded reason) |
| `submission_not_authorized` | [managed_hermes_worker.py:636](../../job_applier/managed_hermes_worker.py#L636) (raise) |
| `telemetry_delivery_pending` | [hermes_adapter.py:102](../../job_applier/hermes_adapter.py#L102) (raise); [hermes_adapter.py:113](../../job_applier/hermes_adapter.py#L113) (raise) |
| `toggle_checkbox: label_text is required` | [element_handlers.py:704](../../job_applier/element_handlers.py#L704) (inline/embedded reason) |
| `toggle_checkbox: no active page` | [element_handlers.py:708](../../job_applier/element_handlers.py#L708) (inline/embedded reason) |
| `workday_create_account: no active page` | [element_handlers.py:1387](../../job_applier/element_handlers.py#L1387) (inline/embedded reason) |
| `workday_create_account: no email available in profile data` | [element_handlers.py:1381](../../job_applier/element_handlers.py#L1381) (inline/embedded reason) |
| `workday_create_account: no password available (and fallback is empty)` | [element_handlers.py:1383](../../job_applier/element_handlers.py#L1383) (inline/embedded reason) |
| `worker_credentials_unavailable` | [hermes_plugin.py:44](../../job_applier/hermes_plugin.py#L44) (raise) |
| `worker_exit` | [managed_hermes_worker.py:395](../../job_applier/managed_hermes_worker.py#L395) (inline/embedded reason) |
| `wrong_session` | [hermes_adapter.py:119](../../job_applier/hermes_adapter.py#L119) (raise) |

## Dynamic exception expressions

These include forwarding, runtime messages, validation sentinels and CLI exits. A forwarded exception inherits the disposition of its original cause; CLI exit wrappers are not additional guards.

| Expression | Source |
|---|---|
| `raise AttributeError(name)` | [__init__.py:23](../../job_applier/__init__.py#L23) |
| `raise InterruptedError(reason)` | [agent.py:227](../../job_applier/agent.py#L227) |
| `raise InterruptedError(self._loop_stop_reason)` | [agent.py:291](../../job_applier/agent.py#L291) |
| `raise FileNotFoundError(f'Profile not found: {self.profile_path}')` | [agent.py:479](../../job_applier/agent.py#L479) |
| `raise HTTPException(status_code=404, detail='Job not found')` | [api.py:123](../../job_applier/api.py#L123) |
| `raise HTTPException(status_code=404, detail='Job not found')` | [api.py:132](../../job_applier/api.py#L132) |
| `raise HTTPException(status_code=404, detail='Job not found')` | [api.py:140](../../job_applier/api.py#L140) |
| `raise HTTPException(status_code=404, detail='Job not found')` | [api.py:149](../../job_applier/api.py#L149) |
| `raise HTTPException(status_code=404, detail='Job not found')` | [api.py:158](../../job_applier/api.py#L158) |
| `raise HTTPException(status_code=404, detail='Job not found')` | [api.py:173](../../job_applier/api.py#L173) |
| `raise HTTPException(status_code=400, detail='No job IDs provided')` | [api.py:267](../../job_applier/api.py#L267) |
| `raise HTTPException(status_code=400, detail='Already processing a job')` | [api.py:347](../../job_applier/api.py#L347) |
| `raise HTTPException(status_code=404, detail='Job not found')` | [api.py:1438](../../job_applier/api.py#L1438) |
| `raise SystemExit(main())` | [application_runtime.py:557](../../job_applier/application_runtime.py#L557) |
| `raise ValueError(f'application attempt not found: {attempt_id}')` | [application_tracker.py:266](../../job_applier/application_tracker.py#L266) |
| `raise ValueError(f'application attempt already completed: {attempt_id}')` | [application_tracker.py:291](../../job_applier/application_tracker.py#L291) |
| `raise RuntimeError(f'callFunctionOn: {text[:400]}')` | [bu_compat.py:56](../../job_applier/bu_compat.py#L56) |
| `raise RuntimeError(f'WebSocket handshake failed: {status_line!r}')` | [cdp_client.py:87](../../job_applier/cdp_client.py#L87) |
| `raise RuntimeError(f'evaluate error: {text[:500]}')` | [cdp_client.py:309](../../job_applier/cdp_client.py#L309) |
| `raise RuntimeError(f'evaluate error: {text[:500]}')` | [cdp_client.py:338](../../job_applier/cdp_client.py#L338) |
| `raise FileExistsError(p)` | [managed.py:63](../../job_applier/managed.py#L63) |
| `raise ProtocolError(run['control'])` | [managed.py:329](../../job_applier/managed.py#L329) |
| `raise ValueError()` | [managed_accounts.py:24](../../job_applier/managed_accounts.py#L24) |
| `raise ValueError()` | [managed_api.py:125](../../job_applier/managed_api.py#L125) |
| `raise ValueError()` | [managed_api.py:131](../../job_applier/managed_api.py#L131) |
| `raise ValueError()` | [managed_api.py:133](../../job_applier/managed_api.py#L133) |
| `raise ValueError()` | [managed_cli.py:32](../../job_applier/managed_cli.py#L32) |
| `raise ValueError()` | [managed_cli.py:35](../../job_applier/managed_cli.py#L35) |
| `raise ValueError()` | [managed_cli.py:38](../../job_applier/managed_cli.py#L38) |
| `raise ProtocolError(data.get('error', 'request_failed'))` | [managed_client.py:22](../../job_applier/managed_client.py#L22) |
| `raise FileExistsError(path)` | [managed_data.py:48](../../job_applier/managed_data.py#L48) |
| `raise ValueError()` | [managed_documents.py:109](../../job_applier/managed_documents.py#L109) |
| `raise ValueError()` | [managed_events.py:27](../../job_applier/managed_events.py#L27) |
| `raise ProtocolError(run['control'])` | [managed_events.py:78](../../job_applier/managed_events.py#L78) |
| `raise ValueError()` | [managed_events.py:97](../../job_applier/managed_events.py#L97) |
| `raise ProtocolError(result['error'])` | [managed_hermes_worker.py:224](../../job_applier/managed_hermes_worker.py#L224) |
| `raise ProtocolError(self.package['blocker'])` | [managed_hermes_worker.py:265](../../job_applier/managed_hermes_worker.py#L265) |
| `raise ValueError(f'Anchor href not in same application scope: {fresh_href}')` | [managed_hermes_worker.py:703](../../job_applier/managed_hermes_worker.py#L703) |
| `raise SystemExit(2)` | [managed_hermes_worker.py:922](../../job_applier/managed_hermes_worker.py#L922) |
| `raise ProtocolError('unsupported_' + key)` | [managed_settings.py:28](../../job_applier/managed_settings.py#L28) |
| `raise ValueError()` | [managed_ui.py:56](../../job_applier/managed_ui.py#L56) |
| `raise ValueError()` | [managed_ui.py:57](../../job_applier/managed_ui.py#L57) |
| `raise ValueError('Required Hermes capabilities unavailable: ' + ','.join(sorted(required - names)))` | [native_hermes_session.py:115](../../job_applier/native_hermes_session.py#L115) |
| `raise SystemExit(main())` | [workday_fast.py:433](../../job_applier/workday_fast.py#L433) |
| `raise ProtocolError(result['error']['code'], result['error']['detail'])` | [workspace_host.py:92](../../job_applier/workspace_host.py#L92) |
| `raise SystemExit(main())` | [workspace_host.py:415](../../job_applier/workspace_host.py#L415) |
| `raise OSError(f'Failed to open stdout file {stdout_path}: {err}')` | [workspace_process.py:588](../../job_applier/workspace_process.py#L588) |
| `raise OSError(f'Failed to open stderr file {stderr_path}: {err}')` | [workspace_process.py:609](../../job_applier/workspace_process.py#L609) |
| `raise OSError(f'CreateProcessW failed for {argv}: {err}')` | [workspace_process.py:656](../../job_applier/workspace_process.py#L656) |

## Explicit status outputs

Statuses are not uniformly terminal. The main audit explains waiting, inspection, authentication, uncertain submission and lifecycle transitions.

| Status | Source |
|---|---|
| `aborted` | [hermes_adapter.py:219](../../job_applier/hermes_adapter.py#L219) |
| `applied` | [agent.py:3027](../../job_applier/agent.py#L3027); [agent.py:3295](../../job_applier/agent.py#L3295); [agent.py:3312](../../job_applier/agent.py#L3312); [submission.py:135](../../job_applier/submission.py#L135) |
| `blocked` | [workday_fast.py:358](../../job_applier/workday_fast.py#L358) |
| `clicked` | [managed_hermes_worker.py:589](../../job_applier/managed_hermes_worker.py#L589) |
| `dry_run` | [agent.py:3056](../../job_applier/agent.py#L3056) |
| `error` | [application_runtime.py:554](../../job_applier/application_runtime.py#L554); [migrate.py:43](../../job_applier/migrate.py#L43); [workday_fast.py:429](../../job_applier/workday_fast.py#L429); [workspace_host.py:258](../../job_applier/workspace_host.py#L258) |
| `failed` | [agent.py:2965](../../job_applier/agent.py#L2965); [agent.py:3044](../../job_applier/agent.py#L3044); [agent.py:3275](../../job_applier/agent.py#L3275); [agent.py:3325](../../job_applier/agent.py#L3325); [agent.py:3355](../../job_applier/agent.py#L3355); [managed_hermes_worker.py:813](../../job_applier/managed_hermes_worker.py#L813); [runner.py:155](../../job_applier/runner.py#L155); [runner.py:230](../../job_applier/runner.py#L230) |
| `inspection_required` | [submission.py:82](../../job_applier/submission.py#L82); [workday_auth.py:69](../../job_applier/workday_auth.py#L69) |
| `needs_review` | [agent.py:3020](../../job_applier/agent.py#L3020); [agent.py:3036](../../job_applier/agent.py#L3036); [agent.py:3063](../../job_applier/agent.py#L3063); [agent.py:3258](../../job_applier/agent.py#L3258); [agent.py:3288](../../job_applier/agent.py#L3288); [agent.py:3303](../../job_applier/agent.py#L3303); [agent.py:3334](../../job_applier/agent.py#L3334) |
| `needs_your_answer` | [managed_questions.py:112](../../job_applier/managed_questions.py#L112) |
| `paused` | [api.py:327](../../job_applier/api.py#L327) |
| `quiescent` | [managed.py:456](../../job_applier/managed.py#L456) |
| `resolved` | [managed_hermes_worker.py:745](../../job_applier/managed_hermes_worker.py#L745); [managed_hermes_worker.py:773](../../job_applier/managed_hermes_worker.py#L773) |
| `running` | [api.py:334](../../job_applier/api.py#L334) |
| `skipped` | [migrate.py:32](../../job_applier/migrate.py#L32); [migrate.py:51](../../job_applier/migrate.py#L51) |
| `stopped` | [api.py:341](../../job_applier/api.py#L341); [runner.py:152](../../job_applier/runner.py#L152); [runner.py:222](../../job_applier/runner.py#L222) |
| `submission_unknown` | [submission.py:138](../../job_applier/submission.py#L138); [workspace_host.py:238](../../job_applier/workspace_host.py#L238) |
| `unresolved` | [managed_hermes_worker.py:615](../../job_applier/managed_hermes_worker.py#L615); [managed_hermes_worker.py:630](../../job_applier/managed_hermes_worker.py#L630); [managed_hermes_worker.py:710](../../job_applier/managed_hermes_worker.py#L710); [managed_hermes_worker.py:751](../../job_applier/managed_hermes_worker.py#L751) |
