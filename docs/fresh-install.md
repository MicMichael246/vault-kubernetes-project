# Fresh Installation Guide

This guide describes how to recreate the Vault + Kubernetes + PostgreSQL security lab from repository manifests.

**Scope:** This is a local learning lab, not a production deployment. The Vault configuration disables TLS and uses standalone file storage. Production environments require appropriate TLS, high availability, access controls, backups, and monitoring.

## 1. Prerequisites

Install and verify the following tools:

- Docker
- Minikube
- `kubectl`
- Helm
- Python 3 on the workstation for local validation commands
- Git, if you intend to publish the project

Start Minikube and verify the cluster:

```bash
minikube start
kubectl get nodes
helm version
kubectl version --client
```

Confirm that the Kubernetes node is ready before proceeding.

## 2. Review the Repository Configuration

Important files:

- `vault/values.yaml` — Vault Helm configuration and persistent storage.
- `vault/policies/app-policy.hcl` — least-privilege Vault policy for the application.
- `database/postgres.yaml` — PostgreSQL Service and StatefulSet.
- `kubernetes/vault-demo-app.yaml` — application deployment and Vault Agent Injector annotations.
- `app/` — application source, Dockerfile, and tests.

Review these files before applying them. Do not commit actual passwords, Vault tokens, unseal keys, or other credentials.

## 3. Create the Database Namespace and Admin Secret

The PostgreSQL manifest expects the `database` namespace and a Secret named `postgres-admin`, containing the key `password`.

Create the namespace:

```bash
kubectl create namespace database
```

Create the Secret interactively, without putting the password directly into shell history:

```bash
read -rsp "PostgreSQL admin password: " POSTGRES_ADMIN_PASSWORD
echo
kubectl create secret generic postgres-admin \
  -n database \
  --from-literal=password="$POSTGRES_ADMIN_PASSWORD"
unset POSTGRES_ADMIN_PASSWORD
```

If the namespace or Secret already exists, inspect it before making changes. Do not overwrite existing resources blindly.

Deploy PostgreSQL:

```bash
kubectl apply -f database/postgres.yaml
kubectl rollout status statefulset/postgres -n database --timeout=180s
kubectl get pods -n database
kubectl get svc postgres -n database
```

Wait until PostgreSQL is ready before continuing.

## 4. Vault Deployment and Initialization

Install Vault using the repository's Helm values:

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update
helm upgrade --install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --values vault/values.yaml
```

Check the release and Pod:

```bash
helm list -n vault
kubectl get pods -n vault
```

For a genuinely fresh Vault installation, initialize Vault exactly once and securely store the resulting unseal keys and initial root token outside the repository. Unseal Vault using the required key shares.

**Never run `vault operator init` against an existing initialized Vault.** Initialization material is sensitive and must never be pasted into project documentation or committed to version control.

The remaining sections of this guide document Vault authentication, policies, application secrets, and dynamic PostgreSQL credentials. Complete and verify these steps before deploying the application.

## 5. Configure Vault Authentication and Secrets

Complete these steps only after Vault has been installed, initialized, unsealed, and is ready to accept configuration.

### Verified Configuration

The current working lab uses these settings:

| Component | Value |
|---|---|
| Kubernetes auth mount | `auth/kubernetes` |
| Kubernetes API | `https://10.96.0.1:443` |
| Kubernetes ServiceAccount | `vault-auth-test` |
| ServiceAccount namespace | `default` |
| Vault role | `vault-auth-test` |
| Vault policy | `app-policy` |
| KV v2 mount | `secret/` |
| Static application secret path | `secret/data/app/config` |
| Database secrets engine | `database/` |
| Database connection | `postgres-database` |
| Dynamic database role | `app-readonly` |
| Default credential TTL | 2 minutes |
| Maximum credential TTL | 5 minutes |

The Vault role binds the `vault-auth-test` ServiceAccount in the `default` namespace and issues tokens with the `app-policy` policy. The role's token TTL is 3600 seconds.

### Apply the Application Policy

From the repository root, review the policy and write it to Vault:

```bash
vault policy read app-policy
vault policy write app-policy vault/policies/app-policy.hcl
```

