# weaviate_cli_commands.py
# Command-based CLI tool for Weaviate, using weaviate-client v4.14+ syntax.
# Manages collections, API key user_ids, and roles with permissions.
# WARNING: This client version is intended for Weaviate server v1.18.0+ (ideally v1.23+).

import os
import yaml 
import weaviate 
import weaviate.classes as wvc 
import weaviate.config as wc_config 
from weaviate.classes.rbac import Permissions # Correct import for Permissions
from weaviate.auth import AuthApiKey
from weaviate.exceptions import WeaviateQueryException, WeaviateConnectionError, WeaviateStartUpError
import argparse
import getpass
import json 
from urllib.parse import urlparse

# Global client variable
client = None

def print_client_version():
    """Prints the installed weaviate-client version."""
    try:
        print(f"Using weaviate-client version: {weaviate.__version__}")
        if not weaviate.__version__.startswith("4."):
             print("WARNING: This script is designed for weaviate-client v4.x.")
    except Exception as e:
        print(f"Could not determine weaviate-client version: {e!r}")


def load_config_from_yaml(file_path):
    """Loads configuration from a YAML file."""
    try:
        with open(file_path, 'r') as f:
            config = yaml.safe_load(f)
            print(f"Loaded configuration from {file_path}")
            return config if config else {}
    except FileNotFoundError:
        print(f"Warning: Config file not found at {file_path}. Proceeding without it.")
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML config file {file_path}: {e!r}. Proceeding without it.")
        return {}
    except Exception as e:
        print(f"Error loading config file {file_path}: {e!r}. Proceeding without it.")
        return {}

def parse_http_url_details(url_str):
    """
    Parses a URL string into HTTP components: host, port, and secure flag.
    """
    parsed_url = urlparse(url_str)
    
    http_scheme = parsed_url.scheme.lower()
    if http_scheme not in ['http', 'https']:
        raise ValueError(f"Invalid URL scheme: {parsed_url.scheme}. Must be 'http' or 'https'.")
    
    http_secure = http_scheme == 'https'
    
    http_host = parsed_url.hostname
    if not http_host:
        raise ValueError(f"Could not determine host from URL: {url_str}")
        
    http_port = parsed_url.port
    if not http_port:
        http_port = 443 if http_secure else 80
        
    return http_host, http_port, http_secure

