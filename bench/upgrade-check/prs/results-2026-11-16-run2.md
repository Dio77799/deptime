# DT-QA-22: the upgrade check on real update pull requests, second run, in-sample (2026-11-16)

**In-sample, not in place of the first run** (`results-2026-11-16.md`). The first run's misses and false breaks
were worked on with this set in view, so this measures those fixes, not how the check does on pull requests it hasn't
seen. Same set, labels, audit and scoring code; DepTime's code at 8a94c1e, on the first published index with
`SNAPSHOT_FORMAT` 27. Every break reported here was in the first run's audit (`audit/breaks.json`), so no new probe
or hand check was needed.

What changed since the first run:

- **DT-CORE-71** (requirements files in any folder): 6 of the 7 subfolder updates are now read; the seventh
  (`harvester/tests` #3011) has two subfolder files pinning different versions, and the shallower one is read
  (urllib3 2.0.7 → 2.8.0 where the title says 1.26.7), so it still counts as not read.
- **DT-CORE-72, DT-DATA-82, DT-DATA-51** (`SNAPSHOT_FORMAT` 27): the three false breaks are gone; no new break
  appeared. Working uses flagged: 0 of 3,291; pull requests failed with no confirmed break: 0 of 264.
- **Unchanged:** the two missed breaks (mcp 2.0's `ClientRequest.model_construct`, DT-CORE-73).
- **Updates still not read (10):** the first run's 9 other than the six above, by its grouping (5 whose base and
  head no longer show the title's change, 2 Renovate updates to several projects' lockfiles in subfolders at once, 1
  `Pipfile.lock`, 1 `requirements.in`), and the two-file case. Three of the ten change only a `uv.lock` in a subfolder
  (the two Renovate updates and transformers' `backend/uv.lock`, where the root `uv.lock` is read instead):
  DT-CORE-74.

Index built 2026-11-16T06:36:40+00:00. 264 pull requests, 3339 labelled uses.

## The bar

| measure | bar | result | met |
|---|---|---|---|
| 1. updates read | ≥ 90% | 96.2% (254/264; 93.2-97.9) | yes |
| 2. breaks found | ≥ 90% | 95.8% (46/48; 86.0-98.8) | yes |
| 3. working uses flagged | ≤ 1% | 0.0% (0/3291; 0.0-0.1) | yes |
| 4. pull requests failed with no confirmed break | ≤ 5% | 0.0% (0/264; 0.0-1.4) | yes |
| 5. labelled uses read | ≥ 95% | 99.6% (3326/3339; 99.3-99.8) | yes |

Of 15 pull requests the check fails: 15 justified, 0 false, 0 undetermined (lower bound for measure 4, false only: 0.0% (0/264; 0.0-1.4)). Audit environments that didn't install: 0. Pull requests where the check stopped with an error: 0.

## Splits

| | pull requests | updates read | breaks found | working uses flagged | failed, no confirmed break | labelled uses read |
|---|---|---|---|---|---|---|
| all | 264 | 96.2% (254/264; 93.2-97.9) | 95.8% (46/48; 86.0-98.8) | 0.0% (0/3291; 0.0-0.1) | 0.0% (0/264; 0.0-1.4) | 99.6% (3326/3339; 99.3-99.8) |
| stratum: major | 108 | 97.2% (105/108; 92.1-99.1) | 95.8% (46/48; 86.0-98.8) | 0.0% (0/1278; 0.0-0.3) | 0.0% (0/108; 0.0-3.4) | 100.0% (1326/1326; 99.7-100.0) |
| stratum: other | 156 | 95.5% (149/156; 91.0-97.8) | - | 0.0% (0/2013; 0.0-0.2) | 0.0% (0/156; 0.0-2.4) | 99.4% (2000/2013; 98.9-99.6) |
| bot: dependabot | 240 | 97.5% (234/240; 94.7-98.8) | 95.8% (46/48; 86.0-98.8) | 0.0% (0/3009; 0.0-0.1) | 0.0% (0/240; 0.0-1.6) | 99.6% (3044/3057; 99.3-99.8) |
| bot: renovate | 24 | 83.3% (20/24; 64.1-93.3) | - | 0.0% (0/282; 0.0-1.3) | 0.0% (0/24; 0.0-13.8) | 100.0% (282/282; 98.7-100.0) |
| state: open | 157 | 97.5% (153/157; 93.6-99.0) | 94.7% (36/38; 82.7-98.5) | 0.0% (0/2092; 0.0-0.2) | 0.0% (0/157; 0.0-2.4) | 99.4% (2118/2130; 99.0-99.7) |
| state: merged | 64 | 93.8% (60/64; 85.0-97.5) | - | 0.0% (0/833; 0.0-0.5) | 0.0% (0/64; 0.0-5.7) | 99.9% (832/833; 99.3-100.0) |
| state: closed | 43 | 95.3% (41/43; 84.5-98.7) | 100.0% (10/10; 72.2-100.0) | 0.0% (0/366; 0.0-1.0) | 0.0% (0/43; 0.0-8.2) | 100.0% (376/376; 99.0-100.0) |

## Beside the bar

- Breaks found among pull requests whose update was read: 95.8% (46/48; 86.0-98.8).
- Pull requests with a labelled break that the check fails: 100.0% (13/13; 77.2-100.0).
- `check_symbols` asked about each labelled use directly: breaks found 95.8% (46/48; 86.0-98.8), working uses flagged 0.1% (2/3291; 0.0-0.2).
- Deprecations: working uses the probe found deprecated at `to` that the check lists: 50.0% (19/38; 34.8-65.2); working uses the check lists as deprecated that the probe agrees on: 82.6% (19/23; 62.9-93.0).

**Breaks found by change type:**

| change | breaks found |
|---|---|
| param_now_required | 100.0% (1/1; 20.7-100.0) |
| param_removed | 100.0% (6/6; 61.0-100.0) |
| removed | 95.1% (39/41; 83.9-98.7) |

## Updates not read

- `pr-lewfkrad__hermes-whiskey-office-30-google-generativeai` (google-generativeai 0.8.3 → 0.8.6): changed integrations/object-studio/requirements.in, requirements.in; read as nothing for this package
- `pr-neo4j__neo4j-graphrag-python-753-langchain-openai` (langchain-openai 1.1.12 → 1.1.14): changed uv.lock; read as ['1.1.12', '1.7.4', 'uv.lock']
- `pr-buggy1111__anonymize-mcp-3-mcp` (mcp 2.0.0 → 2.2.0): changed pyproject.toml; read as ['2.3.0', '2.2.0', 'uv.lock']
- `pr-srn0129__ultimate-7-polars` (polars 1.44.2 → 2.0.0): changed uv.lock; read as nothing for this package
- `pr-ryuichi1208__homecmd-62-pydantic-ai-slim` (pydantic-ai-slim 0.2.3 → 1.56.0): changed llm/uv.lock, mcp/client/uv.lock, tmp/stt/client/tools/uv.lock; read as nothing for this package
- `pr-tennis-wire__tennis-wire-311-pydantic-settings` (pydantic-settings 2.16.2 → 2.16.3): changed parsing-service/uv.lock, transcription-service/uv.lock; read as nothing for this package
- `pr-ginazai__evergreen-generator-16-streamlit` (streamlit 1.66.1 → 1.67.0): changed requirements-ci.txt; read as nothing for this package
- `pr-legitmattias__unstash-224-transformers` (transformers 5.8.1 → 5.10.1): changed backend/uv.lock; read as ['5.12.1', '5.10.1', 'uv.lock']
- `pr-mkataja__flipper-25-urllib3` (urllib3 2.7.0 → 2.8.0): changed Pipfile.lock; read as nothing for this package
- `pr-harvester__tests-3011-urllib3` (urllib3 1.26.7 → 2.8.0): changed harvester_robot_tests/requirements.txt, ui_tests/requirements.txt; read as ['2.0.7', '2.8.0', 'harvester_robot_tests/requirements.txt']

## Merged pull requests the check fails with a confirmed break (0)


## Breaks not found

- `pr-vassiliylakhonin__agenda-intelligence-md-497-mcp`: `mcp.types.ClientRequest.model_construct` (call, removed)
- `pr-vassiliylakhonin__agenda-intelligence-md-497-mcp`: `mcp.types.ClientRequest.model_construct` (name, removed)

## Working uses flagged


## Every pull request the check fails

- **justified** `pr-adameddahmouni__nosograph-127-chromadb` (chromadb 0.6.3 → 1.5.9, open) https://github.com/AdamEddahmouni/nosograph/pull/127
  - true: chromadb `chromadb.errors.InvalidCollectionException` missing  (labelled) [eac4ded5ccd58391]: doesn't resolve: AttributeError: module 'chromadb.errors' has no attribute 'InvalidCollectionException'
- **justified** `pr-burriedalien666__prompt-quality-lab-6-dspy` (dspy 2.6.13 → 3.4.1, open) https://github.com/burriedalien666/prompt-quality-lab/pull/6
  - true: dspy `dspy.retrieve` missing  (labelled) [3894ecb251cefa24]: doesn't resolve: AttributeError: module 'dspy' has no attribute 'retrieve'
- **justified** `pr-mikecastrodemaria__crispz-minimax-2-gradio` (gradio 5.50.0 → 6.16.0, open) https://github.com/mikecastrodemaria/crispz-minimax/pull/2
  - cant_tell: gradio `gradio.Gallery` rejected_kwarg show_fullscreen_button (labelled) [8eb3164e619561b1]: probe: `show_fullscreen_button` absent in (value: 'Sequence[np.ndarray | PIL.Image.Image | str | Path | tuple] | Callable | None' = None, *, format: 'str' = 'webp', file_types: 'list[str] | None' = None; needs the hand check of a call break
  - true: gradio `gradio.Gallery` rejected_kwarg show_download_button (labelled) [30bdc3675922bfcc]: by hand: gradio 6.16.0 gradio/components/gallery.py: Gallery.__init__ (line 78) has no `show_download_button` and no **kwargs; `buttons` (line 110) replaces it
- **justified** `pr-mikecastrodemaria__crispz-moss-1-gradio` (gradio 5.50.0 → 6.16.0, open) https://github.com/mikecastrodemaria/crispz-moss/pull/1
  - cant_tell: gradio `gradio.Gallery` rejected_kwarg show_fullscreen_button (labelled) [306dd56f6c562ca3]: probe: `show_fullscreen_button` absent in (value: 'Sequence[np.ndarray | PIL.Image.Image | str | Path | tuple] | Callable | None' = None, *, format: 'str' = 'webp', file_types: 'list[str] | None' = None; needs the hand check of a call break
  - true: gradio `gradio.Gallery` rejected_kwarg show_download_button (labelled) [788318b9562df98b]: by hand: gradio 6.16.0 gradio/components/gallery.py: Gallery.__init__ (line 78) has no `show_download_button` and no **kwargs
- **justified** `pr-ichekarovaa__iva_chekarova_ccs6442-10-httpx` (httpx 0.23.0 → 0.28.1, closed) https://github.com/ichekarovaa/iva_chekarova_CCS6442/pull/10
  - true: httpx `httpx.AsyncClient` rejected_kwarg app (labelled) [7c344e8aed35f728]: by hand: httpx 0.28.1 httpx/_client.py: AsyncClient.__init__ (lines 1353-1375) has no `app` and no **kwargs
- **justified** `pr-erlisasadiku__erlisa_sadiku_ccs6442-13-httpx` (httpx 0.23.0 → 0.28.1, closed) https://github.com/erlisasadiku/erlisa_sadiku_CCS6442/pull/13
  - true: httpx `httpx.AsyncClient` rejected_kwarg app (labelled) [208bee15cc2f5028]: by hand: httpx 0.28.1 httpx/_client.py: AsyncClient.__init__ (lines 1353-1375) has no `app` and no **kwargs
- **justified** `pr-the-wilful-youth__geniedoc-7-langchain` (langchain 0.3.7 → 1.3.9, open) https://github.com/the-wilful-youth/GenieDoc/pull/7
  - true: langchain `langchain.text_splitter` missing  (labelled) [b065cf5faa4b557b]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'text_splitter'
  - true: langchain `langchain.text_splitter.RecursiveCharacterTextSplitter` missing  (labelled) [771fbf7bac221643]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'text_splitter'
  - true: langchain `langchain.vectorstores` missing  (labelled) [140c2f7263afed34]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'vectorstores'
  - true: langchain `langchain.vectorstores.FAISS` missing  (labelled) [b44fb5780d2c8cd7]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'vectorstores'
  - true: langchain `langchain.chains.question_answering` missing  (labelled) [9d3da47ba0c92e24]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'chains'
  - true: langchain `langchain.chains.question_answering.load_qa_chain` missing  (labelled) [e030f59333a7f889]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'chains'
  - true: langchain `langchain.prompts` missing  (labelled) [312eb17cacc6ff16]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'prompts'
  - true: langchain `langchain.prompts.PromptTemplate` missing  (labelled) [27dc322ba3291500]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'prompts'
  - true: langchain `langchain.vectorstores.FAISS.from_texts` missing  (labelled) [90a21adc5d4d9efe]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'vectorstores'
  - true: langchain `langchain.vectorstores.FAISS.load_local` missing  (labelled) [eba785f559cd1e28]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'vectorstores'
  - true: langchain `langchain.text_splitter.RecursiveCharacterTextSplitter.split_text` missing  (labelled) [ca4c870f34d36b13]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'text_splitter'
- **justified** `pr-enderfairxd__ai-email-organizer-3-langchain` (langchain 0.1.13 → 1.3.9, closed) https://github.com/EnderFairXD/AI-EMAIL-ORGANIZER/pull/3
  - true: langchain `langchain.prompts` missing  (labelled) [723663d7baf3abd9]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'prompts'
  - true: langchain `langchain.prompts.PromptTemplate` missing  (labelled) [4d200f31667d52cd]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'prompts'
- **justified** `pr-enderfairxd__ai-contract-analyzer-2-langchain` (langchain 0.1.13 → 1.3.9, closed) https://github.com/EnderFairXD/AI-CONTRACT-ANALYZER/pull/2
  - true: langchain `langchain.prompts` missing  (labelled) [85a77ea87522e7dd]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'prompts'
  - true: langchain `langchain.prompts.PromptTemplate` missing  (labelled) [5ea118bab2e2ad9b]: doesn't resolve: AttributeError: module 'langchain' has no attribute 'prompts'
- **justified** `pr-johnmungandiall__openalgo-kotak-7-marshmallow` (marshmallow 3.26.2 → 4.4.0, open) https://github.com/johnmungandiall/openalgo-kotak/pull/7
  - true: marshmallow `marshmallow.fields.Str` rejected_kwarg default (labelled) [ca869c9017b3ba29]: by hand: marshmallow 4.4.0 marshmallow/fields.py: Str = String (line 2141), no __init__ of its own; Field.__init__ (line 180) takes load_default/dump_default, no `default`, no **kwargs
  - cant_tell: marshmallow `marshmallow.fields.Str` rejected_kwarg missing (labelled) [f52375cf7355d4de]: probe: `missing` absent in (*, load_default: 'typing.Any' = <marshmallow.missing>, dump_default: 'typing.Any' = <marshmallow.missing>, data_key: 'str | None' = None, attribute: 'str | Non; needs the hand check of a call break
- **justified** `pr-billsking__baseward-10-mcp` (mcp 1.30.0 → 2.3.0, open) https://github.com/billsking/baseward/pull/10
  - true: mcp `mcp.server.fastmcp.exceptions` missing  (labelled) [d2625760706fa2a9]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
  - true: mcp `mcp.server.fastmcp.exceptions.ToolError` missing  (labelled) [8e017c46a84a1d16]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
  - true: mcp `mcp.server.fastmcp` missing  (labelled) [26ef27eb641fdd99]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
  - true: mcp `mcp.server.fastmcp.FastMCP` missing  (labelled) [556875101febe582]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
  - true: mcp `mcp.client.streamable_http.streamablehttp_client` missing  (labelled) [a855c9003f026a67]: doesn't resolve: AttributeError: module 'mcp.client.streamable_http' has no attribute 'streamablehttp_client'
  - true: mcp `mcp.server.fastmcp.FastMCP.tool` missing  (labelled) [2a169127683b2425]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
- **justified** `pr-vassiliylakhonin__agenda-intelligence-md-497-mcp` (mcp 1.30.0 → 2.3.0, open) https://github.com/vassiliylakhonin/agenda-intelligence-md/pull/497
  - true: mcp `mcp.client.streamable_http.streamablehttp_client` missing  (labelled) [7593c66021e132f7]: doesn't resolve: AttributeError: module 'mcp.client.streamable_http' has no attribute 'streamablehttp_client'
- **justified** `pr-buckleson__vibe-trading-9-mcp` (mcp 1.30.0 → 2.3.0, open) https://github.com/buckleson/vibe-trading/pull/9
  - true: mcp `mcp.server.fastmcp` missing  (labelled) [1f31603f5a42fc25]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
  - true: mcp `mcp.server.fastmcp.FastMCP` missing  (labelled) [ab91869516bc3765]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
  - true: mcp `mcp.server.fastmcp.FastMCP.tool` missing  (labelled) [277ed3f13771693d]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
  - true: mcp `mcp.server.fastmcp.FastMCP.run` missing  (labelled) [3fb993f426709ea6]: doesn't resolve: AttributeError: module 'mcp.server' has no attribute 'fastmcp'
- **justified** `pr-levon003__wiki-ores-feedback-120-sqlalchemy` (sqlalchemy 1.4.54 → 2.1.8, open) https://github.com/levon003/wiki-ores-feedback/pull/120
  - cant_tell: sqlalchemy `sqlalchemy.MetaData` rejected_kwarg bind (labelled) [27c71dd9f86ce712]: probe: `bind` absent in (schema: 'Optional[str]' = None, quote_schema: 'Optional[bool]' = None, naming_convention: 'Optional[_NamingSchemaParameter]' = None, info: 'Optional[_InfoType]; needs the hand check of a call break
  - true: sqlalchemy `sqlalchemy.MetaData.reflect` missing_args  (labelled) [46ffaaa1580bc897]: by hand: sqlalchemy 2.1.8 sqlalchemy/sql/schema.py: MetaData.reflect(self, bind: Union[Engine, Connection], ...) (line 6559); `bind` has no default and the call passes no argument
  - cant_tell: sqlalchemy `sqlalchemy.MetaData.drop_all` missing_args  [92ec5a0ab6aeb86d]: probe: missing a required argument: 'bind'; needs the hand check of a call break
- **justified** `pr-ocha-dap__hdx-ckan-7148-sqlalchemy` (sqlalchemy 1.4.52 → 2.1.8, closed) https://github.com/OCHA-DAP/hdx-ckan/pull/7148
  - true: sqlalchemy `sqlalchemy.orm.relation` missing  [ce16582c1e373251]: doesn't resolve: AttributeError: module 'sqlalchemy.orm' has no attribute 'relation'
  - true: sqlalchemy `sqlalchemy.orm.mapper` raises  [608d0e893f97e385]: built to fail
  - true: sqlalchemy `sqlalchemy.schema.Table.exists` missing  [29666f96b7752c99]: doesn't resolve: AttributeError: type object 'Table' has no attribute 'exists'
  - cant_tell: sqlalchemy `sqlalchemy.schema.Table.drop` missing_args  [b51373b57f9f8876]: probe: missing a required argument: 'bind'; needs the hand check of a call break
  - true: sqlalchemy `sqlalchemy.Table.exists` missing  [35ae8f0d05773e70]: doesn't resolve: AttributeError: type object 'Table' has no attribute 'exists'
