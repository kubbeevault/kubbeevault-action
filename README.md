# Kubbeevault Secrets Action

Publish the contents of this directory at the root of a shared GitHub repository,
for example `kubbeetech/kubbeevault-action`, and create a `v1` release tag.
The example repository reference below is a proposed publication location.
No Python packages or build step are required. Runners need Bash and Python 3.6+;
Ubuntu GitHub-hosted runners provide both.

```yaml
name: Application pipeline
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  application:
    runs-on: ubuntu-latest
    steps:
      - name: Load database credentials
        uses: kubbeevault/kubbeevault-action@v1.0.0
        with:
          url: ${{ vars.KUBBEEVAULT_URL }}
          token: ${{ secrets.KUBBEEVAULT_TOKEN }}
          krn: ${{ vars.KUBBEEVAULT_KRN }}
          secrets: |
            username: DB_USERNAME
            password: DB_PASSWORD
            host: DB_HOST
      - name: Use credentials
        run: |
          # Replace with your application command, which reads these variables.
          test -n "$DB_USERNAME"
          test -n "$DB_PASSWORD"
          test -n "$DB_HOST"
```

Use the same mapping syntax for one or more keys. Each nonblank line is a
literal secret key followed by a colon and an environment variable name. This
is a line-oriented format, not a YAML document: do not quote keys or add comments.
The final colon separates the key from the variable name. Variables must use
letters, digits, and underscores and cannot start with a digit. Reserved runner,
action, and process configuration names are rejected, as are duplicate variable
names (case insensitive).

The URL is the server origin, optionally with a gateway prefix. Do not include
`/vault-app/vaults/integration/GITHUB_ACTIONS`; the action appends it. HTTPS is
required except for localhost development. A hosted runner cannot access a
developer's localhost; use a reachable service or an appropriately connected
self-hosted runner.

The action sends one GET request with `KubbeeAccessToken: Bearer <token>` and
`KubbeeVaultKRN: <krn>`. Tokens may be supplied with or without `Bearer`.
It verifies the returned KRN, validates every selected key, masks the selected
values, and writes multiline-safe values to `GITHUB_ENV`. HTTP redirects are
rejected, requests time out after 30 seconds, and response bodies are never logged.
The token must be authorized by the server for the requested vault.

Subsequent steps in the same job can use `$DB_USERNAME` in Bash or
`${{ env.DB_USERNAME }}` in action inputs. Each separate job must load its own
secrets. There are no secret job outputs or artifacts. Exported secrets are
available to subsequent steps, so run this action only in trusted workflows.

For local repository testing after checkout, use `uses: ./kubbeevault-action`.
For shared production use, publish the directory as described above; consumers
can pin an immutable commit SHA instead of a moving version tag.

Run unit tests with:

```sh
python3 -m unittest discover -s tests -v
```