def connect_to_weaviate(url, api_key, cli_grpc_host=None, cli_grpc_port=None):
    """
    Establishes connection to Weaviate using connect_to_custom (client v4.x).
    Allows overriding gRPC host and port via CLI arguments.
    """
    global client
    if client and client.is_connected() and client.is_ready():
        print("Using existing healthy Weaviate connection.")
        return client

    print(f"Attempting to connect to Weaviate at {url} (client v4.x) using custom connection parameters...")
    auth_credentials = None
    if api_key: # Admin API key for performing these operations
        auth_credentials = AuthApiKey(api_key=api_key)
    
    http_host, http_port, http_secure = "", 0, False
    grpc_host_to_use, grpc_port_to_use, grpc_secure_to_use = "", 0, False

    try:
        if client: 
            print("Closing pre-existing client instance.")
            client.close() 
            client = None 

        http_host, http_port, http_secure = parse_http_url_details(url)

        grpc_host_to_use = cli_grpc_host if cli_grpc_host else http_host
        grpc_port_to_use = cli_grpc_port if cli_grpc_port is not None else 50051 
        
        if cli_grpc_port is not None:
            if cli_grpc_port == 443: grpc_secure_to_use = True
            elif cli_grpc_port == 80: grpc_secure_to_use = False
            else: grpc_secure_to_use = http_secure 
        else:
            grpc_secure_to_use = http_secure 

        print(f"  HTTP connection: host='{http_host}', port={http_port}, secure={http_secure}")
        print(f"  gRPC connection: host='{grpc_host_to_use}', port={grpc_port_to_use}, secure={grpc_secure_to_use}")

        additional_config = wc_config.AdditionalConfig(
            timeout=(20, 120), 
            startup_period=30 
        )

        new_client = weaviate.connect_to_custom( 
            http_host=http_host,
            http_port=http_port,
            http_secure=http_secure,
            grpc_host=grpc_host_to_use,
            grpc_port=grpc_port_to_use,
            grpc_secure=grpc_secure_to_use,
            auth_credentials=auth_credentials, # This should be the admin key
            additional_config=additional_config,
        )
        
        if not new_client.is_ready(): 
            print("Error: Weaviate client object created, but instance is not ready. Check Weaviate server logs and network.")
            try:
                live_status = new_client.is_live() 
                print(f"  Instance live status: {live_status}")
            except Exception as live_err:
                print(f"  Could not get live status: {live_err!r}")
            new_client.close()
            exit(1)
        
        client = new_client 
        print("Successfully connected to Weaviate.")
        return client
        
    except ValueError as ve: 
        print(f"Error parsing URL or parameters for custom connection: {ve!r}")
        if client: client.close()
        client = None
        exit(1)
    except WeaviateConnectionError as wce:
        print(f"WeaviateConnectionError: Could not connect to Weaviate. Please check network, firewall, and server status.")
        print(f"  Raw Exception Details: {wce!r}") 
        if hasattr(wce, 'original_exception') and wce.original_exception:
            print(f"  Original Underlying Exception: {wce.original_exception!r}")
        print(f"  Attempted HTTP: {http_host}:{http_port} (secure: {http_secure})")
        print(f"  Attempted gRPC: {grpc_host_to_use}:{grpc_port_to_use} (secure: {grpc_secure_to_use})")
        if client: client.close()
        client = None
        exit(1)
    except WeaviateStartUpError as wse:
        print(f"WeaviateStartUpError: Problem during Weaviate startup or client initialization.")
        print(f"  Raw Exception Details: {wse!r}")
        if hasattr(wse, 'original_exception') and wse.original_exception:
            print(f"  Original Underlying Exception: {wse.original_exception!r}")
        if client: client.close()
        client = None
        exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during Weaviate connection: {type(e).__name__} - {e!r}")
        if client: client.close()
        client = None 
        exit(1)

def close_connection():
    """Closes the Weaviate connection if open (client v4)."""
    global client
    if client:
        try:
            client.close()
            print("Weaviate client connection closed.")
        except Exception as e:
            print(f"Error closing Weaviate client connection: {e!r}")
        finally:
            client = None

def parse_properties_v4(props_str_list):
    """Parses property strings like 'name:dataType' into Weaviate v4 Property objects."""
    properties = []
    if not props_str_list:
        return None 
    for prop_str in props_str_list:
        try:
            name, data_type_str = prop_str.split(':', 1)
            data_type_str_upper = data_type_str.upper()
            
            if data_type_str_upper == "TEXT": data_type_enum = wvc.DataType.TEXT
            elif data_type_str_upper == "INT": data_type_enum = wvc.DataType.INT
            elif data_type_str_upper == "NUMBER": data_type_enum = wvc.DataType.NUMBER
            elif data_type_str_upper == "BOOL": data_type_enum = wvc.DataType.BOOL 
            elif data_type_str_upper == "DATE": data_type_enum = wvc.DataType.DATE
            elif data_type_str_upper == "UUID": data_type_enum = wvc.DataType.UUID
            elif data_type_str_upper == "TEXT_ARRAY": data_type_enum = wvc.DataType.TEXT_ARRAY
            elif data_type_str_upper == "INT_ARRAY": data_type_enum = wvc.DataType.INT_ARRAY
            elif data_type_str_upper == "NUMBER_ARRAY": data_type_enum = wvc.DataType.NUMBER_ARRAY
            elif data_type_str_upper == "BOOL_ARRAY": data_type_enum = wvc.DataType.BOOL_ARRAY
            elif data_type_str_upper == "DATE_ARRAY": data_type_enum = wvc.DataType.DATE_ARRAY
            elif data_type_str_upper == "UUID_ARRAY": data_type_enum = wvc.DataType.UUID_ARRAY
            elif data_type_str_upper == "GEO_COORDINATES": data_type_enum = wvc.DataType.GEO_COORDINATES
            elif data_type_str_upper == "PHONE_NUMBER": data_type_enum = wvc.DataType.PHONE_NUMBER
            elif data_type_str_upper == "BLOB": data_type_enum = wvc.DataType.BLOB
            else: 
                try: 
                    data_type_enum = getattr(wvc.DataType, data_type_str_upper)
                except AttributeError:
                    print(f"Warning: Unsupported or unknown dataType '{data_type_str}' for property '{name}'. Skipping this property.")
                    continue
            
            properties.append(wvc.Property(name=name, data_type=data_type_enum))
        except ValueError:
            print(f"Warning: Invalid property format '{prop_str}'. Expected 'name:dataType'. Skipping.")
            continue
    return properties if properties else None