The first command is a check; the second updates the policy. Run these commands only after authenticating to the intended fresh Vault instance with an appropriately privileged bootstrap token.

The policy should grant read access only to:

- `secret/data/app/config`
- `database/creds/app-readonly`

Do not place root tokens, unseal keys, or secret values in this guide.

### Important Before Continuing

The remaining configuration requires a Kubernetes authentication setup, a KV v2 application secret, and a PostgreSQL database connection and dynamic role. Recreate these using the documented names and values, but use the actual Kubernetes CA and reviewer-token configuration appropriate to the fresh cluster rather than assuming that the current cluster's auth settings will transfer unchanged.

### Kubernetes Authentication Configuration

The working lab enables Vault's Kubernetes authentication method at `auth/kubernetes/`.

The verified configuration uses the Kubernetes API address `https://10.96.0.1:443`, with issuer validation disabled. No explicit Kubernetes CA certificate or token reviewer JWT is configured in the auth configuration.

Vault can use its in-cluster service account credentials for Kubernetes authentication when the deployment and permissions support that approach. A fresh installation must verify the appropriate authentication method, API address, CA trust, and token-review permissions for its own cluster. Do not assume the API address or service-account configuration will be identical across environments.

The application uses the Kubernetes ServiceAccount `vault-auth-test` in the `default` namespace. The Vault role of the same name binds to that ServiceAccount and grants the `app-policy` policy.

**Security note:** Disabling issuer validation is a configuration choice verified in this local lab, not a universal recommendation. Reassess it for the target Kubernetes and Vault versions before deploying outside a disposable learning environment.

**Verification commands:**

```bash
kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault read auth/kubernetes/config'

kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault read auth/kubernetes/role/vault-auth-test'
```

Review the output locally and redact any sensitive data before sharing it. Never publish service-account tokens, reviewer JWTs, or private key material.

#### Vault Kubernetes Auth Role

The verified Vault role is named `vault-auth-test`.

| Setting | Value |
|---|---|
| Vault auth role | `vault-auth-test` |
| Bound ServiceAccount | `vault-auth-test` |
| Bound namespace | `default` |
| Assigned policy | `app-policy` |
| Token audience | `https://kubernetes.default.svc.cluster.local` |
| Vault token TTL | 1 hour |

The role restricts authentication to the specified ServiceAccount and namespace. The assigned `app-policy` grants read access to the application's static KV secret and dynamic database credentials, as defined in `vault/policies/app-policy.hcl`.

**Verification command:**

```bash
kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault read auth/kubernetes/role/vault-auth-test'
```

When recreating the lab, configure the Kubernetes auth method and role for the target cluster before deploying the application. Verify the ServiceAccount name, namespace, audience, policy, and TTL rather than assuming the existing role is present.

### PostgreSQL Least-Privilege Role

The lab uses a PostgreSQL group role named `app_readonly`. Vault generates temporary login roles and grants them membership in this group role.

The following permissions were verified against the running database:

| Permission | Result |
|---|---|
| Connect to `appdb` | Allowed |
| Use the `public` schema | Allowed |
| Create objects in the schema | Denied |
| Read `public.vault_demo` | Allowed |
| Insert, update, or delete table rows | Denied |

The group role itself cannot log in, is not a superuser, and cannot create databases or roles. These restrictions reduce the impact of compromised application credentials.

**Verification command:**

```bash
kubectl exec -n database postgres-0 -- \
  psql -U postgres -d appdb -c \
  "SELECT
     has_database_privilege('app_readonly', 'appdb', 'CONNECT') AS can_connect,
     has_schema_privilege('app_readonly', 'public', 'USAGE') AS schema_usage,
     has_schema_privilege('app_readonly', 'public', 'CREATE') AS can_create_in_schema,
     has_table_privilege('app_readonly', 'public.vault_demo', 'SELECT') AS can_select,
     has_table_privilege('app_readonly', 'public.vault_demo', 'INSERT') AS can_insert,
     has_table_privilege('app_readonly', 'public.vault_demo', 'UPDATE') AS can_update,
     has_table_privilege('app_readonly', 'public.vault_demo', 'DELETE') AS can_delete;"
```

This query inspects permissions without displaying passwords or secret values. Repeat it after recreating the database to confirm that the expected permissions have been applied.

