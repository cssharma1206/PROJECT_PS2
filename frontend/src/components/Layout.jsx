import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LayoutDashboard, MessageSquare, Shield, LogOut, User } from 'lucide-react';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const navItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/query', icon: MessageSquare, label: 'Query' },
  ];

  if (user?.can_admin) {
    navItems.push({ to: '/admin', icon: Shield, label: 'Admin' });
  }

  return (
    <div style={styles.container}>
      {/* Sidebar */}
      <aside style={styles.sidebar}>
        <div style={styles.brand}>
          <div style={styles.brandIcon}>AR</div>
          <div>
            <div style={styles.brandTitle}>Anand Rathi</div>
            <div style={styles.brandSub}>Intelligence Platform</div>
          </div>
        </div>

        <nav style={styles.nav}>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              style={({ isActive }) => ({
                ...styles.navLink,
                ...(isActive ? styles.navLinkActive : {}),
              })}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div style={styles.userSection}>
          <div style={styles.userCard}>
            <div style={styles.userAvatar}>
              <User size={18} />
            </div>
            <div style={styles.userInfo}>
              <div style={styles.userName}>{user?.full_name || user?.username}</div>
              <div style={styles.userRole}>{user?.role_name}</div>
            </div>
          </div>
          <button onClick={handleLogout} style={styles.logoutBtn}>
            <LogOut size={16} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main style={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    minHeight: '100vh',
    background: '#F8FAFB',
    fontFamily: "'DM Sans', -apple-system, sans-serif",
  },
  sidebar: {
    width: 250,
    background: '#FFFFFF',
    borderRight: '1px solid #E8ECF0',
    display: 'flex',
    flexDirection: 'column',
    padding: '24px 16px',
    position: 'fixed',
    top: 0,
    left: 0,
    bottom: 0,
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '0 8px 24px',
    borderBottom: '1px solid #F0F2F5',
    marginBottom: 24,
  },
  brandIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    background: '#0F2744',
    color: '#FFF',
    fontSize: 15,
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    letterSpacing: 1,
    flexShrink: 0,
  },
  brandTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: '#0F2744',
  },
  brandSub: {
    fontSize: 11,
    color: '#8B94A6',
    fontWeight: 400,
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    flex: 1,
  },
  navLink: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 14px',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 500,
    color: '#5A6577',
    textDecoration: 'none',
    transition: 'all 0.15s',
  },
  navLinkActive: {
    background: '#EEF2F7',
    color: '#0F2744',
    fontWeight: 600,
  },
  userSection: {
    borderTop: '1px solid #F0F2F5',
    paddingTop: 16,
  },
  userCard: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '0 8px',
    marginBottom: 12,
  },
  userAvatar: {
    width: 36,
    height: 36,
    borderRadius: 8,
    background: '#EEF2F7',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#5A6577',
    flexShrink: 0,
  },
  userInfo: { flex: 1, minWidth: 0 },
  userName: {
    fontSize: 13,
    fontWeight: 600,
    color: '#0F2744',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  userRole: { fontSize: 11, color: '#8B94A6' },
  logoutBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    width: '100%',
    padding: '9px 14px',
    borderRadius: 8,
    border: '1px solid #E8ECF0',
    background: 'transparent',
    color: '#5A6577',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    fontFamily: 'inherit',
    transition: 'all 0.15s',
  },
  main: {
    flex: 1,
    marginLeft: 250,
    padding: '28px 32px',
    minHeight: '100vh',
  },
};
