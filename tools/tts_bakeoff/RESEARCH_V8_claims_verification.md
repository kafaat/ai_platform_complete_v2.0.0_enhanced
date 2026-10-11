# Claims verification against primary sources — research_v8

Checked: 2026-10-04. Method: PyPI JSON API, sdist/wheel download from files.pythonhosted.org, shallow `git clone --depth 1` of each GitHub repo into `research_v8/repos/` (github.com git transport worked; github.com HTML/API was gated by the session proxy, so GitHub issue pages were read via WebFetch). Blocked: packages.debian.org, bugs.debian.org, lists.debian.org, docs.gitlab.com (GitLab docs read from their Markdown source on gitlab.com instead).

Commits inspected (HEAD of default branch at clone time):

| Repo | Commit | Commit date |
|---|---|---|
| noxdafox/pebble | 7bf3d2e335f9 | 2026-09-26 |
| python-jsonschema/jsonschema | 51cd75e399c7 | 2026-09-28 |
| containers/bubblewrap | 0f8073dd9b54 | 2026-09-25 |
| google/nsjail | 4ff54a6e0d5b | 2026-10-02 |
| SYSTRAN/faster-whisper | 7b99be5376b4 | 2026-10-01 |
| NVIDIA/NeMo-text-processing | ddadfb2a38d2 | 2026-09-18 |
| wenet-e2e/WeTextProcessing | 039007e6b819 | 2026-07-29 |
| CAMeL-Lab/camel_tools | be79ca9fc493 | 2026-06-08 |
| inworld-ai/open-tts-eval | 3cf4b2d | 2026-09-09 |

## Summary table