def handle_collection_create(args):
    """Handles 'collection create' command using client v4.x."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    print(f"Attempting to create collection '{args.name}'...")

    if client.collections.exists(args.name):
        print(f"Collection '{args.name}' already exists. Skipping creation.")
        return

    properties = parse_properties_v4(args.property) 
    
    vectorizer_config = None
    if args.vectorizer:
        vectorizer_name = str(args.vectorizer).lower()
        v_options = args.vectorizer_options if args.vectorizer_options else {}

        if vectorizer_name == "text2vec-openai":
            vectorizer_config = wvc.Configure.Vectorizer.text2vec_openai(
                model=v_options.get("model"),
                type_=v_options.get("type"), 
                vectorize_collection_name=v_options.get("vectorizeClassName", True) 
            )
        elif vectorizer_name == "text2vec-cohere":
            vectorizer_config = wvc.Configure.Vectorizer.text2vec_cohere(
                 model=v_options.get("model"),
                 truncate=v_options.get("truncate"),
                 vectorize_collection_name=v_options.get("vectorizeClassName", True)
            )
        elif vectorizer_name == "text2vec-huggingface":
            vectorizer_config = wvc.Configure.Vectorizer.text2vec_huggingface(
                model=v_options.get("model"), 
                passage_model=v_options.get("passageModel"), 
                query_model=v_options.get("queryModel"),
                source_properties=args.vectorizer_source_properties,
                options=v_options.get("options"), 
                vectorize_collection_name=v_options.get("vectorizeClassName", True)
            )
        elif vectorizer_name == "none":
            vectorizer_config = wvc.Configure.Vectorizer.none()
        else:
            print(f"Warning: Unknown or unsupported vectorizer '{args.vectorizer}'. No vectorizer will be configured.")

    replication_config = None
    if args.replication_factor is not None:
        replication_config = wvc.Configure.replication(factor=args.replication_factor)

    sharding_config = None
    if args.shards is not None:
        sharding_config = wvc.Configure.sharding(desired_count=args.shards)
    
    inverted_index_config = None 

    try:
        client.collections.create(
            name=args.name,
            description=args.description,
            properties=properties, 
            vectorizer_config=vectorizer_config,
            replication_config=replication_config,
            sharding_config=sharding_config,
            inverted_index_config=inverted_index_config 
        )
        print(f"Collection '{args.name}' created successfully.")
    except (WeaviateQueryException, WeaviateConnectionError) as e: 
        print(f"Error creating collection '{args.name}': {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")


def handle_collection_delete(args):
    """Handles 'collection delete' command using client v4.x."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    confirm = input(f"Are you sure you want to delete collection '{args.name}'? This cannot be undone. (yes/no): ")
    if confirm.lower() != 'yes':
        print("Collection deletion cancelled.")
        return
    print(f"Attempting to delete collection '{args.name}'...")
    try:
        client.collections.delete(name=args.name) 
        print(f"Collection '{args.name}' deleted successfully.")
    except WeaviateQueryException as e:
        print(f"Error deleting collection '{args.name}': {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")

