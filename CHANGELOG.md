# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/Artexis10/kb-mcp/compare/kb-mcp-v0.1.0...kb-mcp-v0.2.0) (2026-07-01)


### Features

* **attention:** compose epistemic queues into one ranked review surface ([#67](https://github.com/Artexis10/kb-mcp/issues/67)) ([bdc6ab4](https://github.com/Artexis10/kb-mcp/commit/bdc6ab4163c3fa217e2343f66f6be7f3808dc62e))
* **audit:** ACT-R dormancy ordering for stale_review + get read-logging ([#51](https://github.com/Artexis10/kb-mcp/issues/51)) ([1637906](https://github.com/Artexis10/kb-mcp/commit/16379064f32fcadfaed85cebb3b7069d8580721e))
* **audit:** order corpus_contradictions queue by cosine + ACT-R dormancy (measure-only) ([#59](https://github.com/Artexis10/kb-mcp/issues/59)) ([511a4a6](https://github.com/Artexis10/kb-mcp/commit/511a4a65095edde19e59bb6ab0973c8d2e7a63f4))
* corpus-wide contradiction sweep + opt-in ASR diarization + opt-in vision captioning ([#54](https://github.com/Artexis10/kb-mcp/issues/54)) ([3546773](https://github.com/Artexis10/kb-mcp/commit/35467733ea40a31a91681c25a8025550e716cd7a))
* **detect:** conflict-on-write + stale_review audit (measure-and-surface) ([#50](https://github.com/Artexis10/kb-mcp/issues/50)) ([7533c50](https://github.com/Artexis10/kb-mcp/commit/7533c50f910eee3e5c41ccff03b858b4f4b19022))
* **diarization:** isolate pyannote in a CPU-torch sidecar subprocess ([#63](https://github.com/Artexis10/kb-mcp/issues/63)) ([b0582d7](https://github.com/Artexis10/kb-mcp/commit/b0582d71c79bff72e92e04db3c117dc86a18ca73))
* **evolution:** thinking-evolution view — supersession chains as timelines ([#73](https://github.com/Artexis10/kb-mcp/issues/73)) ([42a55b0](https://github.com/Artexis10/kb-mcp/commit/42a55b0a0a30cc359b01746312225d17c48076a4))
* **extract:** zero-shot image tags via CLIP — richer findable image measurement (default-off) ([#58](https://github.com/Artexis10/kb-mcp/issues/58)) ([be10b5c](https://github.com/Artexis10/kb-mcp/commit/be10b5cfd713c685ad7140352461f7912c86a3db))
* **find:** reasoning-ready context packs via find(pack=true) ([#69](https://github.com/Artexis10/kb-mcp/issues/69)) ([0a5f86a](https://github.com/Artexis10/kb-mcp/commit/0a5f86aa6cd7a929b4b0847487134eae8d1b94f5))
* **find:** speaker filter — find diarized media by who spoke ([#66](https://github.com/Artexis10/kb-mcp/issues/66)) ([5415617](https://github.com/Artexis10/kb-mcp/commit/54156177a220f7f73f69e892560b01512a376d1f))
* **find:** temporal lane + intent-adaptive weighted RRF + auto-tune + smart rerank ([#52](https://github.com/Artexis10/kb-mcp/issues/52)) ([d7347f5](https://github.com/Artexis10/kb-mcp/commit/d7347f5948441c9dfcbf2389af4b0c99dfbadb86))
* **mcp:** annotate tools with readOnly/destructive/open-world hints ([#76](https://github.com/Artexis10/kb-mcp/issues/76)) ([4704498](https://github.com/Artexis10/kb-mcp/commit/4704498699f50b3e19f20b6df77d860be51a1107))
* named-speaker diarization (OpenSpec change [#1](https://github.com/Artexis10/kb-mcp/issues/1)) — voice-profile attribution, default-off + soft-fail ([#55](https://github.com/Artexis10/kb-mcp/issues/55)) ([32c11a6](https://github.com/Artexis10/kb-mcp/commit/32c11a642bdeb74107c1bd88f91e532d0e0e828e))
* **ranking:** close the auto-tune loop (usage→pairs→tuner + reviewed loadable config) ([#64](https://github.com/Artexis10/kb-mcp/issues/64)) ([9d3026a](https://github.com/Artexis10/kb-mcp/commit/9d3026a378ad6a85888903a1cd9ff8cdb6965877))
* **server:** live file-watcher + personal REST facade + heading-targeted edits + get link-summary ([#53](https://github.com/Artexis10/kb-mcp/issues/53)) ([8f7a206](https://github.com/Artexis10/kb-mcp/commit/8f7a206ca69c3691c153a041376a7c702aa97bc1))
* unify command surface — one registry generates MCP + REST + CLI + OpenAPI ([#2](https://github.com/Artexis10/kb-mcp/issues/2)) ([#56](https://github.com/Artexis10/kb-mcp/issues/56)) ([92c9f91](https://github.com/Artexis10/kb-mcp/commit/92c9f91fee2b82bdf3c2b5b1336e385f8c800fc7))


### Bug Fixes

* **auth:** stop SingleUserGitHubVerifier shadowing the parent's _cache (fixes 401) ([#75](https://github.com/Artexis10/kb-mcp/issues/75)) ([9b1f76f](https://github.com/Artexis10/kb-mcp/commit/9b1f76f37778a5777d6d5ec75cb8a309d8d8fcb8))
* **cli:** 4 LOW review follow-ups (kb edit --value string, --field exit code, REST edits blob-guard, tier2 CLI message) ([#57](https://github.com/Artexis10/kb-mcp/issues/57)) ([b666f45](https://github.com/Artexis10/kb-mcp/commit/b666f452f9eb9e318e5c81bc5585f0e63a910462))
* **diarization:** cross-platform sidecar + sharpen the shared-checkout rule ([#65](https://github.com/Artexis10/kb-mcp/issues/65)) ([311ce4f](https://github.com/Artexis10/kb-mcp/commit/311ce4ff5308f2ee7c13eb263cf2d98565003267))
* **diarization:** decode audio via PyAV, bypass torchcodec (+ document removal) ([#61](https://github.com/Artexis10/kb-mcp/issues/61)) ([eeb129f](https://github.com/Artexis10/kb-mcp/commit/eeb129f7236c7df3020400d2585a96da689e694b))
* **diarization:** pyannote 4.x HF-auth kwarg (use_auth_token -&gt; token, 3.x fallback) ([#62](https://github.com/Artexis10/kb-mcp/issues/62)) ([3792534](https://github.com/Artexis10/kb-mcp/commit/37925341b1d3bf028b6a71949a08af97bc7373cb))


### Performance

* **auth:** cache GitHub token validation + un-redden lean CI ([#71](https://github.com/Artexis10/kb-mcp/issues/71)) ([a66582c](https://github.com/Artexis10/kb-mcp/commit/a66582c430b39872a0d3936c75dcc827171ad54b))

## 0.1.0 (2026-07-01)

### Features

* initial public source release baseline