| # | Claim | Verdict | Key correction or caveat |
|---|---|---|---|
| 1 | Pebble `ProcessPool.schedule(fn, args, timeout)`; on timeout the worker is terminated and replaced; `initializer`, `max_tasks` | **VERIFIED** | Stop = `Process.terminate()` (SIGTERM to the **worker PID only**), wait 3 s, then `os.kill(pid, SIGKILL)`. There is **no process-group kill** (no setsid/killpg anywhere), so **grandchildren survive**. The docs say so. The replacement worker re-runs `initializer`, so the model is reloaded after every timeout. v5.2.2 (2026-09-04), LGPL-3.0 |
| 2 | jsonschema supports 2020-12 + if/then/else | **VERIFIED** | v4.26.0 (2026-01-07), MIT. Deps: attrs, jsonschema-specifications, referencing, rpds-py. `format` is only enforced if you pass a `format_checker` |
| 3 | Bubblewrap: empty tmpfs root, --ro-bind/--bind, --unshare-net, --die-with-parent, --new-session, --unshare-all; needs userns **or setuid** | **PARTLY** (the setuid part is **CONTRADICTED**) | Setuid support was **removed in 0.12.0 (2026-08-26)**. bwrap now `die`s if setuid. It needs unprivileged user namespaces. `--unshare-all` uses the *try* variant for user and cgroup namespaces. License is now **LGPL-2.1-or-later** (it was LGPL-2.0+ before 0.12.0). Latest release 0.13.0 (2026-09-22) |
| 4 | NsJail: namespaces + rlimits + seccomp-bpf (Kafel); cgroup v1 & v2; Debian/Ubuntu packaged | **PARTLY** | Features: VERIFIED (`--cgroup_mem_max`, `--cgroup_pids_max`, `--cgroup_cpu_ms_per_sec`, `--use_cgroupv2`, `--detect_cgroupv2`, `--cgroupv2_mount`). Apache-2.0. Latest tag 3.6. **Not in Ubuntu** (packages.ubuntu.com: "no results"; Launchpad: "no current release"). Debian site blocked. A search snippet shows ITP #964199 (2020) still pending, so it is effectively **not packaged**. The upstream repo ships its own `debian/` directory |
| 5 | faster-whisper `transcribe` returns a lazy generator; `local_files_only`/local dir | **VERIFIED**, with a nuance | Decoding is lazy. But audio decode, VAD, the feature extractor and **language detection (an encoder pass) run eagerly** inside `transcribe()`. Passing a directory skips the Hub. **If `tokenizer.json` is missing from that directory, it calls `Tokenizer.from_pretrained("openai/whisper-tiny")`, which is a network fetch.** v1.2.1 (2025-10-31), MIT |
| 6 | NeMo TN/ITN has Arabic | **VERIFIED** (both TN and ITN) | ar classes: Cardinal, Decimal, Fraction, Measure, Money, Word (+Punctuation in ITN only), plus ClassifyFst/VerbalizeFst/VerbalizeFinalFst. **No** date/time/ordinal/telephone/electronic/whitelist for ar. Requires `pynini==2.1.6.post1` (pinned). Apache-2.0. v1.2.0 (2026-06-05) |
| 7 | WeTextProcessing `normalize_with_mapping` | **PARTLY** | It exists on **master only**. It was added in commit 99dc9da (2026-07-29) and is **absent from the PyPI 1.2.0 wheel** (2026-06-10). Languages: zh, en, ja (TN and ITN). **No Arabic.** Apache-2.0 (LICENSE file; PyPI metadata has no license field) |
| 8 | CAMeL Tools: morphology/disambiguation; data download | **VERIFIED** + license caveat | Code is MIT. Data comes from `camel_data -i light/defaults/all`, hosted on **GitHub releases of CAMeL-Lab/camel-tools-data** (catalogue on raw.githubusercontent.com). **The default MSA morphology DB `calima-msa-r13` and its MLE disambiguator are GPL v2.** `calima-msa-s31` is LDC-licensed. BERT models: MIT or AraBERT license. v1.6.0 (2026-06-08), torch is a hard dependency |
| 9 | open-tts-eval | **VERIFIED exists** | github.com/inworld-ai/open-tts-eval, MIT, last commit 2026-09-09 (created 2026-08-25, 4 commits). WER/CER via **jiwer + faster-whisper** ASR. Audio checks: silence, clipping, loudness/RMS, tail-click, duration, speech-rate. Optional NISQAv2 and ECAPA. Normalization is **English-only** (`english-basic`, optional NeMo, plugin hook). Not on PyPI. Version 0.1.0 |
| 10 | GitLab docs mention Bubblewrap in a sandboxed execution environment | **PARTLY** | The GitLab sandbox is **Anthropic Sandbox Runtime (SRT)**. bwrap is listed as an SRT dependency and as a pinned image component, not as GitLab's own sandbox. The docs also say it **fails open** ("flow runs directly with a warning") |
| 11 | whisper.cpp silence hallucination; faster-whisper local-dir recommendations | **VERIFIED** (whisper.cpp) / **PARTLY** (faster-whisper) | whisper.cpp #1724 and Discussion #2286 confirmed. For faster-whisper, offline/local-dir problems are confirmed (#116, #1430, #945, Disc. #1173), but I found no maintainer post recommending an explicit local dir. Docs PR #1554 was **closed unmerged** (2026-10-04). The local-directory recommendation is in the README itself |
| — | pebble & jsonschema installable from PyPI | **VERIFIED** | Both have a py3-none-any wheel and an sdist, not yanked, `requires_python >=3.10` |

---

## 1. Pebble

- PyPI: `pebble` **5.2.2**, uploaded 2026-09-04T13:15:21. Classifier `GNU Library or Lesser General Public License (LGPL)`. No runtime dependencies. `requires_python >=3.10`.
- License file: `pebble-5.2.2/LICENSE` is "GNU LESSER GENERAL PUBLIC LICENSE Version 3, 29 June 2007".
- Source: sdist `pebble-5.2.2.tar.gz`. Master (7bf3d2e) differs only in type hints.

**`schedule` signature.** `pebble/pool/process.py:105-121` (5.2.2):
```python
def schedule(self, function, args=(), kwargs={}, timeout=None) -> ProcessFuture[T]:
    """... *timeout* is an integer, if expires the task will be terminated
    and *Future.result()* will raise *TimeoutError*.
```