def handle_collection_list(args):
    """Handles 'collection list' command using client v4.x."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    print("Fetching list of collections...")
    try:
        collections_dict = client.collections.list_all(simple=not args.detailed) 
        
        if collections_dict:
            print("Collections:")
            for name, coll_data in collections_dict.items():
                if args.detailed: 
                    print(f"\n  Name: {name}")
                    try:
                        config = coll_data.config.get() 
                        print(f"    Description: {config.description}")
                        print(f"    Properties: {[(p.name, p.data_type, p.description) for p in config.properties] if config.properties else 'None'}")
                        print(f"    Vectorizer: {config.vectorizer}")
                        if config.replication_config:
                            print(f"    Replication Factor: {config.replication_config.factor}")
                        if config.sharding_config:
                            s_config = config.sharding_config
                            print(f"    Sharding: Desired={s_config.desired_count}, Actual={s_config.actual_count}, VirtualDesired={s_config.desired_virtual_count}, VirtualActual={s_config.actual_virtual_count}")
                    except Exception as detail_err:
                        print(f"    Could not fetch full details for {name}: {detail_err!r}")
                else: 
                    print(f"  - {name}")
        else:
            print("No collections found.")
    except (WeaviateQueryException, WeaviateConnectionError) as e:
        print(f"Error listing collections: {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")

def handle_collection_describe(args):
    """Handles 'collection describe' command using client v4.x."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    print(f"Fetching details for collection '{args.name}'...")
    try:
        if not client.collections.exists(args.name):
            print(f"Collection '{args.name}' does not exist.")
            return
        
        collection_instance = client.collections.get(args.name)
        collection_config = collection_instance.config.get() 
        
        config_dict = {}
        try:
            config_dict = collection_config.to_dict()
        except Exception: 
            config_dict = {
                "name": collection_config.name,
                "description": collection_config.description,
                "vectorizer": str(collection_config.vectorizer), 
                "vector_index_type": str(collection_config.vector_index_type),
                "properties": [
                    {
                        "name": prop.name,
                        "dataType": [str(dt) for dt in prop.data_type] if isinstance(prop.data_type, list) else str(prop.data_type),
                        "description": prop.description,
                        "indexFilterable": prop.index_filterable,
                        "indexSearchable": prop.index_searchable,
                        "tokenization": str(prop.tokenization) if hasattr(prop,'tokenization') and prop.tokenization else None,
                        "vectorizer_module": str(prop.vectorizer_config.vectorizer) if hasattr(prop, 'vectorizer_config') and prop.vectorizer_config else "default",
                        "vectorize_property_name": prop.vectorizer_config.vectorize_property_name if hasattr(prop, 'vectorizer_config') and prop.vectorizer_config else False,
                    } for prop in collection_config.properties
                ] if collection_config.properties else [],
                "replication_config": {"factor": collection_config.replication_config.factor} if collection_config.replication_config else None,
                "sharding_config": vars(collection_config.sharding_config) if collection_config.sharding_config else None, 
                "inverted_index_config": vars(collection_config.inverted_index_config) if collection_config.inverted_index_config else None
            }
        print(json.dumps(config_dict, indent=2))

    except (WeaviateQueryException, WeaviateConnectionError) as e:
        print(f"Error describing collection '{args.name}': {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred while describing collection '{args.name}': {type(e).__name__} - {e!r}")

# --- User (API Key User ID) Management ---
def handle_user_create(args):
    """Handles 'user create' for API key user_ids using client.users.db."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    
    user_id_to_create = args.user_id 
    roles_to_assign = args.role if args.role else []

    print(f"Attempting to create API key for user_id '{user_id_to_create}'...")

    try:
        existing_keys = client.users.db.list_all()
        user_id_exists = any(key.user_id == user_id_to_create for key in existing_keys)

        if user_id_exists and not args.recreate_api_key:
            print(f"User_id '{user_id_to_create}' already has an API key. Use --recreate-api-key to force.")
        else:
            if user_id_exists and args.recreate_api_key:
                print(f"  --recreate-api-key: Deleting existing API key for '{user_id_to_create}'...")
                try:
                    client.users.db.delete(user_id=user_id_to_create)
                    print(f"  Deleted existing API key for '{user_id_to_create}'.")
                except Exception as del_err:
                    print(f"  Warning: Failed to delete existing API key for '{user_id_to_create}': {del_err!r}")
            
            new_api_key_obj = client.users.db.create(user_id=user_id_to_create)
            key_str = new_api_key_obj.key if hasattr(new_api_key_obj, 'key') else str(new_api_key_obj)
            print(f"  SUCCESS: API key generated for user_id '{user_id_to_create}'.")
            print(f"  IMPORTANT: Store this API key securely: {key_str} (This key is shown only once).")

        if roles_to_assign:
            print(f"  Assigning roles {roles_to_assign} to user_id '{user_id_to_create}'...")
            client.users.db.assign_roles(user_id=user_id_to_create, role_names=roles_to_assign)
            print(f"  Successfully assigned roles to '{user_id_to_create}'.")
        else:
            print(f"  No roles specified to assign to user_id '{user_id_to_create}'.")

    except WeaviateQueryException as e: 
        print(f"Error processing user_id '{user_id_to_create}': {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred while processing user_id '{user_id_to_create}': {e!r}")


def handle_user_delete(args):
    """Handles 'user delete' for API key user_ids using client.users.db."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    user_id_to_delete = args.user_id 
    
    confirm = input(f"Are you sure you want to delete user_id '{user_id_to_delete}' and its API key(s)? This cannot be undone. (yes/no): ")
    if confirm.lower() != 'yes':
        print("User_id deletion cancelled.")
        return

    print(f"Attempting to delete user_id '{user_id_to_delete}' and its API key(s)...")
    try:
        client.users.db.delete(user_id=user_id_to_delete)
        print(f"User_id '{user_id_to_delete}' and associated API key(s) deleted successfully.")
    except WeaviateQueryException as e:
        if "not found" in str(e).lower() or (hasattr(e, 'message') and "not found" in e.message.lower()):
             print(f"User_id '{user_id_to_delete}' not found. Nothing to delete.")
        else:
            print(f"Error deleting user_id '{user_id_to_delete}': {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")

