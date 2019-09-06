# Receptor Contributing Guidelines

Hi there! We're excited to have you as a contributor.

If you have questions about this document or anything not covered here? Come chat with us `#receptor` on irc.freenode.net

## Things to know prior to submitting code

- All code and doc submissions are done through pull requests against the `master` branch.
- Take care to make sure no merge commits are in the submission, and use `git rebase` vs `git merge` for this reason.

## Setting up your development environment

It's entirely possible to develop on **Receptor** simply with

```bash
(host)$ python setup.py develop
```

## Linting and Unit Tests

* Use `flake8` for linting.
* Use `pytest` for unit tests.