**`max_tasks` / `initializer`.** `pebble/pool/process.py:54-58, 65-73`: `ProcessPool(max_workers=cpu_count(), max_tasks=0, initializer=None, initargs=(), context=multiprocessing)`. The docstring says "If max_tasks is a number greater than zero, each worker will be restarted after performing an equal amount of tasks. initializer ... will be called every time a worker is started". The worker runs the initializer at `process.py:481-483` (`if not run_initializer(...): process_exit(1)`). It runs **once per worker process**, so it suits model loading, but it **runs again for every replacement worker**, for example after each timeout.

**Timeout path.**
- `process.py:369-371`: `if task.timeout and task.started: return time.time() - task.timestamp > task.timeout`. The clock starts when the worker acknowledges the task (`task.timestamp = time.time()` at :329), not when it is enqueued.
- `process.py:262-268`: `for task in self.task_manager.timeout_tasks(): if self.worker_manager.maybe_stop_worker(task.worker_id): ... TimeoutError("Task timeout", task.timeout)`.
- `process.py:459-470`, `maybe_stop_worker`: takes the worker channel lock **non-blocking**. If the lock is busy it returns False and the next 0.1 s loop retries. Otherwise it calls `stop_process(worker)`.
- Replacement: `process.py:277-282`, `update_workers()` → `self.worker_manager.create_workers()` refills to `max_workers`.

**How the worker is stopped.** `pebble/common/process.py:50-63`:
```python
def stop_process(process: multiprocessing.Process):
    """Does its best to stop the process."""
    process.terminate()
    process.join(CONSTS.term_timeout)
    if process.is_alive() and os.name != "nt" and process.pid is not None:
        try:
            os.kill(process.pid, signal.SIGKILL)
            process.join()
        except OSError:
            return
```
- `pebble/common/types.py:170-172`: `term_timeout: float = 3`. "On UNIX once a SIGTERM signal is issued to a process, the amount of seconds to wait before issuing a SIGKILL signal."
- `multiprocessing.Process.terminate()` → CPython `Lib/multiprocessing/popen_fork.py:56-57`: `def terminate(self): self._send_signal(signal.SIGTERM)`, which does `os.kill(self.pid, sig)` (:49).
- In the worker, `process.py:476-477`: `signal.signal(signal.SIGTERM, process_exit)`. `process_exit` (`common/process.py:99-102`) calls `multiprocessing.util._exit_function()` and then `os._exit()`. A Python signal handler only runs between bytecodes, so a worker stuck inside a long C call (for example CTranslate2 or ONNX) won't act on SIGTERM and will get the SIGKILL after 3 s.
- `grep -rn "start_new_session|setsid|setpgrp|killpg" pebble/` finds **nothing**. Signals target the worker PID only, and **grandchild processes are not killed.**
- Docs confirm this, at `doc/index.rst:282-285` ("Pool workers termination"): "When a `Future` is cancelled or the underlying task times out or the `ProcessPool` is stopped, the affected worker processes are terminated. As a consequence, scheduled functions which allocate resources such as temporary files or child processes are to be handled carefully. If a worker process is terminated abruptly due to the above reason, such resources will not be relinquished."
- Side note: the README pool example (`README.rst:99-101`) calls `pool.schedule(function, index, bar=1, timeout=...)`. That does not match the signature (`args=` must be an iterable and there is no `bar` kwarg), so don't copy it.

## 2. jsonschema