def handle_user_list(args):
    """Handles 'user list' for API key user_ids using client.users.db."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    print("Fetching list of user_ids with API keys and their assigned roles...")
    try:
        api_keys_list = client.users.db.list_all() 
        if api_keys_list: 
            print("User_IDs with API Keys:")
            for key_obj in api_keys_list:
                user_id = key_obj.user_id
                assigned_roles = []
                try:
                    roles_data = client.users.db.get_assigned_roles(user_id=user_id)
                    if roles_data:
                        # Check if roles_data is a list of strings or list of Role objects
                        if all(isinstance(r, str) for r in roles_data):
                            assigned_roles = roles_data 
                        elif all(hasattr(r, 'name') for r in roles_data): 
                            assigned_roles = [role.name for role in roles_data]
                        else: # Fallback if format is unexpected
                            assigned_roles = [str(r) for r in roles_data] # Try to convert to string
                            print(f"    Warning: Unexpected format for roles_data for user_id '{user_id}': {roles_data!r}. Displaying as strings.")
                except Exception as role_err:
                    print(f"    Could not fetch roles for user_id '{user_id}': {role_err!r}")
                print(f"  - User ID: {user_id}, Roles: {assigned_roles if assigned_roles else 'None'}")
        else:
            print("No user_ids with API keys found.") 
    except (WeaviateQueryException, WeaviateConnectionError) as e:
        print(f"Error listing user_ids: {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")

def handle_user_update_roles(args):
    """Handles 'user update-roles' for API key user_ids using client.users.db."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    user_id_to_update = args.user_id 
    new_roles = args.role if args.role else []

    print(f"Attempting to set roles for user_id '{user_id_to_update}' to: {new_roles}...")
    try:
        client.users.db.assign_roles(
            user_id=user_id_to_update,
            role_names=new_roles 
        )
        print(f"Roles for user_id '{user_id_to_update}' set successfully to: {new_roles if new_roles else 'None (all removed)'}.")
    except WeaviateQueryException as e:
        print(f"Error setting roles for user_id '{user_id_to_update}': {e!r}.")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")