### Application Secret Requirements

The deployment in `kubernetes/vault-demo-app.yaml` uses the Vault Agent Injector to authenticate and render two secrets into files inside the application Pod.

| Purpose | Vault path | Required content |
|---|---|---|
| Static application configuration | `secret/data/app/config` | `username` and `password` fields |
| Dynamic database credentials | `database/creds/app-readonly` | JSON containing the generated database username and password |

The KV path uses the KV version 2 data API. In Vault CLI commands, use the mount and relative path:

```bash
vault kv put -mount=secret app/config \
  username="demo-user" \
  password="replace-with-a-local-demo-value"
```

**Important:** This example creates a demonstration secret. Use a non-sensitive local test value, never a real account password. The command creates or updates a KV entry, so run it only against the intended fresh lab and not against an existing secret you need to preserve.

The deployment references the `vault-auth-test` Kubernetes ServiceAccount in the `default` namespace and the Vault role `vault-auth-test`. Both must exist and be correctly configured before the application can authenticate.

The Vault policy must permit reading `secret/data/app/config` and `database/creds/app-readonly`. The database secrets engine must also have a working PostgreSQL connection and a configured `app-readonly` dynamic role.

The manifest uses `imagePullPolicy: Never`; build `vault-demo-app:1.1.0` inside Minikube before deploying it.

These requirements describe the existing manifest. They do not replace the Kubernetes authentication and database-engine setup steps needed to recreate the lab from scratch.


### PostgreSQL Connection Details for Vault

The PostgreSQL Service runs in the `database` namespace. Vault's database secrets engine connects to it using Kubernetes Service DNS.

| Setting | Value |
|---|---|
| Host | `postgres.database.svc` |
| Port | `5432` |
| Database | `appdb` |
| Administrative username | `postgres` |
| Vault database connection name | `postgres-database` |
| Dynamic role name | `app-readonly` |

The connection URL format used by this lab is:

```text
postgresql://{{username}}:{{password}}@postgres.database.svc:5432/appdb?sslmode=disable
```

The `{{username}}` and `{{password}}` placeholders are resolved by Vault using the administrative database credentials configured for the connection. They are not literal credentials.

The administrative password must come from the locally created `postgres-admin` Kubernetes Secret. Do not copy its value into this guide, a manifest, or a Git commit.

**Security note:** This local lab disables TLS. Do not use this connection configuration unchanged for a production database. Production deployments should use TLS and an appropriately restricted database account for credential management.

The verified Vault database connection configuration has these additional properties:

| Setting | Value |
|---|---|
| Allowed dynamic roles | `app-readonly` only |
| Verify connection | Enabled |
| Administrative database username | `postgres` |

Vault stores the database connection's administrative password separately from the returned `connection_details` fields. The password must be supplied securely when configuring the connection; it must not be committed to this repository.

**Verification:** To inspect the connection without printing the stored password, run this command from the workstation, where `jq` is installed:

```bash
kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault read -format=json database/config/postgres-database' |
jq '{
  allowed_roles: .data.allowed_roles,
  verify_connection: .data.verify_connection,
  connection_url: .data.connection_details.connection_url,
  database_username: .data.connection_details.username,
  password_field_present: (.data.connection_details | has("password"))
}'
```

The command displays the URL template, not the actual database password. Run it only against the intended Vault instance.

For a fresh installation, obtain the administrative password from the `postgres-admin` Kubernetes Secret and supply it through a protected input mechanism when configuring Vault. Do not embed the password in a shell command, manifest, documentation, or Git commit. The Vault pod's default ServiceAccount does not have permission to read this Secret in the `database` namespace, so do not assume Vault can retrieve it directly from Kubernetes.

#### Vault Database Connection Configuration

Vault's database secrets engine uses the PostgreSQL database plugin to connect to the `appdb` database through the Kubernetes Service `postgres.database.svc`.

The verified connection configuration has these properties:

| Setting | Value |
|---|---|
| Connection name | `postgres-database` |
| Plugin | `postgresql-database-plugin` |
| Allowed dynamic role | `app-readonly` |
| Verify connection on configuration | Enabled |

