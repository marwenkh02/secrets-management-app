from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import hvac
import os
import time
import psycopg2
from datetime import datetime, timedelta

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
        # Debug: Check what secrets engines are available
        try:
            secrets_list = client.sys.list_mounted_secrets_engines()
            print("📊 Available secrets engines:", secrets_list.keys() if isinstance(secrets_list, dict) else secrets_list)
        except Exception as list_error:
            print(f"⚠️ Could not list secrets engines: {list_error}")
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

@app.get("/")
def read_root():
    return {
        "message": "Secrets Management API with Dynamic Rotation", 
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "db_secrets": "/secrets/db (dynamic)",
            "db_admin_secrets": "/secrets/db-admin (dynamic)", 
            "api_secrets": "/secrets/api (static)",
            "app_config": "/secrets/app (static)",
            "all_secrets": "/secrets/dynamic",
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

@app.get("/secrets/db")
def get_db_creds():
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

@app.get("/secrets/db-admin")
def get_db_admin_creds():
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

@app.get("/secrets/api")
def get_api_key():
    try:
        secret = client.secrets.kv.v2.read_secret_version(
            path="api",
            mount_point="secret"
        )
        data = secret["data"]["data"]
        return {
            "secret_type": "static_api_keys",
            "rotation": "manual",
            "data": {
                "stripe_api": data["stripe_api"],
                "github_token": data.get("github_token", ""),
                "aws_access_key": data.get("aws_access_key", "")
            },
            "metadata": {
                "version": secret["data"]["metadata"]["version"],
                "created_time": secret["data"]["metadata"]["created_time"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching API secrets: {str(e)}")

@app.get("/secrets/app")
def get_app_config():
    try:
        secret = client.secrets.kv.v2.read_secret_version(
            path="app",
            mount_point="secret"
        )
        data = secret["data"]["data"]
        return {
            "secret_type": "static_application_config",
            "rotation": "manual", 
            "data": {
                "environment": data.get("environment", "development"),
                "debug_mode": data.get("debug_mode", "false"),
                "log_level": data.get("log_level", "info")
            },
            "metadata": {
                "version": secret["data"]["metadata"]["version"],
                "created_time": secret["data"]["metadata"]["created_time"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching app config: {str(e)}")

@app.get("/secrets/dynamic")
def list_dynamic_secrets():
    return {
        "available_dynamic_secrets": [
            {"name": "Database ReadOnly", "endpoint": "/secrets/db", "ttl": "1h", "rotation": "automatic"},
            {"name": "Database Admin", "endpoint": "/secrets/db-admin", "ttl": "1h", "rotation": "automatic"}
        ],
        "available_static_secrets": [
            {"name": "API Keys", "endpoint": "/secrets/api", "rotation": "manual"},
            {"name": "Application Config", "endpoint": "/secrets/app", "rotation": "manual"}
        ],
        "timestamp": datetime.now().isoformat()
    }

@app.get("/secrets/status")
def secrets_status():
    """Check status of all secret types"""
    status = {
        "timestamp": datetime.now().isoformat(),
        "dynamic_credentials": {},
        "static_secrets": {}
    }
    
    # Check dynamic credentials
    for role in ["readonly", "admin"]:
        cache_key = f"db_{role}"
        if cache_key in dynamic_credentials_cache:
            cached = dynamic_credentials_cache[cache_key]
            status["dynamic_credentials"][role] = {
                "cached": True,
                "expires_at": cached['expires_at'].isoformat(),
                "seconds_remaining": int((cached['expires_at'] - datetime.now()).total_seconds())
            }
        else:
            status["dynamic_credentials"][role] = {"cached": False}
    
    return status

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
        
        # Test dynamic secrets generation
        dynamic_test = {}
        if database_mounted and 'readonly' in database_roles:
            try:
                secret = client.read('database/creds/readonly')
                dynamic_test['readonly'] = {
                    'success': True,
                    'username': secret['data']['username'] if secret and 'data' in secret else 'No username'
                }
            except Exception as e:
                dynamic_test['readonly'] = {'success': False, 'error': str(e)}
        
        return {
            "vault_connected": client.is_authenticated(),
            "secrets_engines": list(secrets_engines.keys()) if isinstance(secrets_engines, dict) else str(secrets_engines),
            "database_mounted": database_mounted,
            "database_roles": database_roles,
            "dynamic_test": dynamic_test,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}