# --- Role Management (Directly creating roles with permissions) ---
def handle_role_create(args):
    """Handles 'role create' using client.roles.create()."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    print(f"Attempting to create role '{args.role_name}'...")

    try:
        if client.roles.exists(args.role_name):
            print(f"Role '{args.role_name}' already exists. Skipping creation.")
            return

        permissions_list = []
        collection_patterns = args.collection_pattern 

        permissions_list.append(Permissions.collections(
            collection=collection_patterns,
            create_collection=args.allow_collection_create,
            read_config=args.allow_collection_read_config,
            update_config=args.allow_collection_update_config,
            delete_collection=args.allow_collection_delete
        ))

        permissions_list.append(Permissions.data(
            collection=collection_patterns,
            create=args.allow_data_create,
            read=args.allow_data_read,
            update=args.allow_data_update,
            delete=args.allow_data_delete
        ))
        
        print(f"  Constructed permissions for role '{args.role_name}':")
        for p_obj in permissions_list:
            print(f"    - {p_obj}") 

        client.roles.create(role_name=args.role_name, permissions=permissions_list)
        print(f"Role '{args.role_name}' created successfully.")

    except WeaviateQueryException as e:
        print(f"Error creating role '{args.role_name}': {e.message if hasattr(e, 'message') else e!r}")
    except Exception as e:
        print(f"An unexpected error occurred while creating role '{args.role_name}': {e!r}")


def handle_role_delete(args):
    """Handles 'role delete' using client.roles.delete()."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    confirm = input(f"Are you sure you want to delete role '{args.role_name}'? This cannot be undone. (yes/no): ")
    if confirm.lower() != 'yes':
        print("Role deletion cancelled.")
        return
    print(f"Attempting to delete role '{args.role_name}'...")
    try:
        client.roles.delete(args.role_name)
        print(f"Role '{args.role_name}' deleted successfully.")
    except WeaviateQueryException as e:
        if "not found" in str(e.message).lower(): 
            print(f"Role '{args.role_name}' not found. Nothing to delete.")
        else:
            print(f"Error deleting role '{args.role_name}': {e.message if hasattr(e, 'message') else e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")

