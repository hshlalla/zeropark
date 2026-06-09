import React from 'react';
import { LogIn } from 'lucide-react';

import { setToken } from '../api';

const Login: React.FC = () => {
  const handleGoogleLogin = () => {
    // Redirect to backend OAuth endpoint
    window.location.href = 'http://localhost:8000/api/v1/auth/google/login';
  };

  const handleGuestLogin = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/auth/guest/login', {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
        window.location.href = '/dashboard';
      } else {
        console.error("Guest login failed");
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="flex-center h-screen" style={{
      background: 'linear-gradient(135deg, var(--bg-color) 0%, rgba(37, 99, 235, 0.1) 100%)'
    }}>
      <div 
        className="glass-panel" 
        style={{
          padding: '3rem',
          borderRadius: '1rem',
          width: '100%',
          maxWidth: '400px',
          boxShadow: 'var(--shadow-lg)',
          textAlign: 'center'
        }}
      >
        <div style={{ marginBottom: '2rem' }}>
          <div style={{
            width: '64px',
            height: '64px',
            background: 'var(--primary-color)',
            borderRadius: '16px',
            margin: '0 auto 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            transform: 'rotate(-10deg)'
          }}>
            <span style={{ fontSize: '24px', fontWeight: 'bold' }}>Z</span>
          </div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '0.5rem' }}>Welcome to Zeropark</h1>
          <p style={{ color: 'var(--text-secondary)' }}>Log in to access your workspace.</p>
        </div>

        <button 
          onClick={handleGoogleLogin} 
          className="btn-secondary w-full"
          style={{ height: '48px', fontSize: '1rem', marginBottom: '1rem' }}
        >
          <img 
            src="https://www.svgrepo.com/show/475656/google-color.svg" 
            alt="Google" 
            style={{ width: '20px', height: '20px' }} 
          />
          Continue with Google
        </button>

        <button 
          onClick={handleGuestLogin} 
          className="btn-primary w-full"
          style={{ height: '48px', fontSize: '1rem', backgroundColor: 'var(--text-secondary)' }}
        >
          Guest Login (Test)
        </button>
      </div>
    </div>
  );
};

export default Login;
