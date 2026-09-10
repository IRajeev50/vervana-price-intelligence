# CI workflow (temporarily relocated)

`ci.yml.disabled` is the GitHub Actions workflow. It was moved here out of
`.github/workflows/` only because the initial push used a token without the
`workflow` OAuth scope (GitHub blocks pushing workflow files without it).

To enable CI:

```bash
gh auth refresh -h github.com -s workflow      # approve in browser
git mv ci/ci.yml.disabled .github/workflows/ci.yml
git commit -m "ci: restore GitHub Actions workflow"
git push
```
