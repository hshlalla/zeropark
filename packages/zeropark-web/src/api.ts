// Single source of truth for the gateway address. Override per environment
// with VITE_API_URL (e.g. .env.local); defaults to the local gateway port.
export const API_BASE: string =
  (import.meta as any).env?.VITE_API_URL || '';

export const setToken = (token: string) => {
  localStorage.setItem('zp_access_token', token);
};

export const getToken = (): string | null => {
  return localStorage.getItem('zp_access_token');
};

export const setRefreshToken = (token: string) => {
  localStorage.setItem('zp_refresh_token', token);
};

export const getRefreshToken = (): string | null => {
  return localStorage.getItem('zp_refresh_token');
};

// Store an auth response that may include access + refresh tokens.
export const storeTokens = (data: { access_token?: string; refresh_token?: string }) => {
  if (data.access_token) setToken(data.access_token);
  if (data.refresh_token) setRefreshToken(data.refresh_token);
};

export const removeToken = () => {
  localStorage.removeItem('zp_access_token');
  localStorage.removeItem('zp_refresh_token');
};

export const isAuthenticated = (): boolean => {
  return !!getToken();
};

// Read the caller's role from the JWT payload (UI hint only — every
// privileged action is re-checked server-side).
export const getRole = (): string => {
  const token = getToken();
  if (!token) return 'user';
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.role || 'user';
  } catch {
    return 'user';
  }
};

export const isAdmin = (): boolean => getRole() === 'admin';

// Try to mint a fresh access token from the stored refresh token. Returns the
// new access token on success, or null (caller should then send to login).
let _refreshInFlight: Promise<string | null> | null = null;
const refreshAccessToken = async (): Promise<string | null> => {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  // de-dupe concurrent refreshes so a burst of 401s makes one refresh call
  if (!_refreshInFlight) {
    _refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!res.ok) return null;
        const data = await res.json();
        storeTokens(data);
        return data.access_token || null;
      } catch {
        return null;
      } finally {
        _refreshInFlight = null;
      }
    })();
  }
  return _refreshInFlight;
};

const buildHeaders = (options: RequestInit, token: string | null): Record<string, string> => {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
    'Authorization': `Bearer ${token}`,
  };
  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  return headers;
};

// Authenticated fetch: attaches the bearer token. On 401, transparently tries
// a refresh-token exchange and retries once; if that fails, sends to login.
export const authFetch = async (path: string, options: RequestInit = {}): Promise<Response> => {
  let res = await fetch(`${API_BASE}${path}`, { ...options, headers: buildHeaders(options, getToken()) });
  if (res.status === 401) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      res = await fetch(`${API_BASE}${path}`, { ...options, headers: buildHeaders(options, fresh) });
    }
    if (res.status === 401) {
      removeToken();
      window.location.href = '/login';
    }
  }
  return res;
};

// For raw fetch() call sites: handle a 401 by trying refresh once. Returns a
// new access token to retry with, or null if the user must re-login.
export const handleAuthError = (res: Response): boolean => {
  if (res.status === 401) {
    // best-effort: attempt a silent refresh; on failure bounce to login
    refreshAccessToken().then((fresh) => {
      if (!fresh) {
        removeToken();
        window.location.href = '/login';
      }
    });
    return true;
  }
  return false;
};

export interface Artifact {
  id: string;
  kind: string;
  title?: string;
  uri?: string;
  mime_type: string;
  inline?: string;
}