- PyPI **4.26.0**, uploaded 2026-01-07. `license_expression: MIT`. `requires_python >=3.10`.
- `pyproject.toml:12-13`: `license = "MIT"`, `license-files = ["COPYING"]`. `COPYING` starts "Copyright (c) 2013 Julian Berman / Permission is hereby granted, free of charge…" (MIT).
- Runtime dependencies (`pyproject.toml` `dependencies`): `attrs>=22.2.0`, `jsonschema-specifications>=2023.03.6`, `referencing>=0.28.4`, `rpds-py>=0.25.0`. rpds-py is a Rust extension with binary wheels. Optional extras are `format` and `format-nongpl` (fqdn, idna, isoduration, jsonpointer, rfc3339-validator, rfc3987 or rfc3986-validator/rfc3987-syntax, uri-template, webcolors).
- `README.rst:62`: "Full support for Draft 2020-12, Draft 2019-09, Draft 7, Draft 6, Draft 4 and Draft 3".
- `jsonschema/validators.py:814-832`: `Draft202012Validator = create(meta_schema=SPECIFICATIONS.contents("https://json-schema.org/draft/2020-12/schema"), validators={..., "if": _keywords.if_, ...})`.
- `jsonschema/_keywords.py:382-389`: `def if_(validator, if_schema, instance, schema): if validator.evolve(schema=if_schema).is_valid(instance): if "then" in schema: ... descend(instance, then, schema_path="then") elif "else" in schema: ... descend(instance, else_, schema_path="else")`.
- Caveat: `format` is not checked unless you pass a `format_checker`. `docs/validate.rst:189` shows `format_checker=Draft202012Validator.FORMAT_CHECKER`.

## 3. Bubblewrap

- License: `COPYING` is "GNU LESSER GENERAL PUBLIC LICENSE Version 2.1". `NEWS.md` (0.12.0): "The license has been updated from LGPL 2.0 (or later) to LGPL 2.1 (or later)."
- Releases (`NEWS.md`): 0.13.0 released 2026-09-22; 0.12.0 released 2026-08-26; 0.11.2 2026-04-23; 0.11.0 2024-10-30. `meson.build:4` says `0.13.1` (unreleased).
- Empty tmpfs root, from `README.md:98-103`: "bubblewrap works by creating a new, completely empty, mount namespace where the root is on a tmpfs that is invisible from the host, and will be automatically cleaned up when the last process exits. You can then use commandline options to construct the root filesystem…"
- `README.md:131-133`: "bubblewrap always creates a new mount namespace, and the user can specify exactly what parts of the filesystem should be visible in the sandbox. Any such directories you specify mounted `nodev` by default, and can be made readonly."
- Usage strings in `bubblewrap.c`:
  - :298 `--unshare-all  Unshare every namespace we support by default`
  - :299 `--share-net`
  - :304 `--unshare-net  Create new network namespace`
  - :322 `--bind SRC DEST`
  - :326 `--ro-bind SRC DEST  Bind mount the host path SRC readonly on DEST`
  - :353 `--new-session  Create a new terminal session`
  - :354 `--die-with-parent  Kills with SIGKILL child process (COMMAND) when bwrap or bwrap's parent dies.`
  - Implementation at :373: `prctl (PR_SET_PDEATHSIG, SIGKILL, ...)`.
- `--unshare-all` detail, `bubblewrap.c:1867-1876`: "we use the --try variants of user and cgroup, since we want to support systems/kernels without support for those". It sets `opt_unshare_user_try = ipc = pid = uts = cgroup_try = net = true`.
- `--new-session` is security-relevant, per `README.md:162-164`: "If you are not filtering out `TIOCSTI` commands using seccomp filters, argument `--new-session` is needed to protect against out-of-sandbox command execution (see CVE-2017-5226)."
- **"Requires user namespaces or setuid": CONTRADICTED for current versions.**
  - `README.md:20-22`: "Historically, bubblewrap also supported a setuid mode for systems where unprivileged user namespaces were not supported. However, this has been removed."
  - `NEWS.md` (0.12.0): "This version removes the support for building a setuid bubblewrap… basically all modern linux distributions now support unprivileged user namespaces to some extent."
  - `bubblewrap.c:798-802`: `/* Historically we supported this, but now we only do user namespaces */ die ("setuid use of bubblewrap is not supported");`
  - Older distro builds (< 0.12) may still be setuid.

## 4. NsJail

