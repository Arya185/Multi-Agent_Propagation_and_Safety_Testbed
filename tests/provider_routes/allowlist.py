"""Explicit provider-route allow-list (v2.3.56, Stage 4C).

Every file the scanner (``route_scanner``) finds with a network-capable import, a reference to the provider client
module or class, a ``.complete(`` call, an endpoint literal, dynamic code loading or a ``curl``/``wget`` word MUST have
exactly one entry here, and every ``.ipynb`` file must have one whether or not it has findings. There are no
directory, glob or wildcard entries: one entry names one file by its exact repository-relative POSIX path.

An entry has exactly these fields:
  path            the file (exists, relative, no wildcard characters, no ``..``)
  category        what kind of file it is: source | script | notebook | test | test_support
  purpose         what the file is for (a sentence)
  classification  guarded_experiment | diagnostic_only | test_only | non_provider_network
  kinds           the EXACT set of scanner finding kinds the file is allowed to contain (a file that gains a new kind,
                  for example a first ``requests`` import, fails until a reviewer edits its entry)
  justification   why the file may contain those findings

CLASSIFICATIONS
  guarded_experiment   production code under src/maps that is part of the guarded research path
  diagnostic_only      a labelled diagnostic script under scripts/; never an experiment run, never an analysis input
  test_only            a test or test helper under tests/; real provider calls are impossible there (fake transport,
                       socket tripwire, dummy credentials; see ``test_pr_real_client_guard``)
  non_provider_network network code that does not reach the provider (none exist today)

This list authorises the PRESENCE of these code paths in the repository; it does not authorise running any of them.
It does not validate ``api.base_url`` (a Stage 4E item) and does not make a live run safe or approved.
"""

from __future__ import annotations

CATEGORIES = ("source", "script", "notebook", "test", "test_support")
CLASSIFICATIONS = ("guarded_experiment", "diagnostic_only", "test_only", "non_provider_network")
FIELDS = ("path", "category", "purpose", "classification", "kinds", "justification")
# the directory a classification may live under (checked by the validator; entries are still per file)
CLASSIFICATION_ROOTS = {
    "guarded_experiment": ("src/maps/",),
    "diagnostic_only": ("scripts/",),
    "test_only": ("tests/",),
    "non_provider_network": ("src/maps/", "scripts/"),
}


def _entry(path, category, classification, kinds, purpose, justification):
    return {
        "path": path, "category": category, "purpose": purpose, "classification": classification,
        "kinds": tuple(sorted(kinds)), "justification": justification,
    }


_FAKE_NET = "dummy credentials, a fake transport/session and a socket tripwire; no provider request is possible"

