import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { login as apiLogin, refreshToken as apiRefresh, logout as apiLogout, getMe } from '../api';

const AuthContext = createContext(null);

const TOKEN_KEY = 'anpr_access_token';
const REFRESH_KEY = 'anpr_refresh_token';
const USER_KEY = 'anpr_user';
const INACTIVITY_MS = 30 * 60 * 1000; // 30 minutes

const DEMO_ACCOUNTS = [
  { username: 'admin', password: 'Admin@123', role: 'Admin', label: 'Admin' },
  { username: 'police_sharma', password: 'Police@123', role: 'Traffic Police', label: 'Traffic Police' },
  { username: 'planner_verma', password: 'Planner@123', role: 'City Planner', label: 'City Planner' },
];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem(USER_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [accessToken, setAccessToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const inactivityTimer = useRef(null);
  const lastActivity = useRef(Date.now());

  const persistSession = useCallback((token, refresh, userData) => {
    setAccessToken(token);
    setUser(userData);
    localStorage.setItem(TOKEN_KEY, token);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    localStorage.setItem(USER_KEY, JSON.stringify(userData));
    lastActivity.current = Date.now();
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // ignore network errors on logout
    }
    clearSession();
    setShowLoginModal(false);
  }, [clearSession]);

  const resetInactivityTimer = useCallback(() => {
    lastActivity.current = Date.now();
    if (inactivityTimer.current) clearTimeout(inactivityTimer.current);
    if (!accessToken) return;

    inactivityTimer.current = setTimeout(() => {
      const elapsed = Date.now() - lastActivity.current;
      if (elapsed >= INACTIVITY_MS) {
        handleLogout();
        setShowLoginModal(true);
      }
    }, INACTIVITY_MS);
  }, [accessToken, handleLogout]);

  const handleLogin = useCallback(async (username, password) => {
    setLoading(true);
    try {
      const data = await apiLogin(username, password);
      persistSession(data.access_token, data.refresh_token, data.user);
      setShowLoginModal(false);
      return data;
    } finally {
      setLoading(false);
    }
  }, [persistSession]);

  const handleRefresh = useCallback(async () => {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (!refresh) throw new Error('No refresh token');
    const data = await apiRefresh(refresh);
    setAccessToken(data.access_token);
    localStorage.setItem(TOKEN_KEY, data.access_token);
    return data.access_token;
  }, []);

  // Track user activity for inactivity timeout
  useEffect(() => {
    if (!accessToken) return;

    const events = ['mousedown', 'keydown', 'scroll', 'touchstart'];
    const onActivity = () => resetInactivityTimer();
    events.forEach(e => window.addEventListener(e, onActivity));
    resetInactivityTimer();

    return () => {
      events.forEach(e => window.removeEventListener(e, onActivity));
      if (inactivityTimer.current) clearTimeout(inactivityTimer.current);
    };
  }, [accessToken, resetInactivityTimer]);

  // Validate stored token on mount
  useEffect(() => {
    if (!accessToken || user) return;
    getMe()
      .then(res => setUser(res.user))
      .catch(() => clearSession());
  }, [accessToken, user, clearSession]);

  const hasRole = useCallback((...roles) => {
    if (!user) return false;
    return roles.includes(user.role);
  }, [user]);

  const canAccessVault = hasRole('Admin', 'Traffic Police');
  const canAccessAlerts = hasRole('Admin', 'Traffic Police');
  const canAccessVideo = hasRole('Admin', 'Traffic Police');
  const canAccessLiveMap = hasRole('Admin', 'Traffic Police', 'City Planner');
  const canAccessAnalytics = hasRole('Admin', 'City Planner', 'Traffic Police');
  const canAccessAuditLogs = hasRole('Admin');

  const value = {
    user,
    accessToken,
    loading,
    isAuthenticated: !!user && !!accessToken,
    showLoginModal,
    setShowLoginModal,
    login: handleLogin,
    logout: handleLogout,
    refreshToken: handleRefresh,
    hasRole,
    canAccessVault,
    canAccessAlerts,
    canAccessVideo,
    canAccessLiveMap,
    canAccessAnalytics,
    canAccessAuditLogs,
    demoAccounts: DEMO_ACCOUNTS,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
