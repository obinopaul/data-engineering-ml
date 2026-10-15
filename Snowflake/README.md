# Snowflake: setup, authentication and verification

## View loaded data

In Snowflake's web interface (Snowsight), open a SQL worksheet and run:

```sql
USE ROLE INTERVIEW_ROLE;
USE WAREHOUSE COMPUTE_WH;
SELECT * FROM INTERVIEW_DB.RAW.SAMPLE_TABLE;
SELECT * FROM INTERVIEW_DB.ANALYTICS.MY_FIRST_DBT_MODEL;
SELECT * FROM INTERVIEW_DB.ANALYTICS.MY_SECOND_DBT_MODEL;
```

The Results grid shows the rows. `SAMPLE_TABLE` contains the two synthetic rows from `data/practice.csv`. `_DLT_*` tables and columns track ingestion; `RAW_STAGING` is dlt's merge workspace. The loaded source rows belong in `RAW`.

To load actual oilfield data, run from `main/`:

```bash
python -m Ingestion.run Ingestion/volve_wireline_gr.example.yml
```

Then query `SELECT * FROM INTERVIEW_DB.RAW.VOLVE_WIRELINE_GR LIMIT 100;` in the worksheet. This loads the supplied 1,245-row wireline dataset into its own table. Preview commands alone do not load anything. Default dbt models still read `SAMPLE_TABLE`; adapting them to wireline data requires selecting that source and writing the intended transformations.

## Connection settings

| Setting | Purpose | Current value |
|---|---|---|
| Account/user | Where you connect and who signs in | Your values in `dbt/profiles.yml` |
| Warehouse | Compute that executes queries | Existing `COMPUTE_WH` |
| Database | Container for stored tables and schemas | `INTERVIEW_DB`, created by setup SQL |
| Schema | Groups tables inside the database | `RAW` for ingestion; `ANALYTICS` for dbt |
| Role | Permissions for the signed-in user | `INTERVIEW_ROLE`, created and assigned by setup |

A profile selects these objects; it does not create them. The connector is installed. Successful cloud login and provisioning still require verification; having a populated profile alone does not establish either.

## Create the database and role once

Open [sql/000_bootstrap.sql](sql/000_bootstrap.sql) in a Snowsight SQL worksheet and run the whole file as your existing admin user. It:

1. Uses SYSADMIN to create `INTERVIEW_DB`, `RAW`, `STAGING` and `ANALYTICS` if missing.
2. Uses SECURITYADMIN to create `INTERVIEW_ROLE` and grant warehouse/database/schema permissions.
3. Grants the role to **the user running the script**, using `CURRENT_USER()`.
4. Switches to `INTERVIEW_ROLE`, disables secondary roles for the checks, and verifies temporary-table writes in RAW and ANALYTICS. The final row should contain `INTERVIEW_ROLE, 1, 1`.

It reuses `COMPUTE_WH` and creates no warehouse or new user. It also checks the staging-schema permission needed by dlt. If your login lacks the admin roles, an account administrator must run the provisioning steps and grant `INTERVIEW_ROLE` to your actual login as well.

If an earlier setup attempt reported `Unsupported feature 'assignment from non-constant source expression'`, rerun `python Snowflake/connection.py --setup` with the corrected script. Generated temporary-table names now use `SET ... = (SELECT ...)`, following [Snowflake's query-based variable assignment](https://docs.snowflake.com/en/sql-reference/session-variables). Earlier successful role/database grants remain in place after a later SQL failure. Repeating this setup preserves existing objects and uses new temporary test tables. A normal connection succeeding proves access, but the final `INTERVIEW_ROLE, 1, 1` result is still needed to verify both write checks.

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

### If login says “Incorrect username or password”

This is an authentication rejection. `--login-only` does not select the interview role, database, schema or warehouse, so creating those objects will not resolve this error. A configured password can still be the wrong credential for the selected account/user.

Sign into the intended account in Snowsight. In a worksheet, run this statement on its own:

```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS ACCOUNT_IDENTIFIER,
       CURRENT_USER() AS USER_OBJECT_NAME;
```

Then highlight and run only this statement, and inspect its result grid directly:

```sql
SHOW USERS;
```

Find the row whose `name` matches `USER_OBJECT_NAME` above. Compare `ACCOUNT_IDENTIFIER` with the profile's `account` and that row's `login_name` with its `user`. A display name/email/user object name is not necessarily the login name. If `login_name` is NULL, the active role may lack permission to view it; use your existing account-administration role or ask the administrator to check. [Snowflake SHOW USERS reference](https://docs.snowflake.com/en/sql-reference/sql/show-users).

Do not run the earlier `RESULT_SCAN(LAST_QUERY_ID())` filter: it depends on which query ran immediately before it. If it scans a different result, columns such as `"name"` may not exist and produce an invalid-identifier error.

Verify the actual Snowflake password for that same account in a fresh browser sign-in; an existing browser session does not verify the current password. If you use SSO, an identity-provider password is not necessarily a Snowflake password: configure the supported SSO flow instead. Keep the credential only in `main/.env`, never in chat or a SQL worksheet. A quoted `.env` value protects spaces and `#`; quotes are parsed by python-dotenv.

After correcting the local values, retry from `main/`:

```bash
unset SNOWFLAKE_PASSWORD
python Snowflake/connection.py --login-only
```

`unset` clears only this shell's exported value, allowing the script to read the updated `.env`; it does not delete the file entry. Existing exported values otherwise take precedence. Complete the configured MFA step when requested. Proceed to the normal connection and dbt checks only after login succeeds.

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
