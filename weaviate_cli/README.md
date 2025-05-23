How to Use the Weaviate CLI Tool (Client v4.14+ Syntax)
This command-line tool allows you to manage Weaviate collections, API key user_ids, and roles with their permissions directly. It uses the weaviate-client v4.14+ syntax.

CRITICAL COMPATIBILITY WARNING:

This script is designed for Weaviate server versions 1.18.0 and newer (ideally v1.23+ or your v1.30.x for best feature alignment).

Using this script with an older Weaviate server is highly likely to result in errors.

Ensure your Weaviate server is compatible with weaviate-client v4.x and supports direct role management via the client if you intend to use those features.

Prerequisites:

Python: Ensure you have Python 3.8+ installed.

Libraries: Install weaviate-client v4.14.0 or newer, and pyyaml:

pip install "weaviate-client>=4.14.0,<5.0.0" pyyaml

If you have an older version, uninstall it first.
Run python -c "import weaviate; print(weaviate.__version__)" to confirm your active client version. The script will also print this at startup.

Weaviate Instance: A running Weaviate instance (v1.18.0+, ideally v1.23+ or your v1.30.x).

Saving the Script:

Save the Python script above as weaviate_cli_v4.py (or your preferred name, e.g., weaviate_cli_commands.py).

General Usage:

python weaviate_cli_v4.py [--config-file <PATH_TO_YAML>] [--url <WEAVIATE_URL>] [--api-key <API_KEY>] [--grpc-host <GRPC_HOST>] [--grpc-port <GRPC_PORT>] <COMMAND> <SUBCOMMAND> [options...]

Global Options (Order of Precedence: CLI > YAML > Environment > Prompt):

--config-file <PATH_TO_YAML>: (Optional) Path to a YAML configuration file for connection details.

--url <WEAVIATE_URL>: (Optional if in config file) The full URL of your Weaviate instance.

--api-key <API_KEY> (or --root-key): (Optional if in config file or env var) Your Weaviate Admin API key. Required for most operations.

--grpc-host <GRPC_HOST>: (Optional if in config file) Hostname for the gRPC connection.

--grpc-port <GRPC_PORT>: (Optional if in config file) Port for the gRPC connection.

--recreate-api-key: (Optional, specific to user create) If set, an existing API key for the user_id will be deleted and a new one generated.

YAML Configuration File (--config-file) Structure:

# connection_config.yaml
weaviate_url: "https://your-weaviate-instance.com"
api_key: "your-secret-admin-api-key" 
grpc_host: "your-grpc-host.weaviate.com" 
grpc_port: 443 

Available Commands:

Collection Management (collection)
collection create: Create a new collection.

--name <NAME> (Required), --description <DESC>, --property <PROP_SPEC>, --vectorizer <TYPE>, etc.

collection delete: Delete a collection. (--name <NAME>)

collection list: List all collections. (--detailed for more info)

collection describe: Show configuration of a collection. (--name <NAME>)

User (API Key User ID) Management (user)
Manages user_ids and their associated API keys. Roles are assigned to these user_ids.

user create: Create a new user_id and generate an API key for it.

--user-id <USER_ID>: (Required) The identifier for this API key principal.

--role <ROLE_NAME>: (Optional) Assign a role name. Repeat for multiple roles.

user delete: Delete a user_id and its associated API key(s).

--user-id <USER_ID>: (Required).

user list: List all user_ids that have API keys and show their assigned roles.

user update-roles: Set/replace roles for a user_id.

--user-id <USER_ID>: (Required).

--role <ROLE_NAME>: (Optional) New list of roles. Omitting all --role options removes all roles.

Role Management (role)
Directly manages roles and their permissions on the Weaviate server.

role create: Create a new role with specified permissions directly on the server.

--role-name <NAME>: (Required) The name of the role.

--collection-pattern <PATTERN>: (Required) Collection pattern(s) this rule applies to (e.g., "MyCollection*", "*"). Can be specified multiple times.

--allow-data-create/--allow-data-read/--allow-data-update/--allow-data-delete: (Flags) Grant respective data operations.

--allow-collection-create/--allow-collection-read-config/--allow-collection-update-config/--allow-collection-delete: (Flags) Grant respective collection schema/config operations.

role delete: Delete a role from the server.

--role-name <NAME>: (Required).

role get: Get details (including permissions) of a specific role from the server.

--role-name <NAME>: (Required).

role list: List all roles defined on the server.

--detailed: (Optional flag) Show permissions for each role.

Example Workflow:

Create a role with specific permissions:

python weaviate_cli_v4.py --url <URL> --api-key <ADMIN_KEY> role create \
    --role-name "product_editor" \
    --collection-pattern "Product*" \
    --allow-data-read --allow-data-create --allow-data-update \
    --allow-collection-read-config

Create a user_id for an application/service, generate its API key, and assign it the role:

python weaviate_cli_v4.py --url <URL> --api-key <ADMIN_KEY> user create \
    --user-id "inventory_service_account" \
    --role "product_editor" 

(Securely store the generated API key for "inventory_service_account")

List defined roles:

python weaviate_cli_v4.py --url <URL> --api-key <ADMIN_KEY> role list --detailed

List user_ids and their assigned roles:

python weaviate_cli_v4.py --url <URL> --api-key <ADMIN_KEY> user list
