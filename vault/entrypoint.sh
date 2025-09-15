#!/bin/sh

# Vault Automated Entrypoint Script with Dynamic Database Secrets
echo "🚀 Starting Vault with automated initialization..."

# Start Vault server in development mode in background
echo "🔧 Starting Vault server..."
vault server -dev -dev-root-token-id=root -dev-listen-address="0.0.0.0:8200" &

# Wait for Vault to start
echo "⏳ Waiting for Vault to start..."
sleep 5

# Set environment variables
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=root

# Wait for Vault to be ready
MAX_RETRIES=20
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if vault status > /dev/null 2>&1; then
        echo "✅ Vault is ready and authenticated!"
        break
    fi
    
    echo "⏳ Vault not ready yet, retrying... ($((RETRY_COUNT+1))/$MAX_RETRIES)"
    RETRY_COUNT=$((RETRY_COUNT+1))
    sleep 3
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ Vault failed to start within time limit"
    exit 1
fi

# Enable KV v2 secrets engine if not already enabled
echo "🔧 Setting up KV v2 secrets engine..."
if ! vault secrets list | grep -q "secret/"; then
    vault secrets enable -path=secret kv-v2
    echo "✅ KV v2 enabled at path 'secret'"
else
    echo "ℹ️ KV v2 already enabled at path 'secret'"
fi

# Store static demo secrets
echo "💾 Storing static demo secrets..."
vault kv put secret/db \
  username="dev_user" \
  password="dev_pass" \
  host="postgres" \
  port="5432" \
  database="devdb"

vault kv put secret/api \
  stripe_api="sk_test_12345" \
  github_token="ghp_demo_token_123" \
  aws_access_key="AKIADEMOACCESSKEY"

vault kv put secret/app \
  environment="development" \
  debug_mode="true" \
  log_level="info"

# Enable Database Secrets Engine for Dynamic PostgreSQL Credentials
echo "🔧 Setting up Dynamic PostgreSQL Secrets..."

# Enable database secrets engine if not already enabled
if ! vault secrets list | grep -q "database/"; then
    echo "📊 Enabling database secrets engine..."
    vault secrets enable -path=database database
    echo "✅ Database secrets engine enabled"
else
    echo "ℹ️ Database secrets engine already enabled"
fi

# Wait a moment for the secrets engine to be fully ready
sleep 2

# Configure PostgreSQL connection
echo "📊 Configuring PostgreSQL connection..."
vault write database/config/postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles="readonly,admin" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/devdb?sslmode=disable" \
  username="devuser" \
  password="devpass"

# Create readonly role (1-hour credentials)
echo "👤 Creating readonly role..."
vault write database/roles/readonly \
  db_name=postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"

# Create admin role (1-hour credentials)  
echo "👑 Creating admin role..."
vault write database/roles/admin \
  db_name=postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"

# Wait for database to be ready before testing
echo "⏳ Waiting for database to be ready..."
sleep 10

# Test the dynamic secrets
echo "🧪 Testing dynamic secrets generation..."
echo "Testing readonly role:"
vault read database/creds/readonly || echo "⚠️ Readonly role test failed"

echo "Testing admin role:"
vault read database/creds/admin || echo "⚠️ Admin role test failed"

echo "🔍 Verifying setup..."
echo "Static secrets:"
vault kv get secret/db

echo -e "\nDynamic database roles:"
vault list database/roles

echo -e "\n✅ Vault initialization complete!"
echo "📊 Available secrets:"
echo "   - Static:"
echo "     - Database: /secrets/db (static)"
echo "     - API Keys: /secrets/api"
echo "     - App Config: /secrets/app"
echo "   - Dynamic (Auto-rotating):"
echo "     - Database ReadOnly: /secrets/db (dynamic)"
echo "     - Database Admin: /secrets/db-admin"
echo "     - List all: /secrets/dynamic"
echo "   - Debug: /debug/vault"

# Keep the container running
echo "🎯 Vault is ready! Server running in foreground..."
wait