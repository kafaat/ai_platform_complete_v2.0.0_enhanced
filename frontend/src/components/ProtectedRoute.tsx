import { Navigate, useLocation } from 'react-router-dom';
import { useIsAuthenticated, useCurrentUser } from '../hooks/useAuth';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'expert' | 'farmer' | 'viewer';
}

export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const isAuthenticated = useIsAuthenticated();
  const user = useCurrentUser();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requiredRole) {
    const roleLevel = { admin: 4, expert: 3, farmer: 2, viewer: 1 };
    const userLevel  = roleLevel[user?.role as keyof typeof roleLevel] ?? 0;
    const required   = roleLevel[requiredRole] ?? 0;
    if (userLevel < required) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
}

export default ProtectedRoute;
