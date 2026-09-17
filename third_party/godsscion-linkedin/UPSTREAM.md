# LinkedIn Easy Apply source adaptation

Source: [GodsScion/Auto_job_applier_linkedIn](https://github.com/GodsScion/Auto_job_applier_linkedIn)
at **e0b2401a7a7b333eab0b518e80be5285c3ee85c5**. Copyright
2024–2026 Sai Vignesh Golla; MIT text retained in [LICENSE](LICENSE).
The source was downloaded and inspected on September 17, 2026. The file headers
of `runAiBot.py`, `modules/clickers_and_finders.py` and `modules/helpers.py`
carry MIT notices. No Selenium or other donor dependency is imported.

| Donor source | Native adaptation |
|---|---|
| `runAiBot.py:find_bad_word`, `label_has` | `linkedin_easy_apply.py:label_has`, including alphanumeric phrase boundaries |
| `work_authorization_answer`, `match_answer_to_option` | Explicit Jobbot answer lookup, sponsorship/authorization/citizenship separation, exact-first and unique polarity-aware choices; ambiguous and compound questions return to the executor |
| `easy_apply_locators`, `easy_apply_modal_is_open` | `linkedin_observe.js`: positive Easy Apply text/in-app URL/modal evidence and resume-application controls; a generic Apply ID alone is insufficient |
| `answer_questions` | Modal `[data-test-form-element]` discovery, LinkedIn radio titles, select/text/textarea/radio/checkbox handling, preserving previous answers; shared Jobbot refs, writes and read-back replace Selenium |
| `next_button_xpath`, `review_button_xpath`, `submit_button_xpath` | Dialog-scoped native controls; Next excludes page pagination; shared guarded submission replaces the donor click/timestamp outcome |
| `upload_resume` | Existing selected Jobbot asset, hidden native input, filename/size/selected-card evidence; no previous-resume fallback |
| `questions_are_stalled` | An unchanged step returns evidence for executor recovery; no discard, attempt termination or retry policy is copied |
| `modules/clickers_and_finders.py:pick_first_displayed` | Visible-control selection translated into the owned DOM inventory; native Jobbot pointer validation remains authoritative |
| `tests/test_question_matching.py`, `tests/test_runaibot_fixes.py` | Synthetic regression cases for state/States, no/non-citizen, negated choices, separate authorization facts, unknown answers and existing selections |

No browser launcher, runner import, search loop, AI client, generated résumé,
personal configuration, CSV history, account management, PyAutoGUI, anti-detection,
draft discard, or follow-company policy was copied. Local runtime/attempt history,
writer serialization, approved profile/saved answers and submission settings remain
authoritative. The native helper does not change the bridge or its receipts.
