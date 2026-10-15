# CloudGuard FinOps Action

Evaluate Terraform/OpenTofu plans locally on your CI runner. This public package contains the action wrapper, installer, documentation, and a sample policy. CloudGuard engine and issuer source remain in the private `cloudguard-core` repository.

The action installs a **published, exact binary version** from `mjraraujo/cloudguard-action` releases. It verifies the archive against `checksums.txt` before extracting and executing `cloudguard`. No Go compiler or cloud account credentials are needed for evaluation. The binary's license verification public key is embedded by the release build; the action accepts no replacement key.

## Example

Create `plan.json` with `terraform show -json plan.tfplan > plan.json` (OpenTofu also works), prepare a local pricing catalog, and run:

```yaml
permissions:
  contents: read
steps:
  - uses: actions/checkout@v4
  # Generate plan.json and provide your verified local pricing.db before this step.
  - uses: mjraraujo/cloudguard-action@v1.0.0
    env:
      CLOUDGUARD_LICENSE_KEY: ${{ secrets.CLOUDGUARD_LICENSE_KEY }}
    with:
      version: v1.0.0
      plan: plan.json
      catalog: pricing.db
      config: .cloudguard.yaml
      usage: cloudguard-usage.json
      report: cloudguard-report.md
```

`v1.0.0` illustrates the version syntax; use an actually published release. Pin `uses:` to the reviewed action commit SHA for stronger reproducibility, and keep `version:` pinned to an exact stable semantic tag. Mutable `latest`, `v1`, branch names, and arbitrary repositories are rejected by the installer. Set `archive-sha256` when you also pin the release archive digest independently. SHA256 checks establish integrity against the selected manifest; they are not a detached publisher signature.

Supported runners: Linux, macOS, and Windows on x64/arm64, with Python 3.9+ available as an executable named `python` on `PATH`. The action uses `shell: python`; a runner with only a `python3` command needs `actions/setup-python` or equivalent provisioning before this action. GitHub hosted runners provide Python; self-hosted runners must provision it. The installer accepts only the official release repository and extracts only the requested CloudGuard executable. Release bundles contain compiled `cloudguard`, `price-sync`, and `license-server` binaries for the selected platform; the issuer still needs separately configured private signing credentials to run.

## Pricing catalogs and usage

The PR engine queries a local SQLite catalog. The separate `price-sync` ETL consumes official AWS/Azure/GCP list prices and ECB foreign exchange data outside the PR evaluation. GCP Catalog requires an API consumer key for its public data. No cloud API calls occur while calculating the plan.

To fetch a catalog, replace the local-catalog setup with both `catalog-url` and `catalog-sha256`. Use a reviewed digest and an explicit `catalog-...` release URL. A digest downloaded from the same untrusted URL is not an independent trust pin. Catalog releases have separate tags and are never resolved through `releases/latest` by this action. Catalog staleness, missing prices, unsupported meters, and missing usage can make an evaluation incomplete; the default policy rejects incomplete evaluations.

`usage` is optional for resources whose monthly usage is fully represented by Terraform. Supply forecasts for usage-dependent services such as S3 storage/GET/PUT, NAT data processing, and ALB LCU-hours. The usage file is a JSON object keyed by Terraform resource address; refer to the CLI documentation for supported fields. Omit `usage` from the example when no forecast file is needed.

Optional `source-manifest` enables provider-region expressions from matching Terraform source. In the trusted plan-generation step, capture the matching plan and unchanged source using a published CLI version that supports this command and matches the action's `version`:

```sh
cloudguard source-manifest --plan plan.json --root infrastructure --output source-manifest.json
```

Pass `root: infrastructure` and `source-manifest: source-manifest.json` to the action. The manifest binds plan bytes and source hashes; capture is an operator assertion that they belong together. Changed sources or plan bytes are rejected. Without this input, unresolved provider expressions remain incomplete; evaluated resource locations still work. Unsupported expressions remain incomplete even with a manifest. Older CLI releases do not accept this optional flag.

## Optional PR report comment

Set `github-pr` to explicitly create or update the marked report comment on a pull request. Posting stays disabled when this input is empty. Supply the token through the `GITHUB_TOKEN` environment variable and grant permission to write PR comments:

```yaml
permissions:
  contents: read
  pull-requests: write
steps:
  - uses: actions/checkout@v4
  # Generate plan.json and provide your verified pricing.db before this step.
  - uses: mjraraujo/cloudguard-action@v1.0.0
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    with:
      version: v1.0.0
      plan: plan.json
      catalog: pricing.db
      github-pr: ${{ github.event.pull_request.number }}
      report: cloudguard-report.md
```

`github-repository` defaults to `GITHUB_REPOSITORY`; set it explicitly when targeting another repository authorized for the token. The author defaults to `github-actions[bot]`, so a normal workflow installation token does not need the unsupported `GET /user` identity lookup. For a custom GitHub App set `github-author` to its actual `<app-slug>[bot]` login; for a personal access token set it to the token owner's login. The action updates only marked comments owned by that author. The token remains in the environment and is never passed as a command-line argument.

Fork pull-request workflows normally receive a read-only token and cannot write comments. Keep posting disabled in that context or use a separately reviewed reporting workflow with suitable permissions. A missing token, invalid PR number, or invalid repository is rejected before evaluation. A failed budget gate still writes its local report and returns a failing exit status after a successful comment update.

## Plans and licenses

| Plan | Price | Scope |
| --- | --- | --- |
| Free | €0 | Cost reports and basic budget gates |
| Pro | €149/month | Free features, optimization fixes, and GitHub review suggestions |
| Enterprise | €499/month | Pro features, custom governance policies, and drift detection |

Paid licenses are Ed25519 signed and bound to `GITHUB_REPOSITORY_OWNER`. Set the `CLOUDGUARD_LICENSE_KEY` repository or organization secret as an environment variable. `license:` remains available for compatibility; the environment variable takes precedence. License validation runs offline. This action runs `evaluate`; direct CLI commands expose licensed autofix and drift functions.

The action writes the Markdown report to `report` and exposes that path as its `report` output. It returns the CLI's nonzero exit code for a failed gate or invalid input. PR posting requires the explicit inputs and token described above; this wrapper does not send plan data to the licensing service.

## Inputs

`version` and `plan` are required. Optional inputs are `archive-sha256`, `catalog` (default `pricing.db`), `catalog-url` with `catalog-sha256`, `config` (default `.cloudguard.yaml`), `usage`, `github-pr`, `github-repository`, `github-author` (default `github-actions[bot]`), legacy `license`, `root` (default `.`), `source-manifest` (empty by default), and `report` (default `cloudguard-report.md`).