- License: `LICENSE` is Apache License 2.0. Latest tag **3.6** (from `git ls-remote --tags`).
- `README.md:3`: "Linux process isolation tool using namespaces, resource limits, and seccomp-bpf syscall filters."
- `:8`: "Namespace isolation: UTS, MOUNT, PID, IPC, NET, USER, CGROUPS, TIME".
- `:11`: "Syscall filtering: Kafel seccomp-bpf policies".
- `:13`: "Cgroup integration: Memory, PID, CPU, net_cls control (v1 and v2)".
- `README.md:91-98` covers `--rlimit_as`, `--rlimit_cpu`, `--rlimit_nofile`, `-P/--seccomp_policy`, `--seccomp_string`. `:292-296` shows an example with `--cgroup_mem_max`, `--cgroup_pids_max`, `--cgroup_cpu_ms_per_sec`.
- Flags in `cmdline.cc`:
  - :152 `cgroup_mem_max` "Maximum number of bytes to use in the group"
  - :155 `cgroup_mem_mount` (default `/sys/fs/cgroup/memory`, v1)
  - :157 `cgroup_pids_max`
  - :163 `cgroup_cpu_ms_per_sec`
  - :166 `cgroupv2_mount` (default `/sys/fs/cgroup`)
  - :167 `use_cgroupv2` "Use cgroup v2"
  - :168 `detect_cgroupv2` "Use cgroupv2, if it is available."
  - Separate implementations: `cgroup.cc` (v1) and `cgroup2.cc` (v2).
- Kafel is a git submodule (`.gitmodules`: `https://github.com/google/kafel.git`). Build dependencies (`debian/control`): protobuf-compiler, libprotobuf-dev, libnl-route-3-dev, bison, flex.
- `README.md:304`: "CLONE_NEWUSER required: Run with `--disable_clone_newuser` (requires root) or ensure user namespaces are enabled".
- Packaging:
  - Ubuntu: `https://packages.ubuntu.com/search?keywords=nsjail&searchon=names&suite=all&section=all` returned "Sorry, your search gave no results" across jammy through stonking. `https://launchpad.net/ubuntu/+source/nsjail` says "There is no current release for this source package in Ubuntu."
  - Debian: packages.debian.org and bugs.debian.org are **blocked (UNREACHABLE)**. A WebSearch snippet only (not opened) shows ITP bug **#964199** "ITP: nsjail -- A light-weight process isolation tool…", filed 2020-07-03, with a 2025 note about a kafel RFS (#1110378). Ubuntu syncs from Debian and has nothing, so nsjail is almost certainly not in the Debian archive. Upstream carries its own `debian/` directory (`debian/changelog`: "nsjail (3.0-1) unstable … Initial release").

## 5. faster-whisper

- PyPI **1.2.1**, uploaded 2025-10-31. Latest tag v1.2.1. `faster_whisper/version.py`: `__version__ = "1.2.1"`. `LICENSE`: "MIT License, Copyright (c) 2023 SYSTRAN". Dependencies: ctranslate2>=4,<5; huggingface-hub>=0.21; tokenizers; onnxruntime (Silero VAD); av; tqdm.
- `README.md:150`: "**Warning:** `segments` is a *generator* so the transcription only starts when you iterate over it. The transcription can be run to completion by gathering the segments in a list or a `for` loop", followed by `segments = list(segments)  # The transcription will actually run here.`
- Code: `WhisperModel.transcribe` (`transcribe.py:750`, returns `Tuple[Iterable[Segment], TranscriptionInfo]` at :794) builds `segments = self.generate_segments(...)` (:1011) and then `return segments, info` (:1028). `generate_segments` (:1109) is a generator (`yield Segment(` at :1360). `restore_speech_timestamps` is also a generator (`yield segment` at :1876). The batched pipeline is lazy too (`_batched_segments_generator`, :581/:599).
- **Nuance: work done eagerly before the generator is returned.**
  - `decode_audio` at :882
  - VAD `get_speech_timestamps` at :896
  - `self.feature_extractor(audio, ...)` at :922
  - `self.detect_language(...)` at :948, an encoder forward pass when `language=None`
  - A wall-clock timeout around `transcribe()` alone therefore does not cover decoding, and decoding alone does not cover the whole cost.
