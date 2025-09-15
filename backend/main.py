from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import hvac
import os
import time
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List

app = FastAPI(title="Secrets Management API", version="2.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vault client setup
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://vault:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "root")

# Initialize Vault client with retry logic
def get_vault_client():
    client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
    max_retries = 20
    for i in range(max_retries):
        try:
            if client.is_authenticated():
                print("✅ Vault client authenticated successfully")
                # Test if we can access secrets
                try:
                    client.secrets.kv.v2.read_secret_version(path="db", mount_point="secret")
                    print("✅ Vault KV secrets access verified")
                except Exception as e:
                    print(f"⚠️ KV access test failed: {e}")
                return client
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ Vault connection attempt {i+1} failed: {e}")
            time.sleep(2)
    raise Exception("Vault not available after multiple retries")

client = get_vault_client()

# Cache for dynamic credentials with expiration
dynamic_credentials_cache = {}
CACHE_TTL = 3000  # 50 minutes (less than 1 hour)

def get_dynamic_db_credentials(role="readonly"):
    """Get dynamic database credentials from Vault with caching"""
    cache_key = f"db_{role}"
    current_time = datetime.now()
    
    # Return cached credentials if still valid
    if cache_key in dynamic_credentials_cache:
        cached_data = dynamic_credentials_cache[cache_key]
        if current_time < cached_data['expires_at']:
            print(f"♻️ Using cached {role} credentials (expires: {cached_data['expires_at']})")
            return cached_data['credentials']
    
    # Fetch new credentials from Vault
    try:
        print(f"🔄 Generating new {role} credentials from Vault...")
        
        # Use the correct path for database secrets
        secret_path = f"database/creds/{role}"
        print(f"📋 Requesting credentials from path: {secret_path}")
        
        # Read the secret using the correct path format
        secret = client.read(secret_path)
        
        if not secret:
            raise Exception(f"No response from Vault for path {secret_path}")
        
        if 'data' not in secret:
            raise Exception(f"No data in response from Vault: {secret}")
        
        credentials = secret['data']
        
        # Add lease information
        lease_duration = secret.get('lease_duration', 3600)  # Default 1 hour
        credentials['lease_duration'] = lease_duration
        credentials['renewable'] = secret.get('renewable', False)
        
        expires_at = current_time + timedelta(seconds=lease_duration)
        
        # Cache the credentials
        dynamic_credentials_cache[cache_key] = {
            'credentials': credentials,
            'expires_at': expires_at
        }
        
        print(f"✅ Generated new {role} credentials, expires at {expires_at}")
        print(f"   Username: {credentials['username']}")
        return credentials
        
    except Exception as e:
        print(f"❌ Failed to generate dynamic credentials: {str(e)}")
        raise Exception(f"Failed to generate dynamic credentials: {str(e)}")

def test_db_connection(credentials):
    """Test if the database connection works with given credentials"""
    try:
        conn = psycopg2.connect(
            host="postgres",
            database="devdb",
            user=credentials['username'],
            password=credentials['password'],
            port="5432",
            connect_timeout=5
        )
        # Test with a simple query
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            result = cur.fetchone()
            print(f"✅ Database connection successful: {result[0] if result else 'No result'}")
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Database connection test failed: {e}")
        return False

# Pydantic models for request validation
class SecretValue(BaseModel):
    value: str

class SecretsDict(BaseModel):
    secrets: dict

def get_all_static_secrets_from_vault():
    """Dynamically fetch all static secrets from Vault"""
    try:
        # List all secrets in the secret/ path
        secrets_list = client.secrets.kv.v2.list_secrets(
            path="",
            mount_point="secret"
        )
        
        secret_paths = secrets_list.get('data', {}).get('keys', [])
        static_secrets = {}
        
        for secret_path in secret_paths:
            # Remove trailing slash if present
            if secret_path.endswith('/'):
                secret_path = secret_path[:-1]
            
            try:
                # Read each secret
                secret = client.secrets.kv.v2.read_secret_version(
                    path=secret_path,
                    mount_point="secret"
                )
                
                data = secret["data"]["data"]
                metadata = secret["data"]["metadata"]
                
                static_secrets[secret_path] = {
                    "secret_type": f"static_{secret_path}_secrets",
                    "rotation": "manual",
                    "data": data,
                    "metadata": {
                        "version": metadata["version"],
                        "created_time": metadata["created_time"]
                    }
                }
                
            except Exception as e:
                print(f"⚠️ Error reading secret {secret_path}: {e}")
                # Continue with other secrets even if one fails
                continue
        
        return static_secrets
        
    except Exception as e:
        print(f"❌ Error listing secrets from Vault: {e}")
        # Fallback to hardcoded secrets if listing fails
        return get_fallback_static_secrets()

def get_fallback_static_secrets():
    """Fallback method to get static secrets if listing fails"""
    fallback_secrets = {}
    
    # Try to get known secret types
    known_secrets = ["api", "app", "db"]
    
    for secret_type in known_secrets:
        try:
            secret = client.secrets.kv.v2.read_secret_version(
                path=secret_type,
                mount_point="secret"
            )
            data = secret["data"]["data"]
            metadata = secret["data"]["metadata"]
            
            fallback_secrets[secret_type] = {
                "secret_type": f"static_{secret_type}_secrets",
                "rotation": "manual",
                "data": data,
                "metadata": {
                    "version": metadata["version"],
                    "created_time": metadata["created_time"]
                }
            }
        except Exception as e:
            print(f"⚠️ Error reading fallback secret {secret_type}: {e}")
            continue
    
    return fallback_secrets

@app.get("/")
def read_root():
    return {
        "message": "Secrets Management API with Dynamic Rotation", 
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "all_secrets": "/secrets/all",
            "static_secrets": "/secrets/static",
            "dynamic_secrets": "/secrets/dynamic-all",
            "debug": "/debug/vault"
        }
    }