def handle_role_get(args):
    """Handles 'role get' using client.roles.get()."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    print(f"Fetching details for role '{args.role_name}'...")
    try:
        role = client.roles.get(args.role_name)
        if role:
            print(f"Role Name: {role.name}")
            print("Permissions:")
            if role.permissions:
                for perm in role.permissions:
                    print(f"  - {perm}") 
            else:
                print("  - No permissions defined for this role.")
        else: 
            print(f"Role '{args.role_name}' not found.")
    except WeaviateQueryException as e:
        if "not found" in str(e.message).lower():
            print(f"Role '{args.role_name}' not found.")
        else:
            print(f"Error fetching role '{args.role_name}': {e.message if hasattr(e, 'message') else e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")

def handle_role_list(args):
    """Handles 'role list' using client.roles.list_all()."""
    connect_to_weaviate(args.url, args.root_key, args.grpc_host, args.grpc_port)
    print("Fetching all defined roles...")
    try:
        all_roles_data = client.roles.list_all() # Expected to return List[Role] or List[str]
        
        if all_roles_data:
            print("Defined Roles:")
            for role_item in all_roles_data:
                role_name_to_display = ""
                permissions_to_display = []

                if hasattr(role_item, 'name'): # It's a Role object
                    role_name_to_display = role_item.name
                    if hasattr(role_item, 'permissions'):
                        permissions_to_display = role_item.permissions
                elif isinstance(role_item, str): # It's a role name string
                    role_name_to_display = role_item
                    if args.detailed: # Fetch full role object for details if only name was returned
                        try:
                            detailed_role = client.roles.get(role_name_to_display)
                            if detailed_role and hasattr(detailed_role, 'permissions'):
                                permissions_to_display = detailed_role.permissions
                        except Exception as detail_err:
                            print(f"    Could not fetch details for role '{role_name_to_display}': {detail_err!r}")
                else:
                    print(f"  Unrecognized role item format: {role_item!r}")
                    continue
                
                print(f"\n  Role Name: {role_name_to_display}")
                if args.detailed:
                    if permissions_to_display:
                        print("    Permissions:")
                        for perm in permissions_to_display:
                            print(f"      - {perm}")
                    else:
                        print("    Permissions: None defined or could not be fetched.")
        else:
            print("No roles defined on the server.")
    except (WeaviateQueryException, WeaviateConnectionError) as e:
        print(f"Error listing roles: {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred: {e!r}")


def main():
    print_client_version()
    parser = argparse.ArgumentParser(description="Command-line tool for Weaviate management (Client v4.14+ Syntax).", prog="weaviate_cli_v4")
    
    parser.add_argument('--config-file', help="Path to a YAML configuration file for connection details.")
    parser.add_argument('--url', help="URL of the Weaviate instance for HTTP/REST API (e.g., https://my.weaviate.cluster).")
    parser.add_argument('--root-key', '--api-key', dest='root_key', help="API key for Weaviate authentication.")
    parser.add_argument('--grpc-host', help="Optional: Hostname for the gRPC connection. Defaults to the host from --url.")
    parser.add_argument('--grpc-port', type=int, help="Optional: Port for the gRPC connection. Defaults to 50051.")
    parser.add_argument("--recreate-api-key", action="store_true", help="If set for 'user create', existing API key for the user_id will be deleted and a new one generated.")

    
    subparsers = parser.add_subparsers(title='Commands', dest='command', help="Available commands")
    try: subparsers.required = True 
    except AttributeError: pass 

    # --- Collection Commands ---
    collection_parser = subparsers.add_parser('collection', help="Manage collections.")
    collection_subparsers = collection_parser.add_subparsers(title='Collection Actions', dest='action', help="Action to perform on collections")
    try: collection_subparsers.required = True
    except AttributeError: pass

    coll_create_parser = collection_subparsers.add_parser('create', help="Create a new collection.")
    coll_create_parser.add_argument('--name', required=True, help="Name of the collection.")
    coll_create_parser.add_argument('--description', default='', help="Description.")
    coll_create_parser.add_argument('--property', action='append', help="Property: 'name:dataType'. E.g., title:TEXT")
    coll_create_parser.add_argument('--vectorizer', help="Vectorizer (e.g., 'text2vec-openai', 'none').")
    coll_create_parser.add_argument('--vectorizer-options', type=json.loads, default=None, help='JSON string for vectorizer options (e.g., \'{"model":"ada-002", "type":"text"}\').')
    coll_create_parser.add_argument('--vectorizer-source-properties', action='append', help='Specify source properties for the vectorizer.')
    coll_create_parser.add_argument('--replication-factor', type=int, help="Replication factor.")
    coll_create_parser.add_argument('--shards', type=int, help="Number of shards.")
    coll_create_parser.set_defaults(func=handle_collection_create)

    coll_delete_parser = collection_subparsers.add_parser('delete', help="Delete a collection.")
    coll_delete_parser.add_argument('--name', required=True, help="Name of the collection to delete.")
    coll_delete_parser.set_defaults(func=handle_collection_delete)

    coll_list_parser = collection_subparsers.add_parser('list', help="List all collections.")
    coll_list_parser.add_argument('--detailed', action='store_true', help="Show detailed information (uses non-simple list_all).")
    coll_list_parser.set_defaults(func=handle_collection_list)

    coll_describe_parser = collection_subparsers.add_parser('describe', help="Describe a collection.")
    coll_describe_parser.add_argument('--name', required=True, help="Name of the collection.")
    coll_describe_parser.set_defaults(func=handle_collection_describe)

    # --- User (API Key User ID) Commands ---
    user_parser = subparsers.add_parser('user', help="Manage API key user_ids and their roles.")
    user_subparsers = user_parser.add_subparsers(title='User Actions', dest='action', help="Action to perform on API key user_ids")
    try: user_subparsers.required = True
    except AttributeError: pass

    user_create_parser = user_subparsers.add_parser('create', help="Create a new user_id and generate an API key for it.")
    user_create_parser.add_argument('--user-id', required=True, help="The user_id to create an API key for.")
    user_create_parser.add_argument('--role', action='append', help="Role name to assign to this user_id. Repeat for multiple roles.")
    user_create_parser.set_defaults(func=handle_user_create)

    user_delete_parser = user_subparsers.add_parser('delete', help="Delete a user_id and its associated API key(s).")
    user_delete_parser.add_argument('--user-id', required=True, help="User_id to delete.")
    user_delete_parser.set_defaults(func=handle_user_delete)

    user_list_parser = user_subparsers.add_parser('list', help="List all user_ids with API keys and their assigned roles.")
    user_list_parser.set_defaults(func=handle_user_list)
    
    user_update_roles_parser = user_subparsers.add_parser('update-roles', help="Set/replace roles for a user_id.")
    user_update_roles_parser.add_argument('--user-id', required=True, help="User_id to update.")
    user_update_roles_parser.add_argument('--role', action='append', help="New list of roles. Omitting all --role options will remove all roles for the user_id.")
    user_update_roles_parser.set_defaults(func=handle_user_update_roles)

    # --- Role Commands (Direct Role Management) ---
    role_parser = subparsers.add_parser('role', help="Manage roles and their permissions directly.")
    role_subparsers = role_parser.add_subparsers(title='Role Actions', dest='action', help="Action to perform on roles")
    try: role_subparsers.required = True
    except AttributeError: pass

    role_create_parser = role_subparsers.add_parser('create', help="Create a new role with specified permissions directly on the server.")
    role_create_parser.add_argument('--role-name', required=True, help="The name of the role.")
    role_create_parser.add_argument('--collection-pattern', action='append', required=True, help="Collection pattern(s) this rule applies to (e.g., 'MyCollection*', '*'). Can be specified multiple times.")
    role_create_parser.add_argument('--allow-data-create', action='store_true', help="Allow data 'create' operation.")
    role_create_parser.add_argument('--allow-data-read', action='store_true', help="Allow data 'read' operation.")
    role_create_parser.add_argument('--allow-data-update', action='store_true', help="Allow data 'update' operation.")
    role_create_parser.add_argument('--allow-data-delete', action='store_true', help="Allow data 'delete' operation.")
    role_create_parser.add_argument('--allow-collection-create', action='store_true', help="Allow creating new collections.")
    role_create_parser.add_argument('--allow-collection-read-config', action='store_true', help="Allow reading schema of specified collections.")
    role_create_parser.add_argument('--allow-collection-update-config', action='store_true', help="Allow updating schema of specified collections.")
    role_create_parser.add_argument('--allow-collection-delete', action='store_true', help="Allow deleting collections.")
    role_create_parser.set_defaults(func=handle_role_create)

    role_delete_parser = role_subparsers.add_parser('delete', help="Delete a role from the server.")
    role_delete_parser.add_argument('--role-name', required=True, help="Name of the role to delete.")
    role_delete_parser.set_defaults(func=handle_role_delete)

    role_get_parser = role_subparsers.add_parser('get', help="Get details of a specific role from the server.")
    role_get_parser.add_argument('--role-name', required=True, help="Name of the role.")
    role_get_parser.set_defaults(func=handle_role_get)

    role_list_parser = role_subparsers.add_parser('list', help="List all roles defined on the server.")
    role_list_parser.add_argument('--detailed', action='store_true', help="Show permissions for each role.")
    role_list_parser.set_defaults(func=handle_role_list)


    args = parser.parse_args()

    config_from_file = load_config_from_yaml(args.config_file) if args.config_file else {}
    final_url = args.url if args.url is not None else config_from_file.get('weaviate_url')
    final_api_key = args.root_key if args.root_key is not None else config_from_file.get('api_key', config_from_file.get('root_key'))
    final_grpc_host = args.grpc_host if args.grpc_host is not None else config_from_file.get('grpc_host')
    final_grpc_port = args.grpc_port if args.grpc_port is not None else config_from_file.get('grpc_port')

    args.url = final_url
    args.root_key = final_api_key
    args.grpc_host = final_grpc_host
    args.grpc_port = final_grpc_port

    if not args.command: parser.print_help(); exit(1)
    if hasattr(args, 'action') and not args.action: 
        active_parser = None
        for sp_action in parser._actions: # Find the subparser for the current command
            if isinstance(sp_action, argparse._SubParsersAction):
                if args.command in sp_action.choices:
                    active_parser = sp_action.choices[args.command]
                    break
        if active_parser: active_parser.print_help()
        else: parser.print_help()
        exit(1)

    if not args.root_key:
        args.root_key = os.environ.get("WEAVIATE_API_KEY", os.environ.get("WEAVIATE_ROOT_KEY"))
        if not args.root_key:
            print("Weaviate API key not provided via CLI, config file, or environment variables.")
            try: args.root_key = getpass.getpass("Enter Weaviate Admin API Key: ")
            except Exception as e: print(f"Error reading API key: {e!r}"); close_connection(); exit(1)
            if not args.root_key: print("Error: Admin API Key is required for this command."); close_connection(); exit(1)
    
    if hasattr(args, 'func'):
        try: args.func(args)
        finally: close_connection() 
    else:
        parser.print_help()
        close_connection()

if __name__ == "__main__":
    main()