- Local model:
  - `__init__` has `download_root` and `local_files_only: bool = False` (:633). The docstring at :663-664 says "If True, avoid downloading the file and return the path to the local cached file if it exists."
  - `:681-688`: `elif os.path.isdir(model_size_or_path): model_path = model_size_or_path`, else `download_model(..., local_files_only=..., cache_dir=download_root, ...)` → `huggingface_hub.snapshot_download` (`utils.py:115`).
  - `README.md:277-280`: "Directly load the model from a local directory: `model = faster_whisper.WhisperModel("whisper-large-v3-ct2")`".
  - **Hidden network call**, `transcribe.py:703-711`: if `tokenizer.json` is not in the model directory → `tokenizers.Tokenizer.from_pretrained("openai/whisper-tiny" ...)`. A local directory must include `tokenizer.json` (and `preprocessor_config.json` for non-default feature parameters) to be truly offline.

## 6. NeMo Text Processing

- PyPI `nemo-text-processing` **1.2.0**, uploaded 2026-06-05. `LICENSE` is Apache 2.0. `requirements/requirements.txt:6`: `pynini==2.1.6.post1` (exact pin; it is also in PyPI `requires_dist`).
- Both Arabic directories exist:
  - `nemo_text_processing/inverse_text_normalization/ar/`
    - taggers: cardinal, decimal, fraction, measure, money, punctuation, tokenize_and_classify, word
    - verbalizers: cardinal, decimal, fraction, measure, money, verbalize, verbalize_final, word
  - `nemo_text_processing/text_normalization/ar/`
    - `data/` contains measure, money, number
    - taggers: cardinal, decimal, fraction, measure, money, tokenize_and_classify, word
    - verbalizers: same set as ITN plus verbalize/verbalize_final
- Classes (via `grep ^class`): CardinalFst, DecimalFst, FractionFst, MeasureFst, MoneyFst, WordFst, ClassifyFst, VerbalizeFst, VerbalizeFinalFst. PunctuationFst exists in ITN-ar only.
- **Missing for ar:** date, time, ordinal, telephone, electronic, whitelist, range, serial.
- Registration:
  - `text_normalization/normalize.py:159`: `elif lang == 'ar':`
  - `:748`: choices `["en","de","es","fr","hu","sv","zh","ar","it","hy","ja","hi","ko","vi","pt"]`
  - `inverse_text_normalization/inverse_normalize.py:99`: `elif lang == 'ar':  # Arabic`, and `:204` lists `'ar'`.

## 7. WeTextProcessing

- PyPI **1.2.0**, uploaded 2026-06-10. PyPI `license` and `license_expression` are empty. Repo `LICENSE` is Apache License 2.0. Dependencies: `pynini>=2.1.6`, `importlib_resources`.
- `normalize_with_mapping` exists on master:
  - `tn/processor.py:340`: `def normalize_with_mapping(self, input, nbest=1, include_identity=False):`, docstring "Normalizes text and traces each tagged token through the WFSTs. This requires the tagger to preserve written field values. It never falls back to surface-text diffing."
  - `tn/alignment.py:26` defines `NormalizationMapping` (kind, token_type, input_start/end, output_start/end, input_text, output_text). `:56` defines `NormalizationResult` (input_text, output_text, mappings).
  - `README.md:72-95` gives an example: `zh_tn_model.normalize_with_mapping("今天中午12点")` → mapping `math 12 => 十二` with Unicode character offsets.
  - ITN tests use it as well: `itn/english/test/normalizer_test.py:97`, `itn/japanese/test/normalizer_test.py:108`.
- **It is not in the released package.** The PyPI wheel `wetextprocessing-1.2.0-py3-none-any.whl` has no `alignment.py`, and `'normalize_with_mapping' in tn/processor.py` is False. `git log -- tn/alignment.py` shows the first commit as `99dc9da 2026-07-29 "refactor: separate tagging and verbalization"`. Tag v1.2.0 is 57f8585 (2026-06-10). Using it means installing from git.
- Languages: `tn/` has chinese, english, japanese; `itn/` has chinese, english, japanese. The CLI uses `--language zh|ja` (README:132-135). **No Arabic** (grep for arabic/"ar" returns nothing).

## 8. CAMeL Tools

