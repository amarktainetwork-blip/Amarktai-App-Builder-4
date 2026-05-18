# Go-Live Evidence Matrix

Status values: `working`, `partial`, `broken`, `setup-needed`, `optional`.

| Feature | Claimed in UI | Provider configured | Model/provider discovered | Runtime call tested | Runtime call passed | Artifact/result persisted | Injected/used in generated project | Visible in preview | Final gate enforces it | Dashboard label truthful | Evidence project/test | Status | Required fix |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| GenX text | yes | yes | yes | yes | yes | n/a | yes | yes | yes | yes | backend suite | working | Keep routing tied to live probe. |
| GenX image | yes | yes | yes | now | conditional | conditional | conditional | conditional | now | now | test_genx_media_runtime.py | partial | Require params payload and persisted artifact proof. |
| GenX video | yes | yes | yes | partial | partial | partial | partial | partial | now | now | capability truth labels | partial | Add provider execution evidence before available label. |
| GenX audio/music | yes | conditional | discovered | no | no | no | no | no | no | now | capability matrix | setup-needed | Add runtime smoke before end-to-end label. |
| GenX voice/TTS | yes | conditional | discovered | partial | partial | partial | partial | partial | partial | now | avatar/voice tests | partial | Persist proof chain. |
| GenX avatar | yes | conditional | discovered | partial | partial | conditional | conditional | conditional | partial | now | avatar runtime tests | partial | Gate provider video separately from browser fallback. |
| Qwen text/code | yes | optional | optional | partial | partial | n/a | routing only | n/a | no | yes | capability tests | partial | Keep optional and live-probe based. |
| Qwen image/media | yes | optional | optional | now | no evidence | no | no | no | no | now | test_capability_truth_labels.py | setup-needed | Do not label available until runtime and persistence pass. |
| Firecrawl search/crawl | yes | optional | yes | yes | conditional | n/a | scout context | n/a | yes | yes | test_firecrawl_go_live_status.py | working | Preserve Firecrawl-only labels. |
| Pixabay image | yes | optional | provider | yes | rate-limited possible | conditional | conditional | conditional | now | now | audit + media tests | partial | Mark 429 as rate_limited/fallback. |
| Pixabay video | yes | optional | provider | yes | conditional | conditional | hero only if suitable | conditional | now | now | audit + media tests | partial | Count as video only, not gallery image coverage. |
| GitHub PAT | yes | optional | n/a | yes | conditional | n/a | repo workflows | n/a | guard checks | yes | existing repo tests | working | Keep PAT truth from CapabilityTruthService. |
| repo import | yes | GitHub PAT | n/a | yes | conditional | workspace | yes | dashboard | guard checks | yes | repo workbench tests | working | None. |
| repo analysis | yes | GenX | model | yes | conditional | analysis event | yes | dashboard | event tests | yes | backend tests | working | None. |
| diff view | yes | local | n/a | yes | yes | diff summary | yes | dashboard | PR guard | yes | repo tests | working | None. |
| commit | yes | GitHub/local | n/a | conditional | conditional | git result | repo | dashboard | guard | yes | repo guard tests | partial | Surface command errors. |
| PR creation | yes | GitHub PAT | n/a | conditional | conditional | PR URL | repo | dashboard | guard | yes | PR guard tests | partial | Use connector/gh evidence. |
| rollback/checkpoints | yes | local | n/a | partial | partial | checkpoints | workspace | dashboard | no | partial | versioning tests | partial | Add final-gate evidence. |
| build storage list/archive/delete | yes | local | n/a | yes | yes | storage state | dashboard | dashboard | yes | yes | build storage tests | working | None. |
| preview generation | yes | local | n/a | yes | yes | preview manifest | yes | yes | yes | yes | quality gate tests | working | None. |
| runtime screenshots desktop/tablet/mobile | yes | Playwright | local | yes | conditional | screenshots | runtime QA | dashboard/report | now | yes | runtime QA tests | partial | Missing screenshots block strict premium finalization. |
| Lighthouse | yes | local binary | n/a | yes | conditional | report | runtime QA | dashboard/report | now | yes | runtime QA + premium gate | setup-needed | CHROME_PATH missing is misconfigured, not green. |
| axe-core | yes | local asset | n/a | yes | conditional | report | runtime QA | dashboard/report | now | yes | runtime QA + premium gate | setup-needed | Missing axe-core is setup-needed warning. |
| Whisper/STT | yes | optional | no | no | no | no | no | no | no | now | capability labels | optional | Keep optional/setup-needed. |
| FAISS/RAG | yes | optional | no | no | no | no | no | no | no | now | capability labels | optional | Keep optional/setup-needed. |
| Stable Diffusion fallback | yes | optional | no | no | no | no | no | no | no | now | capability labels | optional | Do not imply enabled without smoke. |
| MusicGen fallback | yes | optional | no | no | no | no | no | no | no | now | capability labels | optional | Do not imply enabled without smoke. |
| Playwright traces | yes | optional | no | no | no | no | no | no | no | now | capability labels | optional | Keep setup-needed. |
| LangGraph/orchestration graph | yes | optional | no | no | no | no | no | no | no | now | capability labels | optional | Keep setup-needed. |
| Media Director | yes | GenX/Qwen/Pixabay | yes | yes | conditional | manifest | yes | yes | now | yes | media tests | partial | Manifest must expose provider failures and alignment. |
| Creative Director | yes | GenX | yes | yes | conditional | design context | generated files | preview | quality gate | yes | existing tests | working | None. |
| Motion/3D | yes | local/code | n/a | yes | conditional | motion manifest | source files | preview | yes | yes | motion tests | partial | Keep manifest and runtime selectors tied. |
| Visual QA | yes | Playwright | local | yes | conditional | screenshots | reports | dashboard/report | now | yes | runtime QA | partial | Strict premium blocks broken media. |
| Content quality gate | yes | local | n/a | yes | yes | content report | final gate | dashboard/report | yes | yes | quality tests | working | Combine with premium score. |
| Final quality gate | yes | local | n/a | yes | yes | quality-report | final status | dashboard/report | yes | yes | premium gate tests | working | Add premium_quality_score. |
| premium/cinematic output quality | yes | providers/local | yes | now | conditional | now | now | now | now | now | premium gate tests | partial | Score cannot be 100 with broken runtime/provider evidence. |
| dashboard capability labels | yes | truth service | yes | now | conditional | latest evidence | latest build | dashboard | n/a | now | test_capability_truth_labels.py | working | Use proof-chain labels. |
| realtime events/websocket replay | yes | local | n/a | yes | yes | event buffer | dashboard | dashboard | yes | yes | backend tests | working | Preserve replay/final gate events. |
