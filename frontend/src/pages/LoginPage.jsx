import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import logoUrl from '../assets/logo_tar.jpg';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [focusedField, setFocusedField] = useState(null);

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
      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={styles.card}>
        <div style={styles.logoSection}>
          <img src={logoUrl} alt="Tech Anand Rathi" style={styles.logo} />
          <p style={styles.subtitle}>Communications Intelligence Platform</p>
        </div>

        <form onSubmit={handleSubmit} style={styles.form}>
          {error && <div style={styles.error}>{error}</div>}

          <label style={styles.label}>Username</label>
          <input
            style={{
              ...styles.input,
              ...(focusedField === 'username' ? styles.inputFocused : {}),
            }}
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onFocus={() => setFocusedField('username')}
            onBlur={() => setFocusedField(null)}
            placeholder="Enter your username"
            required
          />

          <label style={styles.label}>Password</label>
          <input
            style={{
              ...styles.input,
              ...(focusedField === 'password' ? styles.inputFocused : {}),
            }}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onFocus={() => setFocusedField('password')}
            onBlur={() => setFocusedField(null)}
            placeholder="Enter your password"
            required
          />

          <button style={styles.button} type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
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
    background:
      'radial-gradient(circle at 85% 15%, #DDE8F5 0%, transparent 45%), ' +
      'radial-gradient(circle at 10% 90%, #E5EDF3 0%, transparent 50%), ' +
      'linear-gradient(135deg, #F1F5FA 0%, #F8FAFB 50%, #EEF2F7 100%)',
    fontFamily: "'DM Sans', -apple-system, sans-serif",
  },
  card: {
    width: 420,
    background: '#FFFFFF',
    borderRadius: 16,
    padding: '36px 36px 32px',
    boxShadow: '0 8px 32px rgba(15, 39, 68, 0.10), 0 2px 8px rgba(15, 39, 68, 0.04)',
    border: '1px solid #E8ECF0',
    animation: 'fadeUp 0.4s ease-out',
  },
  logoSection: {
    textAlign: 'center',
    marginBottom: 28,
  },
  logo: {
    width: '100%',
    maxWidth: 260,
    height: 'auto',
    display: 'block',
    margin: '0 auto 14px',
  },
  subtitle: {
    fontSize: 13,
    color: '#8B94A6',
    margin: 0,
    fontWeight: 400,
    letterSpacing: 0.2,
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
    transition: 'border-color 0.2s, box-shadow 0.2s',
    marginTop: 4,
    fontFamily: 'inherit',
  },
  inputFocused: {
    borderColor: '#0F2744',
    boxShadow: '0 0 0 3px rgba(15, 39, 68, 0.08)',
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
};