The connection's administrative username is `postgres`. Its password must be supplied securely from the `postgres-admin` Kubernetes Secret when configuring Vault. Do not place the password in source code, shell scripts, manifests, or documentation.

The database connection must be configured successfully before creating the `app-readonly` dynamic role. The connection and role are separate Vault database-engine objects.

**Verification commands:**

```bash
kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault list database/config'

kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault read database/roles/app-readonly'
```

These commands verify the configured connection names and dynamic role settings without requesting a new set of live database credentials.

#### Configure the Database Connection During Fresh Installation

**Preflight checks**

**Do not overwrite an existing connection**

If `postgres-database` appears in `vault list database/config`, stop and inspect the existing configuration. Do not run the fresh-install creation command against that connection.

The current lab already has a working `postgres-database` connection. All remaining configuration examples in this subsection are intended only for a fresh installation where the connection does not yet exist.

Before creating the connection, verify that PostgreSQL is ready and that Vault is initialized, unsealed, and authenticated.

```bash
kubectl rollout status statefulset/postgres -n database --timeout=180s
kubectl get secret postgres-admin -n database
kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault status'
kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault list database/config'
```

If `postgres-database` already exists, inspect and verify it instead of overwriting it. The commands above do not display the database password.

After PostgreSQL is ready, the `postgres-admin` Secret exists, and Vault is initialized and unsealed, configure the database secrets engine.

First, verify the Secret exists and the Vault CLI is authenticated. Do not display the Secret's value or Vault token.

The database connection requires:

- Connection name: `postgres-database`
- PostgreSQL plugin: `postgresql-database-plugin`
- Connection URL: `postgresql://{{username}}:{{password}}@postgres.database.svc:5432/appdb?sslmode=disable`
- Administrative username: `postgres`
- Allowed dynamic role: `app-readonly`

The administrative password must be read from the `postgres-admin` Secret in namespace `database` and supplied securely to Vault. Do not write the password into a manifest, a tracked script, or this guide.

**Important security and authentication notes**

- These instructions describe a fresh installation only. Do not overwrite an existing `postgres-database` connection.
- Authenticate the Vault CLI to the intended Vault instance using an authorized token before configuring the connection. Do not assume a newly deployed Vault Pod is already authenticated.
- Retrieve the PostgreSQL administrator password from the `postgres-admin` Secret in the `database` namespace. Supply it through a protected input mechanism supported by the Vault CLI; never print it or hardcode it in a command, manifest, tracked script, or documentation.
- Do not grant Vault's default Kubernetes ServiceAccount additional permissions to read the PostgreSQL Secret merely to simplify configuration.
- After configuring the connection, verify its name and allowed roles without displaying stored credentials. Confirm that the connection works before creating the `app-readonly` dynamic role.

#### Create the Dynamic PostgreSQL Role

Role-creation instructions will be added after the write procedure has been validated against the installed Vault CLI. Do not overwrite an existing role.

### Dynamic PostgreSQL Credentials

The Vault database secrets engine uses the connection named `postgres-database` and the dynamic role `app-readonly`.

The verified role configuration uses these SQL templates:

**Creation statements**

```sql
CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';
GRANT app_readonly TO "{{name}}";
```

**Revocation statements**

```sql
REVOKE app_readonly FROM "{{name}}";
DROP ROLE IF EXISTS "{{name}}";
```

Vault substitutes the generated role name, password, and expiration when issuing credentials. The generated login receives the privileges of the `app_readonly` group role, rather than PostgreSQL administrator privileges.

| Setting | Value |
|---|---|
| Database connection | `postgres-database` |
| Dynamic role | `app-readonly` |
| Default credential TTL | 2 minutes |
| Maximum credential TTL | 5 minutes |
| Credential type | Password |

The configured maximum is a limit, not a guarantee that every issued credential remains valid for five minutes. Validate the effective lease duration and application behavior in the target environment.

**Verification command:**

```bash
kubectl exec -n vault vault-0 -- sh -c \
  'export VAULT_ADDR=http://127.0.0.1:8200; vault read database/roles/app-readonly'
```

This command displays role configuration, not the generated credentials. Do not use `vault read database/creds/app-readonly` in a shared terminal or capture its output in public logs, because it returns a live username and password.

