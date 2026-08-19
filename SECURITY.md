# Security

## Vulnerabilities in Splunk products

If you have found a security vulnerability in Splunk IT Service Intelligence, the Splunk
platform, or any other Splunk product, report it to
[Splunk Product Security](https://advisory.splunk.com/report).

**Do not report product vulnerabilities here.** This is not an official Splunk repository
and has no route into Splunk's security process.

## Problems with this repository

For security problems in the repository itself — a skill that leaks credentials into
logs, an unsafe command, a dependency issue, or exposed information that should not be
public — use GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository rather than opening a public issue.

## Credential handling

No skill in this repository should ever contain a real credential, token, hostname, IP
address, or customer name. Skills reference credentials through environment variables
(for example `ITSI_URL` and `ITSI_TOKEN`) and use documentation placeholders elsewhere.

If you find anything that looks like a real secret or a real customer identifier in this
repository, report it privately using the link above rather than opening a public issue.
Note that scrubbing a value from the current files does not remove it from Git history,
so these reports are treated as urgent.

CI runs a secret scan and an identifier check on every push and pull request, but neither
is a substitute for review.
