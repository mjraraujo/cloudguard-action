"""Pass action inputs as argv, preserving the CLI's gate/error exit status."""
import os
from pathlib import Path
import subprocess
import sys


def invocation(environment):
    executable = environment.get("CLOUDGUARD_EXECUTABLE", "")
    plan = environment.get("CLOUDGUARD_PLAN", "")
    if not executable or not plan:
        raise ValueError("verified executable and plan inputs are required")
    args = [executable, "evaluate", "--plan", plan,
            "--catalog", environment.get("CLOUDGUARD_CATALOG") or "pricing.db",
            "--config", environment.get("CLOUDGUARD_CONFIG") or ".cloudguard.yaml",
            "--output", environment.get("CLOUDGUARD_REPORT") or "cloudguard-report.md",
            "--root", environment.get("CLOUDGUARD_SOURCE_ROOT") or "."]
    optional = [("CLOUDGUARD_USAGE", "--usage"),
                ("CLOUDGUARD_CATALOG_URL", "--catalog-url"),
                ("CLOUDGUARD_CATALOG_SHA256", "--catalog-sha256")]
    catalog_url = environment.get("CLOUDGUARD_CATALOG_URL", "")
    catalog_hash = environment.get("CLOUDGUARD_CATALOG_SHA256", "")
    if bool(catalog_url) != bool(catalog_hash):
        raise ValueError("catalog-url and catalog-sha256 must be supplied together")
    for key, flag in optional:
        if environment.get(key):
            args.extend([flag, environment[key]])
    env = dict(environment)
    if not env.get("CLOUDGUARD_LICENSE_KEY") and env.get("CLOUDGUARD_LEGACY_LICENSE_INPUT"):
        env["CLOUDGUARD_LICENSE_KEY"] = env["CLOUDGUARD_LEGACY_LICENSE_INPUT"]
    return args, env


def main():
    args, environment = invocation(os.environ)
    if not Path(args[0]).is_file():
        raise ValueError("verified CloudGuard executable is missing")
    return subprocess.run(args, env=environment, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print("CloudGuard action failed: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
