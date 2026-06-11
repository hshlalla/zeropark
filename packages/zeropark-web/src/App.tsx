import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useSearchParams } from 'react-router-dom';
import { setToken, isAuthenticated } from './api';

import Login from './pages/Login';
import DashboardLayout from './layouts/DashboardLayout';
import Dashboard from './pages/Dashboard';
import AppViewer from './pages/AppViewer';
import Knowledge from './pages/Knowledge';
import WorkflowEditor from './pages/WorkflowEditor';
import WorkflowRuns from './pages/WorkflowRuns';
import Admin from './pages/Admin';
import Settings from './pages/Settings';

// OAuth Callback handler component
const OAuthCallback: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  useEffect(() => {
    if (token) {
      setToken(token);
      window.location.href = '/dashboard';
    } else {
      window.location.href = '/login';
    }
  }, [token]);

  return <div>Authenticating...</div>;
};

// Private Route wrapper
const PrivateRoute = ({ children }: { children: React.ReactElement }) => {
  return isAuthenticated() ? children : <Navigate to="/login" replace />;
};

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<OAuthCallback />} />
        
        <Route 
          path="/dashboard" 
          element={
            <PrivateRoute>
              <DashboardLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="admin" element={<Admin />} />
          <Route path="settings" element={<Settings />} />
          <Route path="app/:appId" element={<AppViewer />} />
          <Route path="workflow/:appId" element={<WorkflowEditor />} />
          <Route path="workflow-runs" element={<WorkflowRuns />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
