import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.wrapper}>
      <div style={styles.card}>
        <div style={styles.logoSection}>
          <div style={styles.logoIcon}>AR</div>
          <h1 style={styles.title}>Anand Rathi</h1>
          <p style={styles.subtitle}>Communications Intelligence Platform</p>
        </div>

        <form onSubmit={handleSubmit} style={styles.form}>
          {error && <div style={styles.error}>{error}</div>}

          <label style={styles.label}>Username</label>
          <input
            style={styles.input}
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Enter your username"
            required
          />

          <label style={styles.label}>Password</label>
          <input
            style={styles.input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
            required
          />

          <button style={styles.button} type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div style={styles.footer}>
          <p style={styles.footerText}>Demo: admin / admin123</p>
          <p style={styles.footerText}>RM: rm1 / rm123 | Client: client1 / client123</p>
        </div>
      </div>
    </div>
  );
}

const styles = {
  wrapper: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #EEF2F7 0%, #F8FAFB 50%, #EBF0F5 100%)',
    fontFamily: "'DM Sans', -apple-system, sans-serif",
  },
  card: {
    width: 400,
    background: '#FFFFFF',
    borderRadius: 16,
    padding: '40px 36px',
    boxShadow: '0 4px 24px rgba(15, 39, 68, 0.08)',
    border: '1px solid #E8ECF0',
  },
  logoSection: {
    textAlign: 'center',
    marginBottom: 32,
  },
  logoIcon: {
    width: 56,
    height: 56,
    borderRadius: 14,
    background: '#0F2744',
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: 700,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    letterSpacing: 1,
  },
  title: {
    fontSize: 22,
    fontWeight: 700,
    color: '#0F2744',
    margin: 0,
  },
  subtitle: {
    fontSize: 13,
    color: '#8B94A6',
    margin: '6px 0 0',
    fontWeight: 400,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  label: {
    fontSize: 13,
    fontWeight: 500,
    color: '#4A5568',
    marginTop: 8,
  },
  input: {
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #DDE2E8',
    fontSize: 14,
    outline: 'none',
    transition: 'border-color 0.2s',
    marginTop: 4,
    fontFamily: 'inherit',
  },
  button: {
    marginTop: 20,
    padding: '12px 0',
    borderRadius: 8,
    border: 'none',
    background: '#0F2744',
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
    letterSpacing: 0.3,
    transition: 'background 0.2s',
  },
  error: {
    background: '#FEF0E4',
    color: '#D4620A',
    padding: '10px 14px',
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 500,
  },
  footer: {
    marginTop: 24,
    textAlign: 'center',
    borderTop: '1px solid #F0F2F5',
    paddingTop: 16,
  },
  footerText: {
    fontSize: 12,
    color: '#A0A8B6',
    margin: '4px 0',
  },
};
