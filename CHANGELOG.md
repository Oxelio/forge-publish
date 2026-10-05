# CHANGELOG

<!-- version list -->

## v2.1.0 (2026-10-05)

### Features

- **release**: Publish checksums and provenance attestations
  ([`58e6aa7`](https://github.com/Oxelio/forge-publish/commit/58e6aa76bd96a4a68d09e896ed018a353c73e3c9))


## v2.0.0 (2026-10-05)

### Bug Fixes

- **npm**: Enforce safe pack scripts with npm 11
  ([`c9971a2`](https://github.com/Oxelio/forge-publish/commit/c9971a2de98717a638cb0e7d5f3d7171919c3baa))

### Chores

- **npm**: Checkpoint issue 40 pending compatibility decision
  ([`6dcffeb`](https://github.com/Oxelio/forge-publish/commit/6dcffeb17f2363694f2e85865f805472d8a61392))


## v1.0.6 (2026-10-04)

### Bug Fixes

- **deb**: Guard parser errors with bounded fuzz coverage
  ([`3a8ff82`](https://github.com/Oxelio/forge-publish/commit/3a8ff8277e5b7c5a289f62f669276cbb9a350352))


## v1.0.5 (2026-10-04)

### Bug Fixes

- **config**: Handle URL parser errors
  ([`83a08b5`](https://github.com/Oxelio/forge-publish/commit/83a08b52dbeaa97a3f3897c3b7772374044a8401))


## v1.0.4 (2026-10-04)

### Bug Fixes

- **deb**: Handle malformed tar extension errors
  ([`db658fa`](https://github.com/Oxelio/forge-publish/commit/db658fa674f41c63ee668a1a0ce39df6b81a6436))


## v1.0.3 (2026-10-04)

### Bug Fixes

- **client**: Reject package API redirects
  ([`08de9db`](https://github.com/Oxelio/forge-publish/commit/08de9db5cbeef57f445ef9259727d9643552ba63))

- **deb**: Bound control archive decoder memory
  ([`9722a32`](https://github.com/Oxelio/forge-publish/commit/9722a32edb2afe660d8e3d9a0d766d3e126b833d))


## v1.0.2 (2026-10-04)

### Bug Fixes

- **deb**: Bound debian-binary member reads
  ([`0621f04`](https://github.com/Oxelio/forge-publish/commit/0621f04aec7a2fdc7dec849d23ddc20986ca6c7f))

### Chores

- Ignore XML coverage report
  ([`fd31172`](https://github.com/Oxelio/forge-publish/commit/fd31172fcc2bd4799845dc984d58f2356ce4a15d))

### Continuous Integration

- Add dependency review gate
  ([`b9b546a`](https://github.com/Oxelio/forge-publish/commit/b9b546a702b32a58e22f1117c7de90783d0e0fd8))

- Export XML coverage report
  ([`78a943f`](https://github.com/Oxelio/forge-publish/commit/78a943f9e5e5d23b1d44b2f6a7905562845db6cb))

### Documentation

- Document dependency review gate
  ([`2fa3049`](https://github.com/Oxelio/forge-publish/commit/2fa30497a0582baebdef25008689b4bf0fb5802b))


## v1.0.1 (2026-10-02)

### Bug Fixes

- Normalize package and config decoding errors
  ([#48](https://github.com/Oxelio/forge-publish/pull/48),
  [`646b436`](https://github.com/Oxelio/forge-publish/commit/646b43629766d9a65c1dfc29dde9ff27b951f9cb))

### Chores

- **deps**: Bump click from 8.1.8 to 8.5.0 ([#25](https://github.com/Oxelio/forge-publish/pull/25),
  [`4e9ea4b`](https://github.com/Oxelio/forge-publish/commit/4e9ea4b679f66f8c4a13951d27e7210ac7727785))

- **deps**: Bump python-semantic-release from 10.6.2 to 10.7.0
  ([#27](https://github.com/Oxelio/forge-publish/pull/27),
  [`c437172`](https://github.com/Oxelio/forge-publish/commit/c43717271be841c9aac7fd5a3fe928bdf575fc83))


## v1.0.0 (2026-09-30)

### Chores

- Make Python tooling reproducible ([#24](https://github.com/Oxelio/forge-publish/pull/24),
  [`c0c533e`](https://github.com/Oxelio/forge-publish/commit/c0c533e017e8438e2eae644c027f909dfddd2739))

- **deps**: Bump actions/setup-node from 6.5.0 to 7.0.0
  ([#20](https://github.com/Oxelio/forge-publish/pull/20),
  [`6952a30`](https://github.com/Oxelio/forge-publish/commit/6952a309c4e636c38a8d812f1c92e4b33832c38f))

- **release**: Prepare 1.0.0 [release:major]
  ([#28](https://github.com/Oxelio/forge-publish/pull/28),
  [`86c018e`](https://github.com/Oxelio/forge-publish/commit/86c018e6e54f02a4861c8081211d44df2bedcb26))

### Documentation

- Clarify npm prerelease version requirements
  ([#21](https://github.com/Oxelio/forge-publish/pull/21),
  [`2e63bf1`](https://github.com/Oxelio/forge-publish/commit/2e63bf19b06256874e9907c4a8516de15f75c1d3))

- **security**: Define npm environment policy
  ([#23](https://github.com/Oxelio/forge-publish/pull/23),
  [`e4d2d0a`](https://github.com/Oxelio/forge-publish/commit/e4d2d0a4668161131f37ccb7ee8b2b6bdc050d49))

### Testing

- Validate minimum and bundled npm versions ([#22](https://github.com/Oxelio/forge-publish/pull/22),
  [`c07780c`](https://github.com/Oxelio/forge-publish/commit/c07780ca078f921ca18dc8657df1657c2b7b5f0f))


## v0.1.0 (2026-09-24)

- Initial Release
