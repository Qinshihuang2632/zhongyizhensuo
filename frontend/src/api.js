const TOKEN_KEY = 'zyzs_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers['X-Token'] = token

  let res
  try {
    res = await fetch('/api' + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new Error('无法连接本地服务，请重启程序')
  }

  if (res.status === 401) {
    setToken('')
    if (!location.hash.startsWith('#/login')) location.hash = '#/login'
    throw new Error('未登录或登录已过期')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `请求失败（${res.status}）`)
  return data
}
