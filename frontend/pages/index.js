import { useState } from 'react'

export default function Home() {
  const [secrets, setSecrets] = useState(null)
  const [loading, setLoading] = useState(false)
  const [secretType, setSecretType] = useState('')

  const fetchSecrets = async (type) => {
    setLoading(true)
    setSecretType(type)
    try {
      let endpoint;
      switch(type) {
        case 'dynamic-db':
          endpoint = '/secrets/db';
          break;
        case 'dynamic-admin':
          endpoint = '/secrets/db-admin';
          break;
        case 'api':
          endpoint = '/secrets/api';
          break;
        case 'app':
          endpoint = '/secrets/app';
          break;
        case 'list':
          endpoint = '/secrets/dynamic';
          break;
        case 'debug':
          endpoint = '/debug/vault';
          break;
        default:
          endpoint = '/secrets/db';
      }
      
      const response = await fetch(`http://localhost:8000${endpoint}`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setSecrets(data)
    } catch (error) {
      console.error('Error fetching secrets:', error)
      setSecrets({ error: error.message })
    }
    setLoading(false)
  }

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString()
  }

  const getTimeRemaining = (expiresAt) => {
    const now = new Date()
    const expires = new Date(expiresAt)
    const diffMs = expires - now
    if (diffMs <= 0) return "Expired"
    const diffMins = Math.floor(diffMs / 60000)
    const diffSecs = Math.floor((diffMs % 60000) / 1000)
    return `${diffMins}m ${diffSecs}s`
  }

  const buttonStyle = {
    padding: '10px 15px',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    color: 'white',
    fontWeight: '500'
  }

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif", maxWidth: "1000px", margin: "0 auto" }}>
      <h1 style={{ marginBottom: "5px" }}>Secrets Management</h1>
      <p style={{ color: "#555", marginBottom: "20px" }}>
        Manage dynamic and static secrets with automatic rotation and secure storage.
      </p>
      
      <div style={{ marginBottom: '30px', padding: '20px', background: '#f9f9f9', borderRadius: '6px' }}>
        <h3 style={{ marginTop: 0 }}>Dynamic Secrets</h3>
        <p style={{ fontSize: '14px', color: '#666' }}>Auto-rotating every hour</p>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '20px' }}>
          <button 
            onClick={() => fetchSecrets('dynamic-db')} 
            disabled={loading}
            style={{ ...buttonStyle, background: '#4CAF50' }}
          >
            {loading && secretType === 'dynamic-db' ? 'Generating...' : 'Get DB Credentials'}
          </button>
          <button 
            onClick={() => fetchSecrets('dynamic-admin')} 
            disabled={loading}
            style={{ ...buttonStyle, background: '#2196F3' }}
          >
            {loading && secretType === 'dynamic-admin' ? 'Generating...' : 'Get Admin Credentials'}
          </button>
        </div>
        
        <h3>Static Secrets</h3>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '20px' }}>
          <button 
            onClick={() => fetchSecrets('api')} 
            disabled={loading}
            style={{ ...buttonStyle, background: '#FF9800' }}
          >
            Get API Secrets
          </button>
          <button 
            onClick={() => fetchSecrets('app')} 
            disabled={loading}
            style={{ ...buttonStyle, background: '#9C27B0' }}
          >
            Get App Config
          </button>
        </div>

        <h3>Debug & Information</h3>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button 
            onClick={() => fetchSecrets('list')} 
            disabled={loading}
            style={{ ...buttonStyle, background: '#607D8B' }}
          >
            List All Secrets
          </button>
          <button 
            onClick={() => fetchSecrets('debug')} 
            disabled={loading}
            style={{ ...buttonStyle, background: '#f44336' }}
          >
            Debug Vault
          </button>
        </div>
      </div>

      {secrets && (
        <div style={{ marginTop: '20px', padding: '20px', background: '#fafafa', borderRadius: '6px', border: '1px solid #ddd' }}>
          <h3 style={{ marginTop: 0 }}>
            {secrets.secret_type ? secrets.secret_type.replace(/_/g, ' ').toUpperCase() : 
             secrets.available_dynamic_secrets ? 'Available Secrets' : 'Debug Info'}
            {secrets.rotation && ` (${secrets.rotation.replace('_', ' ')})`}
          </h3>
          
          {secrets.error ? (
            <div style={{ color: 'red', padding: '10px', background: '#ffebee', borderRadius: '4px' }}>
              Error: {secrets.error}
            </div>
          ) : secrets.available_dynamic_secrets ? (
            <div>
              <h4>Dynamic Secrets</h4>
              <ul>
                {secrets.available_dynamic_secrets.map((secret, index) => (
                  <li key={index}>
                    <strong>{secret.name}</strong>: {secret.endpoint} - TTL: {secret.ttl}
                  </li>
                ))}
              </ul>
              <h4>Static Secrets</h4>
              <ul>
                {secrets.available_static_secrets.map((secret, index) => (
                  <li key={index}>
                    <strong>{secret.name}</strong>: {secret.endpoint}
                  </li>
                ))}
              </ul>
            </div>
          ) : secrets.secrets_engines ? (
            <div>
              <h4>Vault Debug Information</h4>
              <pre style={{ 
                background: 'white', 
                padding: '10px', 
                borderRadius: '4px', 
                overflowX: 'auto',
                fontSize: '12px',
                border: '1px solid #eee'
              }}>
                {JSON.stringify(secrets, null, 2)}
              </pre>
            </div>
          ) : (
            <>
              <div><strong>Data</strong></div>
              <pre style={{ 
                background: 'white', 
                padding: '10px', 
                borderRadius: '4px', 
                overflowX: 'auto',
                fontSize: '12px',
                border: '1px solid #eee'
              }}>
                {JSON.stringify(secrets.data, null, 2)}
              </pre>
              
              {secrets.metadata && (
                <>
                  <div style={{ marginTop: '15px' }}><strong>Metadata</strong></div>
                  <div style={{ background: 'white', padding: '10px', borderRadius: '4px', border: '1px solid #eee' }}>
                    <div>Generated: {formatTimestamp(secrets.metadata.generated_at)}</div>
                    {secrets.metadata.expires_at && (
                      <div>Expires: {formatTimestamp(secrets.metadata.expires_at)} 
                        ({getTimeRemaining(secrets.metadata.expires_at)} remaining)
                      </div>
                    )}
                    {secrets.metadata.connection_test && (
                      <div>Connection Test: 
                        <span style={{ color: secrets.metadata.connection_test === 'successful' ? 'green' : 'red', fontWeight: 'bold' }}>
                          {secrets.metadata.connection_test.toUpperCase()}
                        </span>
                      </div>
                    )}
                    {secrets.metadata.cache_status && (
                      <div>Cache: {secrets.metadata.cache_status}</div>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}

      <div style={{ marginTop: '30px', padding: '20px', background: '#f5fdf5', borderRadius: '6px', fontSize: '14px', border: '1px solid #d9ead3' }}>
        <h4 style={{ marginTop: 0 }}>How it works</h4>
        <ul>
          <li><strong>Dynamic Secrets</strong>: Vault generates unique PostgreSQL users that auto-expire after 1 hour</li>
          <li><strong>Automatic Rotation</strong>: Credentials are automatically rotated without service interruption</li>
          <li><strong>Security</strong>: Short-lived credentials reduce risk of exposure</li>
          <li><strong>Verification</strong>: Each credential is tested against the actual database</li>
          <li><strong>Debugging</strong>: Use the Debug option to inspect Vault configuration if issues occur</li>
        </ul>
      </div>
    </div>
  )
}
