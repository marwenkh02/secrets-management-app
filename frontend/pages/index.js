import { useState, useEffect } from 'react'

export default function Home() {
  const [secrets, setSecrets] = useState(null)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('all')
  const [editing, setEditing] = useState(null)
  const [newSecret, setNewSecret] = useState({ type: '', key: '', value: '' })
  const [showCreateForm, setShowCreateForm] = useState(false)

  const fetchSecrets = async (type) => {
    setLoading(true)
    setActiveTab(type)
    try {
      let endpoint;
      switch(type) {
        case 'all':
          endpoint = '/secrets/all';
          break;
        case 'static':
          endpoint = '/secrets/static';
          break;
        case 'dynamic':
          endpoint = '/secrets/dynamic-all';
          break;
        case 'debug':
          endpoint = '/debug/vault';
          break;
        default:
          endpoint = '/secrets/all';
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

  const refreshSecrets = () => {
    fetchSecrets(activeTab)
  }

  const deleteSecret = async (secretType, key) => {
    if (!window.confirm(`Are you sure you want to delete "${key}" from ${secretType}?`)) {
      return
    }

    try {
      const response = await fetch(`http://localhost:8000/secrets/static/${secretType}/${key}`, {
        method: 'DELETE'
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }
      
      const result = await response.json()
      alert(result.message)
      refreshSecrets()
    } catch (error) {
      console.error('Error deleting secret:', error)
      alert(`Error deleting secret: ${error.message}`)
    }
  }

  const deleteEntireSecret = async (secretType) => {
    if (!window.confirm(`Are you sure you want to delete the entire secret "${secretType}"? This cannot be undone.`)) {
      return
    }

    try {
      const response = await fetch(`http://localhost:8000/secrets/static/${secretType}`, {
        method: 'DELETE'
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }
      
      const result = await response.json()
      alert(result.message)
      refreshSecrets()
    } catch (error) {
      console.error('Error deleting entire secret:', error)
      alert(`Error deleting entire secret: ${error.message}`)
    }
  }

  const updateSecret = async (secretType, key, newValue) => {
    try {
      const response = await fetch(`http://localhost:8000/secrets/static/${secretType}/${key}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: newValue })
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }
      
      const result = await response.json()
      alert(result.message)
      setEditing(null)
      refreshSecrets()
    } catch (error) {
      console.error('Error updating secret:', error)
      alert(`Error updating secret: ${error.message}`)
    }
  }

  const createSecret = async (e) => {
    e.preventDefault()
    
    try {
      let response
      if (newSecret.key && newSecret.value) {
        // Create single key in existing secret type
        response = await fetch(`http://localhost:8000/secrets/static/${newSecret.type}/${newSecret.key}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ value: newSecret.value })
        })
      } else {
        // Create new secret type with multiple key-value pairs
        const secretsObj = {}
        if (newSecret.value) {
          newSecret.value.split(',').forEach(pair => {
            const [key, value] = pair.split('=').map(s => s.trim())
            if (key && value) secretsObj[key] = value
          })
        }
        
        // If no key-value pairs were parsed, create a default empty secret
        if (Object.keys(secretsObj).length === 0) {
          secretsObj['default_key'] = 'default_value'
        }
        
        response = await fetch(`http://localhost:8000/secrets/static/${newSecret.type}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ secrets: secretsObj })
        })
      }
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }
      
      const result = await response.json()
      alert(result.message)
      setNewSecret({ type: '', key: '', value: '' })
      setShowCreateForm(false)
      refreshSecrets()
    } catch (error) {
      console.error('Error creating secret:', error)
      alert(`Error creating secret: ${error.message}`)
    }
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
    fontWeight: '500',
    margin: '5px'
  }

  // Fetch all secrets on component mount
  useEffect(() => {
    fetchSecrets('all')
  }, [])

  const renderStaticSecretsTable = () => {
    if (!secrets?.static_secrets) return null

    // Convert the static_secrets object into an array for rendering
    const staticData = Object.entries(secrets.static_secrets).map(([secretType, secretData]) => ({
      name: secretType,
      displayName: secretType.charAt(0).toUpperCase() + secretType.slice(1) + ' Secrets',
      data: secretData.data || {},
      metadata: secretData.metadata || {}
    }))

    return (
      <div style={{ marginBottom: '30px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h3>Static Secrets (Manual Rotation) - {staticData.length} types found</h3>
          <button 
            onClick={() => setShowCreateForm(!showCreateForm)}
            style={{ ...buttonStyle, background: '#9C27B0' }}
          >
            {showCreateForm ? 'Cancel' : 'Create New Secret'}
          </button>
        </div>

        {showCreateForm && (
          <div style={{ background: '#f0f8ff', padding: '15px', borderRadius: '6px', marginBottom: '20px', border: '1px solid #b3d9ff' }}>
            <h4>Create New Secret</h4>
            <form onSubmit={createSecret} style={{ display: 'grid', gap: '10px', gridTemplateColumns: '1fr 1fr 2fr auto' }}>
              <input
                type="text"
                placeholder="Secret Type (e.g., database)"
                value={newSecret.type}
                onChange={(e) => setNewSecret({...newSecret, type: e.target.value})}
                required
                style={{ padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              />
              <input
                type="text"
                placeholder="Key (optional)"
                value={newSecret.key}
                onChange={(e) => setNewSecret({...newSecret, key: e.target.value})}
                style={{ padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              />
              <input
                type="text"
                placeholder="Value (or key=value,key2=value2)"
                value={newSecret.value}
                onChange={(e) => setNewSecret({...newSecret, value: e.target.value})}
                required
                style={{ padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              />
              <button type="submit" style={{ ...buttonStyle, background: '#4CAF50' }}>
                Create
              </button>
            </form>
            <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
              Leave key empty to create multiple key-value pairs (format: key1=value1,key2=value2)
            </small>
          </div>
        )}

        {staticData.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
            No static secrets found. Create one using the form above.
          </div>
        ) : (
          staticData.map((secretGroup, index) => (
            <div key={index} style={{ marginBottom: '20px', background: 'white', padding: '15px', borderRadius: '6px', border: '1px solid #ddd' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h4 style={{ margin: 0 }}>{secretGroup.displayName}</h4>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '12px', color: '#666' }}>
                    Type: {secretGroup.name}
                  </span>
                  <button
                    onClick={() => deleteEntireSecret(secretGroup.name)}
                    style={{ 
                      padding: '5px 10px', 
                      background: '#f44336', 
                      color: 'white', 
                      border: 'none', 
                      borderRadius: '3px', 
                      cursor: 'pointer',
                      fontSize: '12px'
                    }}
                    title="Delete entire secret"
                  >
                    Delete All
                  </button>
                </div>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>Key</th>
                    <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>Value</th>
                    <th style={{ padding: '10px', textAlign: 'center', border: '1px solid #ddd', width: '150px' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(secretGroup.data).length === 0 ? (
                    <tr>
                      <td colSpan="3" style={{ padding: '20px', textAlign: 'center', color: '#999', fontStyle: 'italic' }}>
                        This secret is empty. Click on the value column to add a new key-value pair.
                      </td>
                    </tr>
                  ) : (
                    Object.entries(secretGroup.data).map(([key, value], i) => (
                      <tr key={i}>
                        <td style={{ padding: '10px', border: '1px solid #ddd', fontWeight: 'bold' }}>{key}</td>
                        <td style={{ padding: '10px', border: '1px solid '}}>
                          {editing === `${secretGroup.name}-${key}` ? (
                            <input
                              type="text"
                              defaultValue={value}
                              onBlur={(e) => updateSecret(secretGroup.name, key, e.target.value)}
                              style={{ width: '100%', padding: '5px', border: '1px solid #ccc' }}
                              autoFocus
                            />
                          ) : (
                            <span 
                              onClick={() => setEditing(`${secretGroup.name}-${key}`)} 
                              style={{ cursor: 'pointer', fontFamily: 'monospace', minHeight: '20px', display: 'block' }}
                            >
                              {value || <span style={{ color: '#999', fontStyle: 'italic' }}>Click to add value</span>}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>
                          <button
                            onClick={() => deleteSecret(secretGroup.name, key)}
                            style={{ 
                              padding: '5px 10px', 
                              background: '#f44336', 
                              color: 'white', 
                              border: 'none', 
                              borderRadius: '3px', 
                              cursor: 'pointer',
                              fontSize: '12px'
                            }}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
              {secretGroup.metadata && (
                <div style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
                  Version: {secretGroup.metadata.version} | 
                  Created: {formatTimestamp(secretGroup.metadata.created_time)}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    )
  }

  const renderDynamicSecretsTable = () => {
    if (!secrets?.dynamic_secrets) return null

    const dynamicData = [
      {
        name: 'Database ReadOnly',
        data: secrets.dynamic_secrets.db_readonly?.data || {},
        metadata: secrets.dynamic_secrets.db_readonly?.metadata || {}
      },
      {
        name: 'Database Admin',
        data: secrets.dynamic_secrets.db_admin?.data || {},
        metadata: secrets.dynamic_secrets.db_admin?.metadata || {}
      }
    ]

    return (
      <div style={{ marginBottom: '30px' }}>
        <h3>Dynamic Secrets (Auto-Rotating Hourly)</h3>
        {dynamicData.map((secretGroup, index) => (
          <div key={index} style={{ marginBottom: '20px', background: 'white', padding: '15px', borderRadius: '6px', border: '1px solid #ddd' }}>
            <h4>{secretGroup.name}</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>Key</th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(secretGroup.data).map(([key, value], i) => (
                  <tr key={i}>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontWeight: 'bold' }}>{key}</td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontFamily: 'monospace' }}>
                      {key === 'password' ? '••••••••' : value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {secretGroup.metadata && (
              <div style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
                Generated: {formatTimestamp(secretGroup.metadata.generated_at)} | 
                Expires: {formatTimestamp(secretGroup.metadata.expires_at)} 
                ({getTimeRemaining(secretGroup.metadata.expires_at)} remaining) | 
                Connection: <span style={{ 
                  color: secretGroup.metadata.connection_test === 'successful' ? 'green' : 'red',
                  fontWeight: 'bold'
                }}>
                  {secretGroup.metadata.connection_test?.toUpperCase()}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    )
  }

  const renderDebugInfo = () => {
    if (!secrets) return null

    return (
      <div>
        <h3>Vault Debug Information</h3>
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
    )
  }

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif", maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: "20px" }}>
        <div>
          <h1 style={{ marginBottom: "5px" }}>Secrets Management Dashboard</h1>
          <p style={{ color: "#555" }}>
            View and manage all secrets stored in Vault with automatic rotation for dynamic credentials.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            onClick={refreshSecrets}
            disabled={loading}
            style={{ 
              ...buttonStyle, 
              background: '#2196F3',
              opacity: loading ? 0.7 : 1
            }}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
          <button 
            onClick={() => fetchSecrets('debug')}
            disabled={loading}
            style={{ 
              ...buttonStyle, 
              background: activeTab === 'debug' ? '#C62828' : '#f44336',
              opacity: loading && activeTab === 'debug' ? 0.7 : 1
            }}
          >
            Debug Info
          </button>
        </div>
      </div>

      {/* Content Area */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
          <div>Loading secrets...</div>
        </div>
      )}

      {secrets?.error && (
        <div style={{ color: 'red', padding: '10px', background: '#ffebee', borderRadius: '4px', marginBottom: '20px' }}>
          Error: {secrets.error}
        </div>
      )}

      {!loading && secrets && !secrets.error && (
        <div style={{ background: '#fafafa', borderRadius: '6px', padding: '20px', border: '1px solid #ddd' }}>
          {activeTab !== 'debug' && (
            <>
              {renderStaticSecretsTable()}
              {renderDynamicSecretsTable()}
            </>
          )}
          {activeTab === 'debug' && renderDebugInfo()}
          
          {secrets.timestamp && (
            <div style={{ fontSize: '12px', color: '#999', marginTop: '20px', textAlign: 'right' }}>
              Last updated: {formatTimestamp(secrets.timestamp)}
            </div>
          )}
        </div>
      )}

      {/* Information Section */}
      <div style={{ marginTop: '30px', padding: '20px', background: '#f5fdf5', borderRadius: '6px', fontSize: '14px', border: '1px solid #d9ead3' }}>
        <h4 style={{ marginTop: 0 }}>How it works</h4>
        <ul>
          <li><strong>Static Secrets</strong>: Click on values to edit, use Delete button to remove individual keys, use "Delete All" to remove entire secrets</li>
          <li><strong>Dynamic Secrets</strong>: Auto-rotating credentials (cannot be modified manually)</li>
          <li><strong>Create New</strong>: Use the form to create new secret types or add keys to existing ones</li>
          <li><strong>Refresh</strong>: Click refresh to get the latest secrets from Vault</li>
        </ul>
      </div>
    </div>
  )
}