ALLOWLIST: tuple[dict, ...] = (
    # ---- guarded experiment code --------------------------------------------------------------------------
    _entry(
        "src/maps/llm_client.py", "source", "guarded_experiment",
        ("endpoint_literal", "network_import", "provider_client_ref"),
        "The OpenRouterClient implementation and the LLMClient protocol: the only module that builds provider requests.",
        "Sole production place that imports the HTTP library and forms the provider endpoint path. Redirects are disabled "
        "and a disabled client raises before any request. Production code constructs it only in scripts/test_openrouter.py "
        "(diagnostic) until Stage 4E wires the guarded executor. The base_url it is given is NOT validated in this stage.",
    ),
    _entry(
        "src/maps/runs/endpoint_policy.py", "source", "guarded_experiment",
        ("endpoint_literal",),
        "Endpoint validator: the configured base URL must be exactly the approved provider endpoint (host openrouter.ai, path /api/v1).",
        "Holds the approved host and path as reviewed constants and parses a string only: no network, environment or credential "
        "access, and no URL echoed in errors. It runs in the CLI preflight before any credential or client. Hostname validation "
        "does not prevent DNS or proxy redirection (PR4-PROXY is a separate, pending decision).",
    ),
    _entry(
        "src/maps/runs/live_budget.py", "source", "guarded_experiment",
        ("complete_call", "provider_client_module"),
        "BudgetedClient: enforces the live policy around every complete() call of the client it wraps.",
        "Calls complete() only on the client the guarded live executor hands it and counts and bounds every request; it "
        "imports maps.llm_client for the protocol and error types and never constructs a provider client.",
    ),
    _entry(
        "src/maps/experiments/receiver.py", "source", "guarded_experiment",
        ("complete_call", "provider_client_module"),
        "Receiver experiment runner and CLI; run_episode calls client.complete() on the client it is given.",
        "The runner calls complete() on an injected client (MockClient on the only runnable CLI path). Since Stage 4C the "
        "CLI live branch refuses before any credential, client, run directory or network use, and the module no longer "
        "imports the provider client class; it imports maps.llm_client only for the LLMClient type.",
    ),
    # ---- diagnostic script ----------------------------------------------------------------------------------
    _entry(
        "scripts/test_openrouter.py", "script", "diagnostic_only",
        ("complete_call", "provider_client_module", "provider_client_ref"),
        "Single-request OpenRouter connectivity diagnostic, labelled 'DIAGNOSTIC — NOT AN EXPERIMENT RUN'.",
        "Standalone script outside the research execution path: needs --confirm-spend and api.enabled=true, forces zero "
        "retries, makes at most one request, writes no files and redacts the key. Not an experiment run and not an "
        "analysis input. api.base_url is not validated (Stage 4E item).",
    ),
    # ---- tests that build the real client (PR6: dummy credentials, fake transport, socket tripwire) ---------
    _entry(
        "tests/test_client.py", "test", "test_only",
        ("complete_call", "endpoint_literal", "network_import", "provider_client_module", "provider_client_ref"),
        "Offline tests of OpenRouterClient behaviour.",
        f"Builds the real client with {_FAKE_NET}; requests is imported for its exception types only.",
    ),
    _entry(
        "tests/live_executor/test_le_accounting.py", "test", "test_only",
        ("endpoint_literal", "network_import", "provider_client_module", "provider_client_ref"),
        "Live-executor accounting with the real client class over a fake adapter.",
        f"Builds the real client with {_FAKE_NET}.",
    ),
    _entry(
        "tests/live_policy/test_lp_redirect_hardening.py", "test", "test_only",
        ("complete_call", "endpoint_literal", "network_import", "provider_client_module", "provider_client_ref"),
        "Redirect-hardening tests of OpenRouterClient.",
        f"Builds the real client with {_FAKE_NET}.",
    ),
    # ---- tests that refuse or spy on the real client ----------------------------------------------------------
    _entry(
        "tests/live_executor/test_le_boundaries.py", "test", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Boundary tests of the live executor.",
        "Replaces OpenRouterClient.__init__ with a refusal and blocks sockets; the real client is never constructed.",
    ),
    _entry(
        "tests/live_executor/test_le_interrupt.py", "test", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Interrupt-handling tests of the live executor.",
        "Replaces OpenRouterClient.__init__ with a refusal and blocks sockets; the real client is never constructed.",
    ),
    _entry(
        "tests/live_executor/test_le_routing.py", "test", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Routing tests of the live executor.",
        "Replaces OpenRouterClient.__init__ with a refusal and blocks sockets; the real client is never constructed.",
    ),
    _entry(
        "tests/live_executor/test_le_stops.py", "test", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Policy-stop tests of the live executor.",
        "Replaces OpenRouterClient.__init__ with a refusal and blocks sockets; the real client is never constructed.",
    ),
    _entry(
        "tests/live_policy/test_lp_boundaries.py", "test", "test_only",
        ("complete_call", "network_import", "provider_client_module", "provider_client_ref"),
        "Static and runtime boundary tests of the live policy modules.",
        "Replaces OpenRouterClient.__init__ with a refusal and blocks sockets; complete() is called on fake clients only.",
    ),
    _entry(
        "tests/run_executor/test_re_lifecycle.py", "test", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Lifecycle tests of the shared run executor.",
        "Replaces OpenRouterClient.__init__ with a refusal and blocks sockets; the real client is never constructed.",
    ),
    _entry(
        "tests/cli_safety/cs_support.py", "test_support", "test_only",
        ("endpoint_literal", "network_import", "provider_client_module", "provider_client_ref"),
        "Harness for the CLI safety tests.",
        "Installs a recording OpenRouterClient double that raises if constructed, a key-lookup spy, a fake dotenv module "
        "and a socket tripwire; the real client and real credentials are never used.",
    ),
    _entry(
        "tests/cli_safety/test_cs_executor.py", "test", "test_only",
        ("provider_client_ref",),
        "CLI-to-executor integration and static structure tests of receiver.main.",
        "Names OpenRouterClient only in a static check that receiver.main does not call it.",
    ),
    # ---- tests that block sockets (network_import = importing socket to patch it) ---------------------------
    _entry(
        "tests/run_executor/test_re_executor.py", "test", "test_only", ("network_import",),
        "Tests of the mock run executor.", "Imports socket to install a tripwire; makes no connection.",
    ),
    _entry(
        "tests/run_executor/test_re_hashes.py", "test", "test_only", ("network_import",),
        "Hash-binding tests of the executor.", "Imports socket to install a tripwire; makes no connection.",
    ),
    _entry(
        "tests/run_executor/test_re_pipeline.py", "test", "test_only", ("network_import",),
        "Pipeline tests over executor output.", "Imports socket to install a tripwire; makes no connection.",
    ),
    _entry(
        "tests/pipeline_integration/test_pi_pipeline.py", "test", "test_only", ("network_import",),
        "Pipeline integration tests.", "Imports socket to install a tripwire; makes no connection.",
    ),
    # ---- tests/helpers that call complete() on fake clients only ---------------------------------------------
    _entry(
        "tests/live_policy/test_lp_accounting.py", "test", "test_only", ("complete_call", "provider_client_module"),
        "Budget accounting tests.", "Calls complete() on fake clients through BudgetedClient; imports maps.llm_client for types.",
    ),
    _entry(
        "tests/live_policy/test_lp_budget.py", "test", "test_only", ("complete_call",),
        "Budget wrapper tests.", "Calls complete() on fake clients through BudgetedClient.",
    ),
    _entry(
        "tests/live_policy/test_lp_usage.py", "test", "test_only", ("complete_call",),
        "Usage-accounting tests.", "Calls complete() on fake clients through BudgetedClient.",
    ),
    _entry(
        "tests/live_executor/le_support.py", "test_support", "test_only", ("complete_call",),
        "Fake clients and runners for the live-executor tests.", "A fake runner calls complete() on the fake or wrapped fake client.",
    ),
    _entry(
        "tests/run_executor/le_bridge.py", "test_support", "test_only", ("complete_call",),
        "Bridge from the executor tests to the live-executor fakes.", "A fake runner calls complete() on a fake client.",
    ),
    _entry(
        "tests/run_integrity/ri_gate_support.py", "test_support", "test_only", ("complete_call",),
        "Support code that builds real gate-test runs from fakes.", "Calls complete() on a fake client wrapped by BudgetedClient.",
    ),
    _entry(
        "tests/synthetic/test_syn_prompt_parse.py", "test", "test_only", ("complete_call",),
        "Synthetic prompt and parse tests.", "Calls complete() on MockClient.",
    ),
    # ---- tests with endpoint literals or dynamic loading of repository code ----------------------------------
    _entry(
        "tests/run_integrity/test_ri_provenance.py", "test", "test_only", ("endpoint_literal",),
        "Provenance reader tests.",
        "Writes a fake .git/config containing an example.invalid URL to prove the reader never opens git config; no request.",
    ),
    _entry(
        "tests/run_executor/re_scenarios.py", "test_support", "test_only", ("dynamic_load",),
        "Scenario definitions for the mock lifecycle snapshot.", "Uses __import__('re') to compile a regular expression; loads no repository or network code.",
    ),
    _entry(
        "tests/synthetic/test_syn_golden_sensitivity.py", "test", "test_only", ("dynamic_load",),
        "Golden-sensitivity tests.", "Loads repository tool scripts from fixed repository paths with importlib to test them; no network.",
    ),
    _entry(
        "tests/synthetic/test_syn_provenance.py", "test", "test_only", ("dynamic_load",),
        "Synthetic provenance tests.", "Loads repository tool scripts from fixed repository paths with importlib to test them; no network.",
    ),
    _entry(
        "tests/synthetic/test_syn_write_guard.py", "test", "test_only", ("dynamic_load",),
        "Tests of the write-guard tool script.", "Loads repository tool scripts from fixed repository paths with importlib to test them; no network.",
    ),
    # ---- this stage's tests (they name the patterns they detect, or tripwire the sockets) -------------------
    _entry(
        "tests/provider_routes/allowlist.py", "test_support", "test_only", ("endpoint_literal", "provider_client_ref", "shell_fetch"),
        "This allow-list: it names the provider client class and the curl/wget kind in its entries.",
        "Data only: strings describing the other allow-listed files; nothing here imports or runs anything.",
    ),
    _entry(
        "tests/provider_routes/pr6_check.py", "test_support", "test_only", ("provider_client_ref",),
        "PR6 detector: finds tests that build the real client without a fake transport or tripwire.",
        "Names the class only as a pattern to look for in other test sources; it parses text and never imports or runs it.",
    ),
    _entry(
        "tests/provider_routes/test_pr_allowlist.py", "test", "test_only", ("network_import",),
        "Allow-list validation tests on synthetic trees.", "Imports socket to install a tripwire; makes no connection.",
    ),
    _entry(
        "tests/provider_routes/test_pr_real_client_guard.py", "test", "test_only", ("endpoint_literal",),
        "PR6 regression tests for the real-client detector.",
        "Holds the provider host name only as a pattern for checking that no other test names it; makes no request.",
    ),
    _entry(
        "tests/provider_routes/test_pr_receiver.py", "test", "test_only",
        ("endpoint_literal", "network_import", "provider_client_module", "provider_client_ref"),
        "Tests that receiver --live is refused before anything else.",
        "Replaces OpenRouterClient.__init__, the key lookup, the run guard, the runner and the executors with tripwires, "
        "blocks sockets and watches for .env opens; the real client is never constructed.",
    ),
    _entry(
        "tests/provider_routes/test_pr_scanner.py", "test", "test_only",
        ("endpoint_literal", "network_import", "provider_client_ref", "shell_fetch"),
        "Scanner behaviour tests on synthetic snippets.",
        "Imports socket to install a tripwire; the snippets are parsed as text and never executed. Pattern names appear "
        "only in assertions about what the scanner finds.",
    ),
    _entry(
        "tests/provider_routes/test_pr_script.py", "test", "test_only",
        ("endpoint_literal", "network_import", "provider_client_ref"),
        "Offline tests of the diagnostic script scripts/test_openrouter.py.",
        f"Runs the script's real client through its session seam with {_FAKE_NET}, plus a fake dotenv so no .env is read.",
    ),
    # ---- Stage 4D policy-source tests (synthetic inputs, tripwires, no provider client) --------------------------------
    _entry(
        "tests/policy_source/ps_support.py", "test_support", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Builders and the autouse tripwire fixture for the policy-source tests.",
        "Patches OpenRouterClient.__init__, the key lookup, the run guard, dotenv, sockets and .env opens to raise; the real "
        "client is never constructed and no credential or environment value is read.",
    ),
    _entry(
        "tests/policy_source/test_ps_scope.py", "test", "test_only", ("endpoint_literal",),
        "Scope-binding tests for the policy source.",
        "A URL literal appears only as an ignored api.base_url value in a temporary config to prove the design digest excludes "
        "it; nothing is requested.",
    ),
    _entry(
        "tests/policy_source/test_ps_digest.py", "test", "test_only", ("endpoint_literal",),
        "Digest and canonical-form tests for the policy source.",
        "A URL literal appears only as an ignored api.base_url value in a temporary config to prove the design digest excludes "
        "it; nothing is requested.",
    ),
    _entry(
        "tests/policy_source/test_ps_preflight.py", "test", "test_only", ("provider_client_ref",),
        "Side-effect and static boundary tests for the policy source.",
        "Names the provider client class only in a list of names the policy-source module must not contain.",
    ),
    # ---- Stage 4E tests (fake factories, tripwires, synthetic inputs) --------------------------------------------------
    _entry(
        "tests/endpoint_policy/test_ep_validator.py", "test", "test_only",
        ("complete_call", "endpoint_literal", "network_import", "provider_client_module", "provider_client_ref"),
        "Endpoint validator tests, including a check of the URL the real client posts to.",
        f"Builds the real client with {_FAKE_NET}; name resolution is also blocked. The approved URL is built from the "
        "validator's own constants.",
    ),
    _entry(
        "tests/live_cli/lc_support.py", "test_support", "test_only", ("endpoint_literal",),
        "Builders for the live-CLI flow tests (synthetic config, policy and scripted fake client).",
        "Assembles the approved URL string from the validator's constants as test configuration; nothing connects.",
    ),
    _entry(
        "tests/live_cli/test_lc_flow.py", "test", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Downstream live flow, exit codes, provenance and stop semantics through an injected fake client factory.",
        "Patches OpenRouterClient.__init__, the key lookup and dotenv to raise and blocks sockets; the real client is never "
        "constructed and no credential is read.",
    ),
    _entry(
        "tests/live_cli/test_lc_preflight.py", "test", "test_only",
        ("endpoint_literal", "network_import", "provider_client_module", "provider_client_ref"),
        "CLI preflight order and safety tests for --live, ending in the final refusal.",
        "Tripwires on the key lookup, .env opens, the client constructor, the run guard, the runner and both executors, plus "
        "blocked sockets; nothing real is reached.",
    ),
    _entry(
        "tests/live_executor/test_le_policy_record.py", "test", "test_only",
        ("network_import", "provider_client_module", "provider_client_ref"),
        "Tests of the optional policy_record parameter of the live executor.",
        "Replaces OpenRouterClient.__init__ with a refusal and blocks sockets; a scripted fake client is used.",
    ),
    # ---- this stage's scanner (its own patterns are code) ----------------------------------------------------
    _entry(
        "tests/provider_routes/route_scanner.py", "test_support", "test_only",
        ("endpoint_literal", "provider_client_ref", "shell_fetch"),
        "The provider-route scanner.",
        "Its detection patterns (the provider class name, URL schemes, curl/wget) are string literals; the scanner only "
        "reads and parses text and never imports, executes or fetches anything.",
    ),
)