@app.get("/health")
def health_check():
    try:
        vault_status = client.is_authenticated()
        db_test = False
        
        # Test database connection with static credentials
        try:
            conn = psycopg2.connect(
                host="postgres",
                database="devdb",
                user="devuser",
                password="devpass",
                port="5432",
                connect_timeout=3
            )
            conn.close()
            db_test = True
        except Exception as e:
            print(f"❌ Static DB connection test failed: {e}")
            db_test = False
            
        return {
            "status": "healthy", 
            "vault_connected": vault_status,
            "database_connected": db_test,
            "timestamp": datetime.now().isoformat(),
            "services": {
                "vault": "connected" if vault_status else "disconnected",
                "database": "connected" if db_test else "disconnected",
                "backend": "running"
            }
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/secrets/all")
def get_all_secrets():
    """Get all secrets (both static and dynamic) in a single response"""
    try:
        # Get static secrets dynamically
        static_secrets = get_all_static_secrets_from_vault()
        
        # Get dynamic secrets
        db_secrets = get_db_creds()
        db_admin_secrets = get_db_admin_creds()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "static_secrets": static_secrets,
            "dynamic_secrets": {
                "db_readonly": db_secrets,
                "db_admin": db_admin_secrets
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching all secrets: {str(e)}")

@app.get("/secrets/static")
def get_all_static_secrets():
    """Get all static secrets"""
    try:
        static_secrets = get_all_static_secrets_from_vault()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "secrets": static_secrets
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching static secrets: {str(e)}")

@app.get("/secrets/dynamic-all")
def get_all_dynamic_secrets():
    """Get all dynamic secrets"""
    try:
        db_secrets = get_db_creds()
        db_admin_secrets = get_db_admin_creds()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "secrets": {
                "db_readonly": db_secrets,
                "db_admin": db_admin_secrets
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dynamic secrets: {str(e)}")

def get_db_creds():
    """Helper function to get DB credentials"""
    try:
        # Get dynamic credentials
        credentials = get_dynamic_db_credentials("readonly")
        
        # Test the connection
        connection_works = test_db_connection(credentials)
        
        return {
            "secret_type": "dynamic_database_credentials",
            "rotation": "automatic_1h",
            "data": {
                "username": credentials['username'],
                "password": credentials['password'], 
                "host": "postgres",
                "port": "5432",
                "database": "devdb",
                "lease_duration": credentials.get('lease_duration', 3600),
                "renewable": credentials.get('renewable', False)
            },
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=credentials.get('lease_duration', 3600))).isoformat(),
                "connection_test": "successful" if connection_works else "failed",
                "cache_status": "new_credentials"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching DB secrets: {str(e)}")

def get_db_admin_creds():
    """Helper function to get DB admin credentials"""
    try:
        # Get admin dynamic credentials
        credentials = get_dynamic_db_credentials("admin")
        connection_works = test_db_connection(credentials)
        
        return {
            "secret_type": "dynamic_database_admin_credentials", 
            "rotation": "automatic_1h",
            "data": {
                "username": credentials['username'],
                "password": credentials['password'],
                "lease_duration": credentials.get('lease_duration', 3600),
                "renewable": credentials.get('renewable', False)
            },
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=credentials.get('lease_duration', 3600))).isoformat(),
                "connection_test": "successful" if connection_works else "failed",
                "cache_status": "new_credentials"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching admin DB secrets: {str(e)}")

@app.delete("/secrets/static/{secret_type}/{key}")
def delete_static_secret(secret_type: str, key: str):
    """Delete a specific key from a static secret"""
    try:
        # Read current secret
        secret = client.secrets.kv.v2.read_secret_version(
            path=secret_type,
            mount_point="secret"
        )
        data = secret["data"]["data"].copy()
        
        # Remove the specified key
        if key in data:
            del data[key]
            
            # Write updated secret back to Vault
            client.secrets.kv.v2.create_or_update_secret(
                path=secret_type,
                secret=data,
                mount_point="secret"
            )
            
            return {
                "status": "success",
                "message": f"Key '{key}' deleted from {secret_type}",
                "remaining_keys": list(data.keys())
            }
        else:
            raise HTTPException(status_code=404, detail=f"Key '{key}' not found in {secret_type}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting secret: {str(e)}")

@app.delete("/secrets/static/{secret_type}")
def delete_entire_secret(secret_type: str):
    """Delete an entire secret with all its keys"""
    try:
        # Check if secret exists
        try:
            client.secrets.kv.v2.read_secret_version(
                path=secret_type,
                mount_point="secret"
            )
        except:
            raise HTTPException(status_code=404, detail=f"Secret type '{secret_type}' not found")
        
        # Delete the entire secret
        client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=secret_type,
            mount_point="secret"
        )
        
        return {
            "status": "success",
            "message": f"Entire secret '{secret_type}' deleted successfully"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting entire secret: {str(e)}")

@app.put("/secrets/static/{secret_type}/{key}")
def update_static_secret(secret_type: str, key: str, secret_value: SecretValue):
    """Update a specific key in a static secret"""
    try:
        # Read current secret (if it exists)
        try:
            secret = client.secrets.kv.v2.read_secret_version(
                path=secret_type,
                mount_point="secret"
            )
            data = secret["data"]["data"].copy()
        except:
            # Secret doesn't exist yet, create empty data
            data = {}
        
        # Update the specified key
        data[key] = secret_value.value
        
        # Write updated secret back to Vault
        client.secrets.kv.v2.create_or_update_secret(
            path=secret_type,
            secret=data,
            mount_point="secret"
        )
        
        return {
            "status": "success",
            "message": f"Key '{key}' updated in {secret_type}",
            "data": {key: secret_value.value}
        }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating secret: {str(e)}")

@app.post("/secrets/static/{secret_type}/{key}")
def create_static_secret(secret_type: str, key: str, secret_value: SecretValue):
    """Create a new key in a static secret"""
    try:
        # Read current secret (if it exists)
        try:
            secret = client.secrets.kv.v2.read_secret_version(
                path=secret_type,
                mount_point="secret"
            )
            data = secret["data"]["data"].copy()
        except:
            # Secret doesn't exist yet, create empty data
            data = {}
        
        # Check if key already exists
        if key in data:
            raise HTTPException(status_code=400, detail=f"Key '{key}' already exists in {secret_type}")
        
        # Add the new key
        data[key] = secret_value.value
        
        # Write updated secret back to Vault
        client.secrets.kv.v2.create_or_update_secret(
            path=secret_type,
            secret=data,
            mount_point="secret"
        )
        
        return {
            "status": "success",
            "message": f"Key '{key}' created in {secret_type}",
            "data": {key: secret_value.value}
        }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating secret: {str(e)}")

@app.post("/secrets/static/{secret_type}")
def create_new_secret_type(secret_type: str, secrets_data: SecretsDict):
    """Create a completely new secret type with multiple key-value pairs"""
    try:
        # Check if secret type already exists
        try:
            client.secrets.kv.v2.read_secret_version(
                path=secret_type,
                mount_point="secret"
            )
            raise HTTPException(status_code=400, detail=f"Secret type '{secret_type}' already exists")
        except:
            # Secret doesn't exist, good to create
            pass
        
        # Create the new secret
        client.secrets.kv.v2.create_or_update_secret(
            path=secret_type,
            secret=secrets_data.secrets,
            mount_point="secret"
        )
        
        # Read back the created secret to verify
        created_secret = client.secrets.kv.v2.read_secret_version(
            path=secret_type,
            mount_point="secret"
        )
        
        return {
            "status": "success",
            "message": f"New secret type '{secret_type}' created",
            "data": created_secret["data"]["data"],
            "metadata": {
                "version": created_secret["data"]["metadata"]["version"],
                "created_time": created_secret["data"]["metadata"]["created_time"]
            }
        }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating secret type: {str(e)}")

@app.get("/debug/vault")
def debug_vault():
    """Debug endpoint to check Vault configuration"""
    try:
        # Check mounted secrets engines
        secrets_engines = client.sys.list_mounted_secrets_engines()
        
        # Check if database secrets engine is mounted
        database_mounted = "database/" in str(secrets_engines)
        
        # Check database roles if mounted
        database_roles = []
        if database_mounted:
            try:
                roles = client.list('database/roles')
                database_roles = roles.get('data', {}).get('keys', [])
            except Exception as e:
                database_roles = [f"Error listing roles: {str(e)}"]
        
        # Get static secrets info
        static_secrets = get_all_static_secrets_from_vault()
        
        return {
            "vault_connected": client.is_authenticated(),
            "secrets_engines": list(secrets_engines.keys()) if isinstance(secrets_engines, dict) else str(secrets_engines),
            "database_mounted": database_mounted,
            "database_roles": database_roles,
            "static_secrets_count": len(static_secrets),
            "static_secrets_types": list(static_secrets.keys()),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}