- PyPI `camel-tools` **1.6.0**, uploaded 2026-06-08. `LICENSE` is "MIT License, Copyright 2018-2026 New York University Abu Dhabi". `README.rst:271`: "CAMeL Tools is available under the MIT license."
- `README.rst:262` (paper abstract): "utilities for pre-processing, morphological modeling, Dialect Identification, Named Entity Recognition and Sentiment Analysis". Modules: `camel_tools/morphology`, `disambig`, `tagger`, `tokenizers`, `dialectid`, `ner`, `sentiment`.
- Hard dependencies include `torch>=2.0`, `transformers>=4.44.0`, `scikit-learn>=1.8.0` and `camel-kenlm` (non-Windows). The install is heavy.
- **Data packages are required.** `README.rst:174-186`: "To install the data packages required by CAMeL Tools components, run … `camel_data -i all` / `camel_data -i light` (morphology and MLE disambiguation only) / `camel_data -i defaults`". The location is overridable with the `CAMELTOOLS_DATA` env var (`camel_tools/data/catalogue.py:64-66`).
- Hosting: `camel_tools/data/catalogue.py:47`: `CATALOGUE_URL = "https://raw.githubusercontent.com/CAMeL-Lab/camel-tools-data/main/catalogue-1.6.json"`. The catalogue's download URLs are all `https://github.com/CAMeL-Lab/camel-tools-data/releases/download/<date>/...` (the only other host in it is catalog.ldc.upenn.edu, for the LDC license).
- **Per-package data licenses (from the catalogue):**
  - `morphology-db-msa-r13` (the **default** MorphologyDB): **GPL v2**
  - `disambig-mle-calima-msa-r13`: **GPL v2**
  - `morphology-db-egy-r13`: GPL v2
  - `morphology-db-glf-01` and `morphology-db-lev-01`: CC BY 4.0
  - `morphology-db-msa-s31`: **LDC** (shipped "muddled")
  - BERT disambiguators and dialectid: MIT
  - `ner-arabert` and `sentiment-analysis-arabert`: "AraBERT"
  - `sentiment-analysis-mbert`: Apache 2.0
  - `light` = morphology-db-all + disambig-mle-all + dialectid-model26. `defaults` includes msa-r13 (GPL v2) plus roughly 0.5 GB BERT models each.

## 9. open-tts-eval

- Found at **https://github.com/inworld-ai/open-tts-eval** ("Inworld TTS Open Evaluation Toolkit"). There is a fork at ashwinexe/open-tts-eval.
- `LICENSE`: "MIT License, Copyright (c) 2026 Inworld AI".
- Commits: initial 2026-08-25 (5c531a1); **last 2026-09-09** (3cf4b2d "Eval integrity fixes…"). Four commits in total.
- `pyproject.toml`: name `inworld-tts-evaluation-toolkit` 0.1.0. Not on PyPI under `open-tts-eval` or `tts-assess` (both 404).
- README "What It Does":
  - "Runs local ASR with `faster-whisper` or a mock backend for tests."
  - "Computes WER/CER, insertion/deletion/substitution rates, hallucination heuristics, duration, speech-rate proxy, silence, clipping, loudness proxy, and tail-click signals."
  - "Optionally runs heavier public metrics: NISQAv2, ECAPA speaker similarity…"
- Dependencies: jiwer>=3.0, numpy, pydantic, pyyaml, rich, scipy, soundfile, typer. The `asr` extra is `faster-whisper>=1.0.0` (`src/tts_assess/asr/backends.py:73-115`).
- Audio metrics: `src/tts_assess/metrics/audio.py:11-16` covers rms, clipping_ratio, leading/trailing_silence_sec, silence_ratio.
- **English-centric**: `config.py:29` `language: str | None = "en"`. Normalizers (`normalization/backends.py:12-36`) are `english-basic`, optional NeMo (wrapped by `normalize_english`), or a plugin spec. There is no Arabic normalizer.
- The optional sampling subsystem calls the Inworld, ElevenLabs and Hume APIs.

## 10. GitLab docs and Bubblewrap

