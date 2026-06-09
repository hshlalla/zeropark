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
