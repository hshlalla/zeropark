// Single source of truth for the gateway address. Override per environment
// with VITE_API_URL (e.g. .env.local); defaults to the local gateway port.
export const API_BASE: string =
  (import.meta as any).env?.VITE_API_URL || 'http://localhost:8080';

export const setToken = (token: string) => {
  localStorage.setItem('zp_access_token', token);
};

export const getToken = (): string | null => {
  return localStorage.getItem('zp_access_token');
};

export const removeToken = () => {
  localStorage.removeItem('zp_access_token');
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

// Authenticated fetch helper: attaches the bearer token and bounces to login
// on 401 (stale token after a gateway restart, expired session, ...).
export const authFetch = async (path: string, options: RequestInit = {}): Promise<Response> => {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
    'Authorization': `Bearer ${getToken()}`,
  };
  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  handleAuthError(res);
  return res;
};

// Call on any 401 response: the stored token is stale (e.g. the gateway
// restarted with a new SECRET_KEY). Clears it and sends the user to login.
// Returns true when the response was a handled auth failure.
export const handleAuthError = (res: Response): boolean => {
  if (res.status === 401) {
    removeToken();
    window.location.href = '/login';
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