- Page: https://docs.gitlab.com/user/duo_agent_platform/environment_sandbox/ ("Remote execution environment sandbox"). docs.gitlab.com is blocked here, so this was read from source at `https://gitlab.com/gitlab-org/gitlab/-/raw/master/doc/user/duo_agent_platform/environment_sandbox.md` (master, fetched 2026-10-04).
  - :53 "The execution environment sandbox uses Anthropic Sandbox Runtime (SRT) to wrap flow execution with the following protections: Network isolation… Filesystem restrictions… Graceful fallback: If SRT is unavailable or required operating system privileges are missing, the flow runs directly with a warning message."
  - :115 "Error: Sandbox dependencies are not available on this system. Required: ripgrep (rg), bubblewrap (bwrap), and socat."
- Also https://docs.gitlab.com/user/duo_agent_platform/flows/execution/images/ (source `doc/user/duo_agent_platform/flows/execution/images.md:301-302`):
  - "`@anthropic-ai/sandbox-runtime` (SRT) | 0.0.77 (via npm)"
  - "`bwrap` (bubblewrap) | AlmaLinux 9 EPEL (plain binary, userns-based sandboxing)"
- Verdict PARTLY: GitLab does use bwrap, but indirectly through SRT, and its documented behaviour is **fail-open**, which is a pattern to avoid.

## 11. Issue and discussion URLs

whisper.cpp (repo now `ggml-org/whisper.cpp`; titles confirmed with WebFetch):
- https://github.com/ggml-org/whisper.cpp/issues/1724: **"Hallucination on silence"**, pprobst, 2024-01-04, open. "in audio files that have silence at the end (even ~1s of silence), whispercpp sometimes transcribes "bullshit" text from nonexistent speech."
- https://github.com/ggml-org/whisper.cpp/discussions/2286: **"Improving hallucinations and repetitions"**, bviksoe, 2024-07-07. "Several people complain that whisper will easily get into an endless repetition loop, and hallucinations especially after silence or noise."
- From search results only (not opened): #1490 "Large Model hallucination and repeating issue"; #3744 "Proposal: reduce repetition hallucinations in long-form decoding".

faster-whisper:
- https://github.com/SYSTRAN/faster-whisper/issues/116: **"Faster Whisper will not run offline"**, 2023-04-05, closed. Reports Hub connection errors when offline.
- https://github.com/SYSTRAN/faster-whisper/issues/1430: **"Disable model download in first run"**, 2026-03-24, closed. Asks to "replace the model size parameter with the specific folder path where the model exists."
- https://github.com/SYSTRAN/faster-whisper/discussions/1173: **"Where does faster-whisper downloads the model ?"**, 2024-11-26. Maintainer MahmoudAshraf97: "it's downloaded from huggingface to the huggingface cache dir".
- https://github.com/SYSTRAN/faster-whisper/pull/1554: **"docs: explain offline model loading"**, widechaos, opened 2026-10-01, **closed unmerged 2026-10-04** (redirected to Show and Tell). Its text notes "a local model still needs `tokenizer.json`, otherwise loading may attempt a separate Hub request", which matches `transcribe.py:703-711`.
- https://github.com/SYSTRAN/faster-whisper/issues/945: "Unable to open file 'model.bin' in model 'models\\base'" (a local-directory loading failure).
- I found no explicit maintainer recommendation of a local model directory in an issue. The authoritative recommendation is README:277-280 together with the code at transcribe.py:681-682.

## PyPI availability (not installed)

- `https://pypi.org/pypi/pebble/json` → 5.2.2, files `pebble-5.2.2-py3-none-any.whl`, `pebble-5.2.2.tar.gz`, not yanked, `requires_python >=3.10`.
- `https://pypi.org/pypi/jsonschema/json` → 4.26.0, files `jsonschema-4.26.0-py3-none-any.whl`, `.tar.gz`, not yanked, `requires_python >=3.10`. Its dependency `rpds-py` needs a binary wheel for your platform.
- Both are reachable from this container (HTTP 200; sdist and wheel downloads succeeded for pebble and WeTextProcessing).
