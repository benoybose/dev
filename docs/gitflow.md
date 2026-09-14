# GitFlow and Semantic Versioning

The repository uses GitFlow-style branches with semantic versioning managed by
`.github/workflows/version.yml` and `scripts/version.py`.

| Branch | Version behavior | Example |
|---|---|---|
| `feature/*` | Preserve the current version | `feature/cache` |
| `develop` | Move to the next minor development version once | `0.2.0-dev.0` |
| `release/X.Y` | Set the release version with patch `0` | `release/1.2` → `1.2.0` |
| `release/X.Y.Z` | Set the exact release version | `release/1.2.0` → `1.2.0` |
| `hotfix/X.Y.Z` | Set the exact patch version | `hotfix/1.2.1` → `1.2.1` |
| `main` | Preserve the stable version merged from release/hotfix | `1.2.0` |

The version workflow updates both `pyproject.toml` and `src/dev/__init__.py`.
It commits changes as the GitHub Actions bot with `[skip ci]` to avoid a loop.
The workflow only runs automatically for `develop`, `release/*`, and
`hotfix/*`; it can also be run manually with a branch name.

## Release flow

1. Create `feature/*` from `develop`.
2. Merge completed features into `develop`.
3. Create `release/X.Y` from `develop`; the workflow sets `X.Y.0`.
4. Validate the release candidate through CI.
5. Merge the release branch into `main` and `develop`.
6. Create a tag such as `vX.Y.0` on `main`.
7. CI builds and smoke-tests the package. Publishing is intentionally not
   configured until a package registry and publishing credentials are selected.

For urgent fixes, create `hotfix/X.Y.Z` from `main`, validate it, merge it
back into both `main` and `develop`, then tag the resulting `main` commit.
