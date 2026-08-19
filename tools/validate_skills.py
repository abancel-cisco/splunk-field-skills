#!/usr/bin/env python3
"""Validate the skill catalogue before it goes public.

Checks the SKILL.md frontmatter contract, keeps the README index and the plugin
manifest in step with what is actually on disk, and refuses anything that looks
like a real customer or site-specific identifier.

    validate_skills.py                 full check of this repository
    validate_skills.py --scan PATH...   identifier check on arbitrary skills

--scan applies only the rules that are about content rather than about this
repository's layout, so it can be pointed at a skill that is not published yet.
Use it as the sanitisation gate when promoting a newly captured skill: the rules
that decide whether something is safe to share should live in one place.

Exit code is non-zero if any error is found. Warnings do not fail the build.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

try:
    import yaml
except ImportError:  # checked again where it matters
    yaml = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO, "skills")
VALID_CATEGORIES = {"itsi", "platform", "observability", "_meta"}
REQUIRED_FIELDS = ("name", "category", "description")

# Generic classes of identifier that must never reach a public repository.
# Extend rather than relax.
FORBIDDEN = [
    # The GitHub handle is intentionally public in install commands; a bare
    # username elsewhere is usually a leaked filesystem path.
    (re.compile(r"/Users/[a-z0-9._-]+", re.I), "local filesystem path"),
    (re.compile(r"/home/[a-z0-9._-]+", re.I), "local filesystem path"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(?:cisco|splunk)\.com", re.I), "corporate email"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "JWT"),
]

# Specific customer, partner, and environment names are held as SHA-256 digests of the
# lowercased word. Storing them in clear text here would publish, in a public repo,
# exactly the identifiers this check exists to keep out of it. Add one with:
#
#     python3 -c "import hashlib;print(hashlib.sha256(b'name').hexdigest())"
#
# Substring forms (a name embedded in a hostname) are caught instead by the
# unrecognised-hostname check below, which works from an allow-list.
DENY_DIGESTS = {
    "3e46aed850183180e1777d724c59e617fe50f6b11253e3b23e57d2cc9f1c814f": "customer name",
    "3df303d788879992fe67ba18c411762a9751cd22dc0e511a5b919759f3686787": "customer hostname fragment",
    "86a18e6f11b02b39d554b16421d86b512627d0c422f83a84ad4e19b848401765": "customer name",
    "882ae4fc6f8d1979b8244d8bb093e5f7602bee0802f0732e3fd348844d89ca8f": "lab hostname",
    "20c57ec903dd4b97240ef1b69f86060494a181c43cc31784ba7a1dd84efb1b90": "stack hostname",
    "398e945f5817a68454aa66babba19b7b6b0f433901ec36e026e92dfe44dd7f4e": "personal username",
    "2558310e6bf593925763d96f37571887d0a9a64599e6dc5541cac5cbb9181d2d": "customer name",
    "f1308241eb02418033bca0183ceda2f65c40923e3b3210b87b057b492a3d1fbf": "customer perimeter name",
    "72d2cdc1909424897e2b5679a7908f584f2782526c943b5cd06ff6615eff0985": "customer perimeter name",
    "513d80034937ac1341ed0fd0013946e742f776f8dc3adee5b5a1e50987b3dfde": "customer application name",
    "80b7ff16ded9c7587dc18b5e7e6d5e091bc3319e954f0a15c4f3b511963c1a2e": "personal name",
    "c7cf074f027be20fd9cef6e29c679c020a4ee9ade23d94438d5149ca33e63e9f": "customer system ID",
    "0cc6af186804ec14414e0e761fc8067da2f53ade90362e396fd55dabcd6d7b74": "customer system ID",
}

# A host-naming convention leaks an environment even when the domain is a
# documentation placeholder: a name like `<prefix>host01.example.com` satisfies the
# hostname allow-list below and still says which system, region and tier it came
# from. Whole-word digests miss those, because the word being hashed is the whole
# FQDN. So these are digests of the prefix, tested against every leading substring
# of each word -- which keeps the prefixes themselves out of this file.
DENY_PREFIX_DIGESTS = {
    "09b0f033a7b54ac1a34773cca0453dd28bcb22558336efaa9a4d8a91c706aeb8": "customer hostname prefix",
    "4d068e20277ff7ecb4c6e1e0a488715c817bf15016557730d9e0d79bf5fe2627": "customer hostname prefix",
    "c60e52eb1720141d957920b24e86e713e3ee476de28c583b084bf5811d1b7d5d": "customer hostname prefix",
    "e864382fa5e9e4f1b5fb41f52ce05f736dfa75af793cfe905277b198426b6a41": "customer hostname prefix",
    "76925cd32f347bde91cea0e42ae2798de7421e4a02f3802aeb711dfab6f4a375": "customer hostname prefix",
    "b2a54e138bc6c04433c522d56bccd210cf0cc2241dcdfe17c8ef9772d15ec641": "customer hostname prefix",
    "0d6dfa80c1ac20dfe1197e99cffeaa7eff396b5133b0546138777e95944b2773": "customer hostname prefix",
    "3d063448dac60727713bb6973308752581229fd8566285946b068e7ee4fcb15d": "customer hostname prefix",
    "ab1820a8ccaa3f210334931ab62bec14bbda5b46af78d9875791ec13a4892501": "customer hostname prefix",
}

# Below four characters a prefix collides with ordinary words.
MIN_PREFIX = 4

# Optional additional digests, one "sha256  label" pair per line. Kept out of the
# repository so a longer, site-specific list can be enforced locally without publishing
# the names it is there to exclude.
DENY_DIGESTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deny-digests.txt")
if os.path.exists(DENY_DIGESTS_PATH):
    for line in open(DENY_DIGESTS_PATH, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if line:
            digest, _, label = line.partition(" ")
            DENY_DIGESTS[digest.strip()] = label.strip() or "denied identifier"

WORD = re.compile(r"[A-Za-z][A-Za-z0-9.-]{2,}")

# Hostnames and addresses that are explicitly allowed as documentation examples.
# Matched with fullmatch, so a customer label in front of one of these still
# fails: 'observability.splunkcloud.com' is allowed but
# 'customerx.observability.splunkcloud.com' is not.
ALLOWED_TOKENS = re.compile(
    r"buttercup[a-z0-9-]*\.(?:observability\.)?splunkcloud\.com"
    # Product endpoints shared by every tenant, so they identify nobody. The
    # realm is required to look like a realm ('eu1'), which is what stops a
    # customer name being waved through as a subdomain.
    r"|observability\.splunkcloud\.com"
    r"|(?:app|api|ingest)\.[a-z]{2}\d\.signalfx\.com"
    r"|127\.0\.0\.1"
    r"|(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}",
    re.I,
)

# Any host or address not on the allow-list above is treated as a real identifier.
# A customer name embedded in a hostname (customerx.splunkcloud.com) is the most
# likely way one escapes review, so this fails the build rather than warning.
SUSPICIOUS = [
    (re.compile(r"\b(?:[a-z0-9][a-z0-9-]*\.)+splunkcloud\.com\b", re.I), "hostname"),
    (re.compile(r"\b(?:[a-z0-9][a-z0-9-]*\.)+signalfx\.com\b", re.I), "hostname"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "IP address"),
]

# Every skill must say what it was validated against; without it a reader cannot
# judge whether it still applies to their release.
VERSION_HINT = re.compile(r"\b(4\.\d+|5\.\d+|10\.\d+|20\d\d-\d\d)")

errors: list[str] = []
warnings: list[str] = []


def rel(path: str) -> str:
    """Path for display. --scan is given files outside this repo, where a
    relative path would be a chain of '..' segments."""
    path = os.path.abspath(path)
    if path.startswith(REPO + os.sep):
        return os.path.relpath(path, REPO)
    return path


def parse_frontmatter(path: str, text: str):
    """Parse SKILL.md frontmatter the way the installer does.

    A regex scan is not sufficient here. An unquoted description containing a
    colon followed by a space is valid to a regex but invalid YAML -- the parser
    reads it as a nested mapping -- and the `skills` CLI silently skips any skill
    it cannot parse. Three skills shipped broken that way before this check
    existed, so the real parser is used whenever it is available.
    """
    if not text.startswith("---\n"):
        return None
    try:
        end = text.index("\n---", 4)
    except ValueError:
        return None
    raw = text[4:end]

    if yaml is not None:
        try:
            fields = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            detail = " ".join(str(exc).split())
            errors.append(
                f"{rel(path)}: frontmatter is not valid YAML -- the skills CLI will "
                f"skip this file. {detail[:180]}"
            )
            return None
        if not isinstance(fields, dict):
            errors.append(f"{rel(path)}: frontmatter did not parse to a mapping")
            return None

        def scalar(v):
            if v is None:
                return ""
            # str(True) is 'True', which would not match the 'true' the fallback
            # reads straight from the file. Keep both paths returning the same text.
            if isinstance(v, bool):
                return "true" if v else "false"
            return str(v).strip()

        return {k: scalar(v) for k, v in fields.items()}

    # Fallback: no PyYAML. Catch the one mistake that actually breaks the CLI.
    fields = {}
    lines = raw.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        m = re.match(r"^([a-z][a-z-]*):\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()

        # A block scalar holds its value in the indented lines that follow. Taking
        # the indicator itself as the value makes every folded description look two
        # characters long, which is how this fallback used to report the descriptions
        # that were converted to '>-' precisely to keep them valid.
        if re.fullmatch(r"[>|][+-]?\d*", value):
            block = []
            while i < len(lines) and (not lines[i].strip() or lines[i][:1] in " \t"):
                block.append(lines[i].strip())
                i += 1
            fields[key] = " ".join(part for part in block if part)
            continue

        if re.search(r":\s", value) and not (
            value.startswith(("'", '"'))
            and value.endswith(value[0])
        ):
            errors.append(
                f"{rel(path)}: {key!r} contains ': ' unquoted, which is invalid YAML "
                f"and makes the skills CLI skip this file -- use a '>-' block scalar"
            )
        if len(value) > 1 and value[0] in "'\"" and value.endswith(value[0]):
            value = value[1:-1]
        fields[key] = value
    return fields


def check_identifiers(path: str, text: str) -> None:
    for pattern, why in FORBIDDEN:
        for m in pattern.finditer(text):
            line = text[: m.start()].count("\n") + 1
            errors.append(f"{rel(path)}:{line}: forbidden {why} -- {m.group(0)!r}")

    for m in WORD.finditer(text):
        word = m.group(0).lower().strip(".-")
        why = DENY_DIGESTS.get(hashlib.sha256(word.encode()).hexdigest())
        for n in range(MIN_PREFIX, len(word) + 1):
            if why:
                break
            why = DENY_PREFIX_DIGESTS.get(
                hashlib.sha256(word[:n].encode()).hexdigest()
            )
        if why:
            line = text[: m.start()].count("\n") + 1
            errors.append(
                f"{rel(path)}:{line}: denied {why} -- {m.group(0)!r} "
                f"must not appear in a public repository"
            )

    for pattern, kind in SUSPICIOUS:
        for m in pattern.finditer(text):
            if ALLOWED_TOKENS.fullmatch(m.group(0)):
                continue
            line = text[: m.start()].count("\n") + 1
            errors.append(
                f"{rel(path)}:{line}: unrecognised {kind} {m.group(0)!r} -- use a "
                f"documentation placeholder, or add it to ALLOWED_TOKENS if it is one"
            )


def collect(paths: list[str]) -> list[str]:
    found = []
    for path in paths:
        if os.path.isdir(path):
            for dirpath, _dirs, filenames in os.walk(path):
                if "SKILL.md" in filenames:
                    found.append(os.path.join(dirpath, "SKILL.md"))
        elif os.path.basename(path) == "SKILL.md":
            found.append(path)
        else:
            errors.append(f"{path}: not a SKILL.md or a directory containing one")
    return sorted(found)


def scan(paths: list[str]) -> int:
    """Content checks only: no README index, plugin manifest, category allow-list
    or visibility ban, since none of those apply outside the published tree."""
    files = collect(paths)
    if not files and not errors:
        errors.append("no SKILL.md found in the given paths")

    for path in files:
        text = open(path, encoding="utf-8").read()
        if parse_frontmatter(path, text) is None and not text.startswith("---\n"):
            errors.append(f"{rel(path)}: missing YAML frontmatter")
        if not VERSION_HINT.search(text):
            warnings.append(
                f"{rel(path)}: no product version or date -- state what this was "
                f"validated against before it is shared"
            )
        check_identifiers(path, text)

    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    print(f"\n{len(files)} skill(s) scanned, {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def main() -> int:
    if not os.path.isdir(SKILLS_DIR):
        print(f"error: no skills/ directory at {SKILLS_DIR}", file=sys.stderr)
        return 1

    found: dict[str, str] = {}

    for dirpath, _dirnames, filenames in os.walk(SKILLS_DIR):
        if "SKILL.md" not in filenames:
            continue
        path = os.path.join(dirpath, "SKILL.md")
        folder = os.path.basename(dirpath)
        category = os.path.basename(os.path.dirname(dirpath))
        text = open(path, encoding="utf-8").read()

        fm = parse_frontmatter(path, text)
        if fm is None:
            # parse_frontmatter has already reported the specific reason
            if text.startswith("---\n"):
                continue
            errors.append(f"{rel(path)}: missing YAML frontmatter")
            continue

        for field in REQUIRED_FIELDS:
            if not fm.get(field):
                errors.append(f"{rel(path)}: missing required field {field!r}")

        if fm.get("name") and fm["name"] != folder:
            errors.append(
                f"{rel(path)}: name {fm['name']!r} does not match directory "
                f"{folder!r} -- the installer resolves --skill against the directory"
            )

        if category not in VALID_CATEGORIES:
            errors.append(
                f"{rel(path)}: category directory {category!r} is not one of "
                f"{sorted(VALID_CATEGORIES)}"
            )
        elif fm.get("category") and fm["category"] != category:
            errors.append(
                f"{rel(path)}: frontmatter category {fm['category']!r} does not "
                f"match directory {category!r}"
            )

        if "visibility" in fm:
            errors.append(
                f"{rel(path)}: 'visibility' field must be stripped before publishing"
            )

        desc = fm.get("description", "")
        if desc and len(desc) < 40:
            warnings.append(
                f"{rel(path)}: description is very short ({len(desc)} chars); "
                f"agents use it to decide whether to load the skill"
            )

        if not VERSION_HINT.search(text):
            errors.append(
                f"{rel(path)}: no product version or date found -- state what this "
                f"was validated against (see CONTRIBUTING.md)"
            )

        check_identifiers(path, text)
        found[folder] = os.path.join(category, folder)

    if not found:
        errors.append("no skills found under skills/")

    # README index must list every skill.
    readme_path = os.path.join(REPO, "README.md")
    if os.path.exists(readme_path):
        readme = open(readme_path, encoding="utf-8").read()
        for name in sorted(found):
            if name not in readme:
                errors.append(f"README.md: skill {name!r} is not listed in the index")
        check_identifiers(readme_path, readme)
    else:
        errors.append("README.md is missing")

    # plugin.json must match the tree, or nested skills vanish from the default menu.
    manifest_path = os.path.join(REPO, ".claude-plugin", "plugin.json")
    if os.path.exists(manifest_path):
        try:
            listed = set(json.load(open(manifest_path, encoding="utf-8")).get("skills", []))
        except json.JSONDecodeError as exc:
            errors.append(f".claude-plugin/plugin.json: invalid JSON ({exc})")
            listed = set()
        expected = {"./skills/" + p.replace(os.sep, "/") for p in found.values()}
        for missing in sorted(expected - listed):
            errors.append(f".claude-plugin/plugin.json: missing {missing}")
        for extra in sorted(listed - expected):
            errors.append(f".claude-plugin/plugin.json: lists {extra}, which is not on disk")
    else:
        errors.append(".claude-plugin/plugin.json is missing")

    if yaml is None:
        warnings.append(
            "PyYAML is not installed, so frontmatter was checked with a fallback "
            "linter rather than a real parser -- run 'pip install pyyaml'"
        )

    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)

    print(
        f"\n{len(found)} skills checked, "
        f"{len(errors)} error(s), {len(warnings)} warning(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    if "--scan" in sys.argv:
        targets = [a for a in sys.argv[1:] if a != "--scan"]
        if not targets:
            print("usage: validate_skills.py --scan PATH [PATH...]", file=sys.stderr)
            sys.exit(2)
        sys.exit(scan(targets))
    sys.exit(main())
