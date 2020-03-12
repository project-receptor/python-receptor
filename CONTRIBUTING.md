# Receptor Contributing Guidelines

Hi there! We're excited to have you as a contributor.

If you have questions about this document or anything not covered here? Come chat with us `#receptor` on irc.freenode.net

## Things to know prior to submitting code

- All code and doc submissions are done through pull requests against the `devel` branch.
- Bugfixes for a release should be submitted as a pull request against the
  release branch.  Bugfixes in releases will selectively be merged back into
  devel. 
- Take care to make sure no merge commits are in the submission, and use `git rebase` vs `git merge` for this reason.

## Setting up your development environment

We use [poetry](https://python-poetry.org) to develop **Receptor**.

```bash
(host)$ poetry install
```

## Linting and Unit Tests

* Use `flake8` for linting.
* Use `pytest` for unit tests.
