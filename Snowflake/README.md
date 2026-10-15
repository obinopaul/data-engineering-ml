# Snowflake: setup, authentication and verification

## What the names mean

| Setting | Purpose | Current value |
|---|---|---|
| Account/user | Where you connect and who signs in | Your values in `dbt/profiles.yml` |
| Warehouse | Compute that executes queries | Existing `COMPUTE_WH` |
| Database | Container for stored tables and schemas | `INTERVIEW_DB`, created by setup SQL |
| Schema | Groups tables inside the database | `RAW` for ingestion; `ANALYTICS` for dbt |
| Role | Permissions for the signed-in user | `INTERVIEW_ROLE`, created and assigned by setup |

A profile selects these objects; it does not create them. Local scripts have been prepared, but cloud creation and login are not verified in this session: package downloads are blocked by DNS and the connector is absent.

## Create the database and role once

Open [sql/000_bootstrap.sql](sql/000_bootstrap.sql) in a Snowsight SQL worksheet and run the whole file as your existing admin user. It:

1. Uses SYSADMIN to create `INTERVIEW_DB`, `RAW`, `STAGING` and `ANALYTICS` if missing.
2. Uses SECURITYADMIN to create `INTERVIEW_ROLE` and grant warehouse/database/schema permissions.
3. Grants the role to **the user running the script**, using `CURRENT_USER()`.
4. Switches to `INTERVIEW_ROLE`, disables secondary roles for the checks, and verifies temporary-table writes in RAW and ANALYTICS. The final row should contain `INTERVIEW_ROLE, 1, 1`.

It reuses `COMPUTE_WH` and creates no warehouse or new user. It also checks the staging-schema permission needed by dlt. If your login lacks the admin roles, an account administrator must run the provisioning steps and grant `INTERVIEW_ROLE` to your actual login as well.

Your [RBAC lab](../snowflake_rbac_lab.sql) demonstrates the same object → privileges → user pattern. Its analyst role has read access; ingestion/dbt need permission to create and modify their own output tables. We do not run the lab's separate user creation as part of this setup. RBAC means **role-based access control**: authentication proves identity, while role grants control permitted actions.

The older `001`, `002` and `003` SQL files remain individual examples; use the complete `000_bootstrap.sql` for this workflow. Do not run `002` to create another warehouse.

## Your password and authenticator

Your ignored `main/.env` already contains `SNOWFLAKE_PASSWORD`. The profile references it without storing another copy:

```yaml
authenticator: username_password_mfa
password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"
```

The Python helper uses python-dotenv to read `.env` as configuration. Quoted values are supported; surrounding quotes are not part of the password. Existing exported variables take precedence. Never send the password in chat. No Snowflake API key is required for this connector flow.

`username_password_mfa` uses your password with Snowflake's MFA flow. Approve the registered factor if prompted; your account policy determines which factors are accepted. A password alone may not satisfy that policy. `externalbrowser` instead opens your browser for configured SSO; it does not mean that the script reads a password from `.env`. [Connector authentication reference](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect).

From `main/`, after package installation:

```bash
source .venv/bin/activate
python Snowflake/connection.py --login-only
python Snowflake/connection.py --setup  # alternative to running the SQL in Snowsight
python Snowflake/connection.py
python Snowflake/connection.py --dbt debug
```

`--login-only` omits the interview database/role so it can test authentication before setup. `--setup` connects with your existing ACCOUNTADMIN access and runs the fixed setup SQL. With no options, the helper selects the working role/database/schema and prints the session context.

`--dbt debug` loads `.env`, then launches `.venv/bin/dbt` against this workspace. Direct `dbt` commands do not automatically read `.env`; use this launcher for `build`, `test`, `parse` and other project commands too. Ingestion loads the same profile and environment itself.

## Unattended login for Airflow and streaming

Password/MFA and browser login can require human interaction. Use a registered key pair before scheduling jobs. Generate a dedicated encrypted key with unused filenames:

```bash
mkdir -p .cache/keys
openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 aes-256-cbc -inform PEM -out .cache/keys/snowflake_key.p8
openssl pkey -in .cache/keys/snowflake_key.p8 -pubout -out .cache/keys/snowflake_key.pub
chmod 600 .cache/keys/snowflake_key.p8
```

Using a role allowed to alter your user, register only the public key's base64 body (omit BEGIN/END lines and line breaks):

```sql
ALTER USER YOUR_USERNAME SET RSA_PUBLIC_KEY='PUBLIC_KEY_BODY';
```

Change the profile to `authenticator: snowflake_jwt`, **remove its `password` entry**, and set an absolute `private_key_path` plus `private_key_passphrase`. Then repeat the connection and dbt checks. [Key-pair reference](https://docs.snowflake.com/en/user-guide/key-pair-auth).

The shared helper supports plain YAML values and exact `env_var('NAME')` references, not arbitrary Jinja. Importing it opens no connection. For files/API/SQL loading, see [Ingestion](../Ingestion/README.md).
