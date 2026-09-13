import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useHub } from '../context/HubContext';
import { workspaceService } from '../services/workspaceService';

export default function WorkspaceRestorer() {
  const location = useLocation();
  const navigate = useNavigate();
  const { prefs } = useHub();
  const restored = useRef(false);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const sessionKey = 'koolkid_workspace_session_started';
    const firstViewThisSession = !sessionStorage.getItem(sessionKey);
    sessionStorage.setItem(sessionKey, '1');
    if (!prefs.restoreWorkspace || !firstViewThisSession || location.pathname !== '/') return;
    const lastPath = workspaceService.getRaw('last_path', '/');
    if (typeof lastPath === 'string' && lastPath.startsWith('/') && lastPath !== '/') {
      navigate(lastPath, { replace: true });
    }
  }, [location.pathname, navigate, prefs.restoreWorkspace]);

  useEffect(() => {
    if (!prefs.restoreWorkspace) return;
    workspaceService.set('last_path', location.pathname + location.search);
  }, [location.pathname, location.search, prefs.restoreWorkspace]);

  return null;
}
